import os
import sys
import json
import uuid
from pathlib import Path
from statistics import median
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from common import load_config, log_event, check_subscription, detect_operator, history_path, laya_state, last_active_rung, skill_dir, agents_dir

#-----------------------------------------------------------
# Functions
#-----------------------------------------------------------
def check_state(state, config):
    required = ['description', 'operation', 'files', 'ambiguous', 'critical']
    missing = [field for field in required if field not in state]
    if missing: raise ValueError(f'State missing fields {missing}. Required: {required}. Step: {state.get("description")}')
    if state['operation'] not in config['base_level_by_operation']: raise ValueError(f"Invalid operation '{state['operation']}'. Accepted: {list(config['base_level_by_operation'])}")

def overlaps(target_a, target_b):
    # same file, or one is a folder that contains the other
    a, b = Path(target_a).resolve(), Path(target_b).resolve()
    return a == b or a in b.parents or b in a.parents

def check_batch(states, config):
    # parallel agents writing to the same file overwrite each other without warning
    if len(states) > config['max_parallel']: raise ValueError(f"Batch with {len(states)} steps; the maximum is {config['max_parallel']} (max_parallel in ladder.json). Split it.")
    no_targets = [s['description'] for s in states if 'targets' not in s]
    if no_targets: raise ValueError(f'In a batch, every step declares "targets" (files or folders it writes; [] if read-only). Missing in: {no_targets}')
    for i, state_a in enumerate(states):
        for state_b in states[i + 1:]:
            shared = [(a, b) for a in state_a['targets'] for b in state_b['targets'] if overlaps(a, b)]
            if shared: raise ValueError(f"Steps with shared targets cannot share a batch: '{state_a['description']}' and '{state_b['description']}' on {shared}. Run them in sequence or isolate with a worktree.")

def limits(state, config, names):
    # ceiling: the last active rung (Fable stays off while it bills usage credits), and
    # security never climbs to Fable, which reroutes flagged cybersecurity requests to another model
    ceiling = min(config['ceiling_by_operation'].get(state['operation'], len(names) - 1), last_active_rung(config['ladder']))
    #
    # user_ceiling: the user declined a costly rung and chose the cheaper alternative
    user_ceiling = state.get('user_ceiling')
    if user_ceiling:
        if user_ceiling not in names: raise ValueError(f"user_ceiling '{user_ceiling}' is not on the ladder: {names}")
        ceiling = min(ceiling, names.index(user_ceiling))
    #
    # after a failure the step jumps escalation_jump rungs, because raising only the effort
    # of the same model rarely fixes what it could not
    floor = 0
    failed_with = state.get('failed_with')
    if failed_with:
        if failed_with not in names: raise ValueError(f"failed_with '{failed_with}' is not on the ladder: {names}")
        failed_level = names.index(failed_with)
        if failed_level >= ceiling: raise ValueError(f"Step '{state['description']}' already failed at the ceiling ({names[ceiling]}). Stop and ask the user instead of repeating it.")
        floor = min(failed_level + config['escalation_jump'], ceiling)
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

def laya_probabilities(state, config):
    # one binary question per rung, with neutral keys: Laya's noul type
    # tends to follow the true/false labels instead of the content
    questions = {}
    for rung in config['ladder']:
        questions[rung['agent']] = {
            'type':         'choice',
            'instructions': config['laya_question'].format(label=rung['label'], suited_for=rung['suited_for']),
            'criteria':     config['laya_criteria'],
        }
    # Explicitly select the public English checkpoint used by this skill.
    request_body = {'state': laya_state(state), 'questions': questions, 'model': config['laya_checkpoint']}
    body = json.dumps(request_body, ensure_ascii=False).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    # laya-serve only requires a key when started with LAYA_API_KEY
    if os.environ.get('LAYA_API_KEY'):
        headers['Authorization'] = f"Bearer {os.environ['LAYA_API_KEY']}"
    request = Request(config['laya_url'], data=body, headers=headers)
    with urlopen(request, timeout=config['laya_timeout_s']) as response:
        answers = json.load(response)['answers']
    return {name: answers[name]['probabilities']['A'] for name in questions}

def first_above_threshold(probabilities, names, floor, ceiling, threshold):
    for i in range(floor, ceiling + 1):
        if probabilities[names[i]] >= threshold:
            return i
    # no configuration is reliable enough: take the most capable one allowed
    return ceiling

def observed_token_costs(operator, operation, min_samples):
    history = history_path(operator)
    if not history.exists():
        return {}
    decisions, samples = {}, {}
    for line in history.read_text(encoding='utf-8').splitlines():
        event = json.loads(line)
        if event.get('event') == 'decision':
            decisions[event['id']] = event
        elif event.get('event') == 'result':
            decision = decisions.get(event['id'])
            tokens = event.get('tokens')
            if (decision and decision.get('backend', '').startswith(('heuristic', 'laya'))
                    and decision['state']['operation'] == operation
                    and not decision['state'].get('failed_with')
                    and isinstance(tokens, int) and tokens > 0):
                samples.setdefault(decision['agent'], []).append(tokens)
    return {name: median(values) for name, values in samples.items() if len(values) >= min_samples}

