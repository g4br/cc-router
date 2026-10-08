import argparse
import math
from failures import KINDS
from candidates import string

from common import decision_events, log_event

#-----------------------------------------------------------
# Input and paths
#-----------------------------------------------------------
parser = argparse.ArgumentParser(description='Record one routed attempt and its verified outcome')
parser.add_argument('id')
parser.add_argument('result', choices=('success', 'failure', 'escalated'))
parser.add_argument('tokens', nargs='?', type=int)
parser.add_argument('duration_s', nargs='?', type=float)
parser.add_argument('--no-rework', choices=('true', 'false'), help='Whether this attempt passed without any correction or retry')
parser.add_argument('--effective-candidate')
parser.add_argument('--resolved-model')
parser.add_argument('--effective-effort')
parser.add_argument('--host-confirmed', action='store_true')
parser.add_argument('--verification', choices=('passed', 'failed', 'unknown'))
parser.add_argument('--failure-kind', choices=KINDS)
parser.add_argument('--task-complete', choices=('true', 'false'))
parser.add_argument('--metric-source', default='host_report')
for name in ('input', 'output', 'reasoning', 'cache'):
    parser.add_argument(f'--{name}-tokens', type=int)
args = parser.parse_args()

decision_id = args.id
result = args.result
tokens = args.tokens
duration_s = args.duration_s
no_rework = None if args.no_rework is None else args.no_rework == 'true'
if tokens is not None and tokens < 0: parser.error('tokens must be nonnegative')
if duration_s is not None and (not math.isfinite(duration_s) or duration_s < 0): parser.error('duration_s must be nonnegative')
if no_rework and result != 'success': parser.error('--no-rework true requires success')
for name in ('input_tokens', 'output_tokens', 'reasoning_tokens', 'cache_tokens'):
    if getattr(args, name) is not None and getattr(args, name) < 0:
        parser.error(f'{name} must be nonnegative')
if args.reasoning_tokens is not None and args.output_tokens is not None and args.reasoning_tokens > args.output_tokens:
    parser.error('reasoning_tokens are a subset of output_tokens')
if args.cache_tokens is not None and args.input_tokens is not None and args.cache_tokens > args.input_tokens:
    parser.error('cache_tokens are a subset of input_tokens')
if tokens is None and args.input_tokens is not None and args.output_tokens is not None:
    tokens = args.input_tokens + args.output_tokens
if args.input_tokens is not None and args.output_tokens is not None and tokens != args.input_tokens + args.output_tokens:
    parser.error('tokens must equal input_tokens + output_tokens; do not double count reasoning/cache')
for name in ('effective_candidate', 'resolved_model', 'effective_effort', 'metric_source'):
    string(getattr(args, name), name, nullable=name != 'metric_source')
if not args.host_confirmed and any((args.effective_candidate, args.resolved_model, args.effective_effort)):
    parser.error('effective execution fields require --host-confirmed')
verification = args.verification or ('passed' if result == 'success' else 'failed')
if result == 'success' and verification != 'passed':
    parser.error('success requires passed verification')
if result == 'success' and args.failure_kind:
    parser.error('failure-kind is incompatible with success')
if args.task_complete == 'true' and result != 'success':
    parser.error('task completion requires verified success')
#-----------------------------------------------------------
# Check decision, justification and approval
#-----------------------------------------------------------
# without a logged justification there is no way to audit why the model was used
decision, events = decision_events(decision_id)
if decision.get('execution', {}).get('status') == 'blocked':
    raise ValueError('Decision is blocked; resolve the failure before recording execution')
if no_rework and (decision.get('attempt_count', 1) > 1 or decision.get('state', {}).get('failed_with')):
    raise ValueError('A retry cannot be marked as completed without rework')
if any(e['event'] == 'result' for e in events): raise ValueError(f'Decision {decision_id} already has a result; use feedback.py to correct its no-rework label')
answers = [e['answer'] for e in events if e['event'] == 'justification']
if not answers: raise ValueError(f'Decision {decision_id} has no justification. Run justify.py before delegating.')
if 'declined' in answers: raise ValueError(f"The user declined {decision['agent']} in decision {decision_id}; it cannot have a result. Route again with user_ceiling.")
if decision['needs_approval'] and 'approved' not in answers: raise ValueError(f"{decision['agent']} needs approval and decision {decision_id} has none logged.")
#-----------------------------------------------------------
# Log the result
#-----------------------------------------------------------
log_event({
    'event':      'result',
    'task_id': decision.get('task_id'),
    'decision_id': decision_id,
    'attempt_id': decision.get('attempt_id'),
    'intended_candidate': decision.get('selected', decision['agent']),
    'intended_model': decision.get('model'),
    'intended_effort': decision.get('effort'),
    'effective_candidate': args.effective_candidate if args.host_confirmed else None,
    'resolved_model': args.resolved_model if args.host_confirmed else None,
    'effective_effort': args.effective_effort if args.host_confirmed else None,
    'host_confirmed': args.host_confirmed,
    'verification': verification,
    'failure_kind': args.failure_kind or ('unknown' if result != 'success' else None),
    'task_complete': (result == 'success') if args.task_complete is None else args.task_complete == 'true',
    'attempt_count': decision.get('attempt_count'),
    'rework': None if no_rework is None else not no_rework,
    'backend': decision.get('backend'),
    'task_profile': decision.get('task_profile'),
    'metrics': {'total_tokens': tokens, 'input_tokens': args.input_tokens,
                'output_tokens': args.output_tokens, 'reasoning_tokens': args.reasoning_tokens,
                'cache_tokens': args.cache_tokens, 'source': args.metric_source, 'unit': 'tokens'},
    'duration_source': 'host_report' if duration_s is not None else None,
    'duration_unit': 'seconds',
    'id':         decision_id,
    'agent':      decision['agent'],
    'result':     result,
    'no_rework':  no_rework,
    'tokens':     tokens,
    'duration_s': duration_s,
})
print(f"Logged: {decision_id} {decision['agent']} {result}")
