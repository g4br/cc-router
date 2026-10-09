import os
import sys
import json
import uuid
from pathlib import Path
from statistics import median
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from urllib.error import URLError, HTTPError

from common import load_config, log_event, check_subscription, detect_operator, history_path, laya_state, last_active_rung, skill_dir, agents_dir

#-----------------------------------------------------------
# Functions
#-----------------------------------------------------------
from state import check_state

def overlaps(target_a, target_b):
    # same file, or one is a folder that contains the other
    a, b = Path(target_a).resolve(), Path(target_b).resolve()
    return a == b or a in b.parents or b in a.parents

def check_batch(states, config):
    from planning import plan
    return plan(states, config)

def limits(state, config, names):
    # Compatibility helper for legacy consumers; native v2 uses eligibility gates.
    ceiling = min(config['ceiling_by_operation'].get(state['operation'], len(names) - 1), last_active_rung(config['ladder']))
    #
    # user_ceiling: the user declined a costly rung and chose the cheaper alternative
    user_ceiling = state.get('user_ceiling')
    if user_ceiling:
        if user_ceiling not in names: raise ValueError(f"user_ceiling '{user_ceiling}' is not on the ladder: {names}")
        ceiling = min(ceiling, names.index(user_ceiling))
    #
    # The old fixed jump remains available only in this legacy helper.
    floor = 0
    user_floor = state.get('user_floor')
    if user_floor:
        if user_floor not in names: raise ValueError(f"user_floor '{user_floor}' is not on the ladder: {names}")
        floor = min(names.index(user_floor), ceiling)
    failed_with = state.get('failed_with')
    if failed_with:
        if failed_with not in names: raise ValueError(f"failed_with '{failed_with}' is not on the ladder: {names}")
        failed_level = names.index(failed_with)
        if failed_level >= ceiling: raise ValueError(f"Step '{state['description']}' already failed at the ceiling ({names[ceiling]}). Stop and ask the user instead of repeating it.")
        floor = max(floor, min(failed_level + config['escalation_jump'], ceiling))
    return floor, ceiling

def heuristic_level(state, config):
    level = config['base_level_by_operation'][state['operation']]
    reasons = [f"operation={state['operation']} (rung {level})"]
    #
    if state['files'] > config['file_limit']:
        level += 1
        reasons.append(f"+1 files>{config['file_limit']}")
    if state['ambiguous']:
        level += 1
        reasons.append('+1 ambiguous')
    if state['critical']:
        level += 1
        reasons.append('+1 critical')
    return level, reasons

SWAPPED_SUFFIX = '#swapped'

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("laya response: redirects are not permitted")


def laya_probabilities(state, config):
    # one binary question per rung, with neutral keys: Laya's noul type
    # tends to follow the true/false labels instead of the content.
    # laya-serve renders options in criteria key order, so every question is sent twice,
    # once as A,B and once as B,A, and the two "A" (yes) probabilities are averaged to
    # cancel position bias. Both copies travel in the same request.
    criteria = config['laya_criteria']
    swapped = {'B': criteria['B'], 'A': criteria['A']}
    questions = {}
    for rung in config['ladder']:
        instructions = config['laya_question'].format(label=rung['label'], suited_for=rung['suited_for'])
        questions[rung['agent']] = {'type': 'choice', 'instructions': instructions, 'criteria': criteria}
        questions[rung['agent'] + SWAPPED_SUFFIX] = {'type': 'choice', 'instructions': instructions, 'criteria': swapped}
    # Explicitly select the public English checkpoint used by this skill.
    request_body = {'state': laya_state(state), 'questions': questions, 'model': config['laya_checkpoint']}
    body = json.dumps(request_body, ensure_ascii=False).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    # laya-serve only requires a key when started with LAYA_API_KEY
    if os.environ.get('LAYA_API_KEY'):
        headers['Authorization'] = f"Bearer {os.environ['LAYA_API_KEY']}"
    request = Request(config['laya_url'], data=body, headers=headers)
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=config['laya_timeout_s']) as response:
            answers = json.load(response)['answers']
        from candidates import number
        values = {}
        for rung in config['ladder']:
            name = rung['agent']
            pair = [answers[key]['probabilities']['A'] for key in (name, name + SWAPPED_SUFFIX)]
            for value in pair:
                number(value, 'laya score', 0, 1)
            values[name] = sum(pair) / 2
        return values
    except (KeyError, TypeError, ValueError):
        raise ValueError('laya response: invalid score contract') from None