def choose_level(state, config, names, floor, ceiling):
    level, reasons = heuristic_level(state, config)
    if floor > level:
        level = floor
        reasons.append(f"floor {floor} after failing with {state['failed_with']}")
    if level > ceiling:
        level = ceiling
        reasons.append(f'capped at {names[ceiling]}')
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
    level = first_above_threshold(probabilities, names, floor, ceiling, config['success_threshold'])
    eligible = [i for i in range(floor, ceiling + 1)
                if probabilities[names[i]] >= config['success_threshold']]
    costs = observed_token_costs(config['operator'], state['operation'], config['min_cost_samples'])
    cost_reason = None
    if eligible and all(names[i] in costs for i in eligible):
        level = min(eligible, key=lambda i: (costs[names[i]] / probabilities[names[i]], i))
        cost_reason = f'estimated tokens per first-pass success={costs[names[level]] / probabilities[names[level]]:.0f}'
    reasons = [f"P(success)={probabilities[names[level]]:.3f}, threshold {config['success_threshold']}, floor {floor}, ceiling {ceiling}"]
    if cost_reason:
        reasons.append(cost_reason)
    elif eligible:
        reasons.append(f'token estimates incomplete (<{config["min_cost_samples"]} samples per eligible rung); using ladder order')
    if level > 0:
        reasons.append(f"rung below at P(success)={probabilities[names[level - 1]]:.3f}")
    return level, reasons, 'laya', probabilities

def alternative_without_approval(ladder, floor, level):
    # the most capable rung below the chosen one that needs no approval, never below the floor
    for i in range(level - 1, floor - 1, -1):
        if not ladder[i]['approval']:
            return ladder[i]['agent']
    return None

#-----------------------------------------------------------
# Input and paths
#-----------------------------------------------------------
if len(sys.argv) != 2: raise ValueError("usage: python route.py '<state JSON>' or '[<state>, <state>, ...]' for a parallel batch")

# Claude Code can switch from subscription billing when an API credential is set.
operator = detect_operator()
if operator == 'claude':
    check_subscription()

payload  = json.loads(sys.argv[1])
is_batch = isinstance(payload, list)
states   = payload if is_batch else [payload]
config   = load_config(operator)
ladder   = config['ladder']
names    = [rung['agent'] for rung in ladder]

if config['backend'] not in ('heuristic', 'laya'): raise ValueError(f"Invalid backend '{config['backend']}' in ladder.json. Accepted: heuristic, laya")
if config['backend'] == 'laya' and operator not in config['laya_enabled_operators']:
    config['backend'] = 'heuristic'
    config['backend_label'] = f'heuristic (no enabled {operator} Laya checkpoint)'
#-----------------------------------------------------------
# Check every step before deciding any
#-----------------------------------------------------------
# a batch is only logged if every step passes, so no orphan decision is left behind
for state in states:
    check_state(state, config)
if is_batch:
    check_batch(states, config)

limits_per_step = [limits(state, config, names) for state in states]
#-----------------------------------------------------------
# Decide each step
#-----------------------------------------------------------
batch_id  = uuid.uuid4().hex[:8] if is_batch else None
records   = []
decisions = []
for state, (floor, ceiling) in zip(states, limits_per_step):
    level, reasons, backend, probabilities = choose_level(state, config, names, floor, ceiling)
    rung = ladder[level]
    if operator == 'claude' and not (agents_dir / f"{rung['agent']}.md").exists(): raise FileNotFoundError(f"Agent {rung['agent']} is not installed. Run: python {skill_dir / 'scripts' / 'install.py'}")
    #
    decision_id = uuid.uuid4().hex[:8]
    records.append({
        'event':          'decision',
        'operator':       operator,
        'id':             decision_id,
        'batch':          batch_id,
        'state':          state,
        'agent':          rung['agent'],
        'level':          level,
        'needs_approval': rung['approval'],
        'backend':        backend,
        'probabilities':  probabilities,
    })
    # the orchestrator uses label, suited_for, reason and below to write the justification
    decisions.append({
        'id':             decision_id,
        'batch':          batch_id,
        'description':    state['description'],
        'operator':       operator,
        'agent':          rung['agent'],
        'label':          rung['label'],
        'model':          rung['model'],
        'effort':         rung['effort'],
        'suited_for':     rung['suited_for'],
        'reason':         '; '.join(reasons),
        'below':          f"{ladder[level - 1]['label']}: {ladder[level - 1]['suited_for']}" if level > 0 else None,
        'needs_approval': rung['approval'],
        'alternative':    alternative_without_approval(ladder, floor, level) if rung['approval'] else None,
        'backend':        backend,
    })
#-----------------------------------------------------------
# Log and return
#-----------------------------------------------------------
for record in records:
    log_event(record)

print(json.dumps(decisions if is_batch else decisions[0], ensure_ascii=False))
