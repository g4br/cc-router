"""Event-driven DAG reservations. Native tools execute; Python never watches with an LLM.

Only `next` classifies ready work. `finish` consumes a recorded, validated result.
State is private, locked and atomically replaced; pending audit events are replayable.
"""
import argparse
import copy
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import uuid

from candidates import require, string, number
from common import detect_operator, check_subscription, load_config, history_path, read_history, log_event
from planning import plan, verify_changes
from difficulty import MAX_STATES
from route import route_one, link_task, compact, decision_record, difficulty_active, difficulty_answers, UNSET
from state import check_state
from telemetry import workflow_efficiency

OVERHEAD = ('planning', 'classification', 'delegation', 'validation')


def emit(run, event, **fields):
    run['outbox'].append({'event': event, 'id': run['id'], 'run_id': run['id'],
                          'operator': run['operator'], 'event_id': uuid.uuid4().hex, **fields})


def initialize(payload, config):
    require(type(payload) is list and bool(payload), 'plan', 'expected nonempty task list')
    run = {'schema_version': 1, 'id': uuid.uuid4().hex, 'operator': config['operator'],
           'tasks': {}, 'outbox': [], 'overhead': {k: None for k in OVERHEAD},
           'routing_seconds': 0.0}
    states = []
    for item in payload:
        require(type(item) is dict, 'task', 'expected object')
        state = copy.deepcopy(item)
        acceptance = state.pop('acceptance', None)
        string(acceptance, 'acceptance', 2000)
        require('step_id' in state, 'step_id', 'required for scheduler tasks')
        require(not any(k in state for k in ('task_id', 'failed_with', 'attempt_count', 'failure_kind')),
                'task', 'new plans cannot import attempt identities')
        state['project_root'] = str(Path(state.get('project_root', '.')).resolve())
        state['task_id'] = uuid.uuid4().hex
        check_state(state, config)
        require(state['step_id'] not in run['tasks'], 'step_id', 'duplicate ID')
        states.append(state)
        run['tasks'][state['step_id']] = {'state': state, 'acceptance': acceptance,
                                        'status': 'PENDING', 'decision': None, 'output_ref': None}
    plan(states, config)  # Validate the whole graph without classifying any task.
    emit(run, 'workflow_started', tasks=len(states), task_ids=[s['task_id'] for s in states])
    return run


def reserve(run, config, events, capacity):
    number(capacity, 'capacity', 0, 10000, True)
    tasks = run['tasks']
    states = [t['state'] for t in tasks.values()]
    for state in states:
        check_state(state, config)
    plan(states, config)  # Recheck live configuration and symlink/path ownership.
    limit = min([config['max_parallel']] + [s.get('host_max_parallel', config['max_parallel']) for s in states])
    active = [t for t in tasks.values() if t['status'] == 'RESERVED']
    slots = min(capacity, max(0, limit - len(active)))
    dispatch = []
    if any(t['state'].get('isolation') == 'sequential' for t in active):
        return dispatch
    while slots > 0:
        # Gather the next ready tasks, then route them with one Laya request (a blocked task frees its slot: gather again).
        picked = []
        for step_id, task in tasks.items():
            if task['status'] != 'PENDING':
                continue
            dependencies = task['state'].get('depends_on', [])
            if not all(tasks[d]['status'] == 'DONE' for d in dependencies):
                continue
            serial = task['state'].get('isolation') == 'sequential'
            if serial and (active or dispatch or picked):
                continue
            state = copy.deepcopy(task['state'])
            context = {d: tasks[d]['output_ref'] for d in dependencies}
            state['description'] += '\nAcceptance: ' + task['acceptance']
            if context:
                state['description'] += '\nVerified dependency artifacts: ' + json.dumps(context, ensure_ascii=False)
            check_state(state, config)
            link_task(state, events, config)
            picked.append((step_id, task, state, context, serial))
            if serial or len(picked) == min(slots, MAX_STATES):
                break
        if not picked:
            break
        started = time.monotonic()
        answers = difficulty_answers([p[2] for p in picked], config) if difficulty_active(config) else [UNSET] * len(picked)
        decisions = [route_one(p[2], config, events, run['id'], answer) for p, answer in zip(picked, answers)]
        run['routing_seconds'] += time.monotonic() - started
        for (step_id, task, state, context, serial), decision in zip(picked, decisions):
            task['decision'] = decision
            task['status'] = 'BLOCKED' if decision['execution']['status'] == 'blocked' else 'RESERVED'
            record = decision_record(state, decision)
            record.update(event_id=uuid.uuid4().hex, run_id=run['id'])
            run['outbox'].append(record)
            if task['status'] == 'BLOCKED':
                continue
            emit(run, 'task_reserved', step_id=step_id, decision_id=decision['id'])
            dispatch.append({'step_id': step_id, 'decision': compact(decision),
                             'description': task['state']['description'], 'acceptance': task['acceptance'],
                             'project_root': state['project_root'],
                             'write_targets': state.get('write_targets', state.get('targets', [])),
                             'read_targets': state.get('read_targets', []),
                             'user_language': state.get('user_language'), 'dependencies': context})
            slots -= 1
            if serial:
                return dispatch
    return dispatch