def first_above_threshold(probabilities, ladder, floor, ceiling, threshold):
    for i in range(floor, ceiling + 1):
        if i > floor and ladder[i].get('escalation_only'):
            continue
        if probabilities[ladder[i]['agent']] >= threshold:
            return i
    # no reachable rung is reliable enough: Laya has no opinion, so the heuristic decides
    return None

def below_escalation_only(level, floor, ladder):
    # max-effort rungs cost several times the rung below for a marginal gain: reached only by a floor
    while level > floor and ladder[level].get('escalation_only'):
        level -= 1
    return level

def observed_token_costs(operator, operation, min_samples):
    history = history_path(operator)
    if not history.exists():
        return {}
    decisions, samples = {}, {}
    for event in read_history(history):
        if event.get('event') == 'decision':
            decisions[event['id']] = event
        elif event.get('event') == 'result':
            decision = decisions.get(event['id'])
            tokens = event.get('tokens')
            if (decision and decision.get('backend', '').startswith(('heuristic', 'laya'))
                    and decision['state']['operation'] == operation
                    and not decision['state'].get('failed_with')
                    and event.get('result') == 'success' and type(tokens) is int and tokens > 0):
                samples.setdefault(decision['agent'], []).append(tokens)
    return {name: median(values) for name, values in samples.items() if len(values) >= min_samples}

def choose_level(state, config, names, floor, ceiling):
    level, reasons = heuristic_level(state, config)
    if floor > level:
        level = floor
        reasons.append(f"floor {floor} after failing with {state['failed_with']}" if state.get('failed_with') else f"floor {floor} from user_floor")
    if level > ceiling:
        level = ceiling
        reasons.append(f'capped at {names[ceiling]}')
    if below_escalation_only(level, floor, config['ladder']) != level:
        level = below_escalation_only(level, floor, config['ladder'])
        reasons.append(f'{names[level + 1]} only by escalation')
    if config['backend'] == 'heuristic':
        return level, reasons, config.get('backend_label', 'heuristic'), None
    #
    try:
        probabilities = laya_probabilities(state, config)
    except HTTPError:
        # the server answered with an error: malformed request or broken model, not an outage
        raise
    except (URLError, TimeoutError) as error:
        print(f'Laya unavailable at {config["laya_url"]} ({error}); deciding with the heuristic', file=sys.stderr)
        return level, reasons, 'heuristic (laya unavailable)', None
    #
    level = first_above_threshold(probabilities, config['ladder'], floor, ceiling, config['success_threshold'])
    if level is None:
        level, reasons, _, _ = choose_level(state, dict(config, backend='heuristic'), names, floor, ceiling)
        reasons.append(f"no reachable rung at uncalibrated score>={config['success_threshold']}; heuristic decides")
        return level, reasons, 'laya (no opinion)', probabilities
    eligible = [i for i in range(floor, ceiling + 1)
                if probabilities[names[i]] >= config['success_threshold'] and (i == floor or not config['ladder'][i].get('escalation_only'))]
    costs = observed_token_costs(config['operator'], state['operation'], config['min_cost_samples'])
    cost_reason = None
    if eligible and all(names[i] in costs for i in eligible):
        level = min(eligible, key=lambda i: (costs[names[i]], i))
        cost_reason = f'legacy observed successful-attempt tokens={costs[names[level]]:.0f}'
    reasons = [f"uncalibrated score={probabilities[names[level]]:.3f}, threshold {config['success_threshold']}, floor {floor}, ceiling {ceiling}"]
    if cost_reason:
        reasons.append(cost_reason)
    elif eligible:
        reasons.append(f'token estimates incomplete (<{config["min_cost_samples"]} samples per eligible rung); using ladder order')
    if level > 0:
        reasons.append(f"rung below at uncalibrated score={probabilities[names[level - 1]]:.3f}")
    return level, reasons, 'laya', probabilities

def alternative_without_approval(ladder, floor, level):
    # the most capable rung below the chosen one that needs no approval, never below the floor
    for i in range(level - 1, floor - 1, -1):
        if not ladder[i]['approval']:
            return ladder[i]['agent']
    return None

from common import read_history
from failures import diagnose
from selection import eligible_candidates, select, needs_approval
from telemetry import profile, estimates


def route_one(state, config, events, batch_id=None):
    diagnosis = diagnose(state, config)
    eligible, excluded = eligible_candidates(state, config, diagnosis)
    decision_id, attempt_id = uuid.uuid4().hex, uuid.uuid4().hex
    task_id = state.get('task_id', uuid.uuid4().hex)
    common = {'schema_version': 2, 'id': decision_id, 'decision_id': decision_id,
              'task_id': task_id, 'attempt_id': attempt_id, 'batch': batch_id,
              'host': config['operator'], 'operator': config['operator'],
              'description': state['description'], 'user_language': state.get('user_language'),
              'eligible': [c['id'] for c in eligible], 'excluded': excluded,
              'failure': diagnosis, 'task_profile': profile(state, config['file_limit']),
              'policy': state.get('policy', config['policy']),
              'attempt_count': state.get('attempt_count', 1 if state.get('failed_with') else 0) + 1,
              'constraints': {k: state[k] for k in ('user_ceiling', 'user_floor', 'blocked_candidates',
                              'allowed_candidates', 'required_capabilities') if k in state}}
    if diagnosis['kind'] and not diagnosis['retry_allowed']:
        common.update(selected=None, agent=None, model=None, effort=None, label=None, suited_for=None,
                      needs_approval=diagnosis['action'] in ('request_authorization', 'approve_non_idempotent_retry'),
                      alternative=None, below=None, backend='heuristic', confidence='unknown',
                      reason=diagnosis['action'], execution={'status': 'blocked', 'applied': False},
                      uncertainty='failure must be resolved before retry')
        return common
    if not eligible:
        raise ValueError('candidates: no eligible native candidate under current constraints')
    baseline, reasons = heuristic_level(state, config)
    backend, scores = config['backend'], None
    if backend == 'laya' and config['operator'] not in config['laya_enabled_operators']:
        backend = 'heuristic (host Laya disabled)'
    if backend == 'laya':
        try:
            by_agent = laya_probabilities(state, dict(config, ladder=eligible))
            scores = {c['id']: by_agent[c['agent']] for c in eligible}
        except HTTPError:
            raise ValueError('laya response: HTTP error; check local service contract') from None
        except (URLError, TimeoutError, ConnectionError):
            backend = 'heuristic (laya unavailable)'
            print('Laya unavailable; deciding with the heuristic', file=sys.stderr)
    evidence = estimates(events, state, eligible, config, scores)
    chosen, selection_reasons, confidence, objectives = select(state, config, eligible, evidence, baseline, scores)
    if state.get('policy', config['policy']) == 'legacy':
        if scores:
            above = [c for c in eligible if scores[c['id']] >= config['success_threshold']]
            if above:
                chosen = min(above, key=lambda c: c['legacy_rank'])
        selection_reasons = ['legacy operation/flags and first score above transitional threshold; current safety gates apply']
    if scores and not any(s >= config['success_threshold'] for s in scores.values()):
        backend = 'laya (no opinion)'
    if config['operator'] == 'claude' and not (agents_dir / f"{chosen['agent']}.md").exists():
        raise FileNotFoundError('Agent is not installed. Run scripts/install.py for Claude Code')
    alternatives = [c for c in eligible if c['id'] != chosen['id']]
    nearest = min(alternatives, key=lambda c: abs(c['legacy_rank']-chosen['legacy_rank']), default=None)
    safe = [c for c in alternatives if not needs_approval(c) and c['consumption_tier'] <= chosen['consumption_tier']]
    alternative = min(safe, key=lambda c: abs(c['legacy_rank']-chosen['legacy_rank']), default=None)
    limitations = ['native host must confirm effective model and effort', config['host_config']['capability_source']]
    if config['operator'] == 'claude' and any(os.environ.get(k) for k in ('CLAUDE_CODE_EFFORT_LEVEL', 'CLAUDE_CODE_SUBAGENT_MODEL_FORCE')):
        limitations.append('host environment may override selected settings')
    common.update(selected=chosen['id'], agent=chosen['agent'], model=chosen['model'], effort=chosen['effort'],
                  label=chosen['label'], suited_for=chosen['suited_for'],
                  needs_approval=needs_approval(chosen), alternative=alternative['agent'] if alternative else None,
                  nearest_alternative=nearest['id'] if nearest else None,
                  below=f"{nearest['label']}: {nearest['suited_for']}" if nearest else None,
                  backend=backend, confidence=confidence, uncertainty='observational estimates; untried outcomes unknown',
                  reason='; '.join(reasons + selection_reasons), evidence=evidence, objectives=objectives,
                  scores=scores, score_kind='uncalibrated' if scores else None,
                  billing_mode=chosen['billing_mode'],
                  execution={'mode': 'native', 'status': 'requires_host_confirmation', 'applied': False,
                             'effective_candidate': None, 'resolved_model': None, 'effective_effort': None,
                             'limitations': limitations})
    return common