def finish(run, step_id, report, events):
    require(step_id in run['tasks'], 'step_id', 'unknown task')
    task = run['tasks'][step_id]
    require(type(report) is dict and set(report) <= {'decision_id', 'changed_paths', 'evidence', 'output_ref'},
            'report', 'unknown fields')
    decision = task['decision']
    require(decision is not None and report.get('decision_id') == decision['id'],
            'decision_id', 'missing or stale attempt')
    if task['status'] in ('DONE', 'FAILED'):
        require(task.get('report') == report, 'report', 'completion already recorded differently')
        return  # At-least-once delivery is safe; no duplicate completion.
    require(task['status'] == 'RESERVED', 'task', 'not reserved')
    results = [e for e in events if e.get('event') == 'result' and e['id'] == decision['id']]
    require(len(results) == 1, 'result', 'record exactly one host outcome with record.py first')
    result = results[0]
    if result['result'] == 'success':
        require(result.get('verification') == 'passed' and result.get('task_complete') is True,
                'verification', 'task criterion must pass completely')
        string(report.get('evidence'), 'evidence', 2000)
        string(report.get('output_ref'), 'output_ref', 512)
        require('changed_paths' in report, 'changed_paths', 'actual changes required; [] for read-only')
        ownership = verify_changes([task['state']], {step_id: report['changed_paths']})
        require(not ownership['unexpected_steps'], 'changed_paths', 'changes outside declared ownership')
        task['status'], task['output_ref'] = 'DONE', report['output_ref']
    else:
        task['status'] = 'FAILED'
    task['report'] = report
    emit(run, 'task_completed' if task['status'] == 'DONE' else 'task_failed',
         step_id=step_id, task_id=task['state']['task_id'], decision_id=decision['id'])


def revise(run, step_id, patch, config, events, retry=False):
    require(step_id in run['tasks'], 'step_id', 'unknown task')
    task = run['tasks'][step_id]
    allowed = {'description', 'files', 'ambiguous', 'critical', 'context_class',
               'user_ceiling', 'user_floor', 'blocked_candidates', 'allowed_candidates', 'policy'}
    if retry:
        allowed |= {'failure_kind', 'idempotent', 'retry_approved', 'diff_verified', 'recovery_confirmed'}
        decision = task['decision']
        declined = decision and any(e.get('event') == 'justification' and e['id'] == decision['id']
                                    and e.get('answer') == 'declined' for e in events)
        require(task['status'] in ('FAILED', 'BLOCKED') or (task['status'] == 'RESERVED' and declined),
                'retry', 'finish the attempt or record refusal first; no automatic replay')
    else:
        require(task['status'] == 'PENDING' and task['decision'] is None, 'update', 'task already classified')
    require(type(patch) is dict and set(patch) <= allowed, 'update', 'unsupported fields')
    state = copy.deepcopy(task['state'])
    # Recovery attestations expire with each attempt; never reuse an old diff approval.
    for key in ('diff_verified', 'retry_approved', 'recovery_confirmed', 'failure_kind', 'failed_with', 'attempt_count'):
        state.pop(key, None)
    state.update(patch)
    if retry:
        # link_task hydrates failure and attempt counters before strict validation.
        link_task(state, events, config)
    check_state(state, config)
    task.update(state=state, status='PENDING')
    emit(run, 'task_retry_requested' if retry else 'task_updated', step_id=step_id)