def link_task(state, events, config):
    if not state.get('task_id'):
        return
    prior = [e for e in events if e.get('event') == 'decision' and e.get('task_id') == state['task_id']]
    if not prior:
        return
    previous = prior[-1]
    results = [e for e in events if e.get('event') == 'result' and e['id'] in {p['id'] for p in prior}]
    if any(e.get('result') == 'success' and e.get('task_complete', True) for e in results):
        raise ValueError('task_id: already completed; use a new task ID')
    if previous['task_profile'] != profile(state, config['file_limit']):
        raise ValueError('task_id: task profile changed; create a new task')
    answers = [e.get('answer') for e in events if e.get('event') == 'justification' and e['id'] == previous['id']]
    if 'declined' in answers:
        if not state.get('user_ceiling') and not state.get('allowed_candidates'):
            raise ValueError('user_ceiling: required after a declined decision')
        blocked = state.setdefault('blocked_candidates', [])
        if previous['selected'] not in blocked:
            blocked.append(previous['selected'])
    elif previous.get('selected') and not any(r['id'] == previous['id'] for r in results):
        raise ValueError('task_id: previous attempt has no result; record it before retrying')
    if results:
        latest = results[-1]
        decision = next(p for p in prior if p['id'] == latest['id'])
        state.setdefault('failed_with', decision['selected'])
        state.setdefault('failure_kind', latest.get('failure_kind') or 'unknown')
        if state.get('attempt_count', len(results)) != len(results):
            raise ValueError('attempt_count: disagrees with task history')
        state['attempt_count'] = len(results)
    check_state(state, config)


def decision_record(state, decision):
    record = {k: v for k, v in decision.items() if k not in ('description', 'user_language')}
    record.update(event='decision', state={k: state[k] for k in
                  ('operation', 'files', 'ambiguous', 'critical', 'failed_with', 'context_class') if k in state})
    return record


def compact(decision):
    keys = ('id', 'task_id', 'selected', 'agent', 'model', 'effort', 'needs_approval',
            'alternative', 'failure', 'execution', 'scheduling')
    result = {key: decision[key] for key in keys if key in decision}
    result['execution'] = {key: decision['execution'][key] for key in ('mode', 'status', 'applied')
                           if key in decision['execution']}
    if decision['needs_approval'] or decision['execution']['status'] == 'blocked':
        result.update(reason=decision['reason'], nearest_alternative=decision.get('nearest_alternative'),
                      billing_mode=decision.get('billing_mode'))
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Classify a task; use scheduler.py for a live DAG')
    parser.add_argument('state', nargs='?')
    parser.add_argument('--state-file', type=Path)
    parser.add_argument('--compact', action='store_true')
    args = parser.parse_args()
    if (args.state is None) == (args.state_file is None):
        parser.error('provide state JSON or --state-file')
    operator = detect_operator()
    if operator == 'claude':
        check_subscription()
    try:
        payload = json.loads(args.state_file.read_text() if args.state_file else args.state)
    except json.JSONDecodeError:
        raise ValueError('state: invalid JSON') from None
    is_batch = type(payload) is list
    states = payload if is_batch else [payload]
    if not states:
        raise ValueError('batch: must not be empty')
    config = load_config(operator)
    for state in states:
        check_state(state, config)
    schedule = check_batch(states, config) if is_batch else None
    events = read_history(history_path(operator))
    batch_id = uuid.uuid4().hex if is_batch else None
    for state in states:
        link_task(state, events, config)
    decisions = [route_one(state, config, events, batch_id) for state in states]
    if schedule:
        for decision, step in zip(decisions, schedule):
            decision['scheduling'] = step
    # All decisions and checks finish before the first history mutation.
    for state, decision in zip(states, decisions):
        log_event(decision_record(state, decision))
    output = [compact(d) for d in decisions] if args.compact else decisions
    print(json.dumps(output if is_batch else output[0], ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        print(f'cc-router: {error}', file=sys.stderr)
        sys.exit(1)