def usage(run, values):
    require(type(values) is dict and set(values) <= set(OVERHEAD), 'usage', 'unknown overhead phase')
    for key, value in values.items():
        number(value, key, 0, 10**15, True)
        require(run['overhead'][key] is None or value >= run['overhead'][key], key, 'cumulative total cannot decrease')
    run['overhead'].update(values)
    emit(run, 'workflow_usage', overhead=run['overhead'].copy(), source='host_report', unit='tokens')


def status(run, events, recover=False):
    tasks = run['tasks']
    return {'run_id': run['id'], 'complete': all(t['status'] == 'DONE' for t in tasks.values()),
            'tasks': {k: t['status'] for k, t in tasks.items()},
            'reserved': {k: compact(t['decision']) if recover or t['status'] == 'BLOCKED' else t['decision']['id']
                         for k, t in tasks.items() if t['status'] in ('RESERVED', 'BLOCKED')},
            'routing_seconds': run['routing_seconds'],
            'efficiency': workflow_efficiency(events, [t['state']['task_id'] for t in tasks.values()],
                                              sum(t['status'] == 'DONE' for t in tasks.values()), run['overhead'])}


def save(path, run):
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(run, handle, ensure_ascii=False, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def flush(run, events):
    known = {e.get('event_id') for e in events}
    for event in run['outbox']:
        if event['event_id'] not in known:
            log_event(event)
            events.append(event)
            known.add(event['event_id'])
    run['outbox'] = []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('init', 'next', 'status', 'finish', 'update', 'retry', 'usage'):
        command = sub.add_parser(name)
        command.add_argument('run', type=Path)
        if name == 'init':
            command.add_argument('plan', type=Path)
        if name == 'next':
            command.add_argument('--capacity', type=int, required=True, help='currently free native slots, excluding this run reservations')
        if name in ('finish', 'update', 'retry'):
            command.add_argument('step_id')
        if name in ('finish', 'update', 'retry', 'usage'):
            command.add_argument('payload', help='JSON object, or @path to a JSON file')
    args = parser.parse_args()
    operator = detect_operator()
    config = load_config(operator)
    if operator == 'claude':
        check_subscription()
    path = args.run.resolve()
    require(path.parent.is_dir(), 'run', 'parent directory must exist')
    fd = os.open(str(path) + '.lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        events = read_history(history_path(operator))
        if args.command == 'init':
            require(not path.exists(), 'run', 'already exists; use status to recover')
            run = initialize(json.loads(args.plan.read_text()), config)
        else:
            run = json.loads(path.read_text())
            require(run.get('schema_version') == 1 and run['operator'] == operator, 'run', 'schema or host mismatch')
            flush(run, events)
        dispatch = []
        payload = None
        if hasattr(args, 'payload'):
            raw = Path(args.payload[1:]).read_text() if args.payload.startswith('@') else args.payload
            payload = json.loads(raw)
        if args.command == 'next':
            dispatch = reserve(run, config, events, args.capacity)
        elif args.command == 'finish':
            finish(run, args.step_id, payload, events)
        elif args.command in ('update', 'retry'):
            revise(run, args.step_id, payload, config, events, retry=args.command == 'retry')
        elif args.command == 'usage':
            usage(run, payload)
        # Commit reservations before emitting history or returning dispatch instructions.
        save(path, run)
        flush(run, events)
        print(json.dumps({**status(run, events, recover=args.command == 'status'), 'dispatch': dispatch},
                         ensure_ascii=False, allow_nan=False))
    finally:
        os.close(fd)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        print(f'cc-router scheduler: {error}', file=sys.stderr)
        sys.exit(1)
