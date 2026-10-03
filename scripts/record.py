import argparse

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
args = parser.parse_args()

decision_id = args.id
result = args.result
tokens = args.tokens
duration_s = args.duration_s
no_rework = None if args.no_rework is None else args.no_rework == 'true'
if tokens is not None and tokens < 0: parser.error('tokens must be nonnegative')
if duration_s is not None and duration_s < 0: parser.error('duration_s must be nonnegative')
if no_rework and result != 'success': parser.error('--no-rework true requires success')
#-----------------------------------------------------------
# Check decision, justification and approval
#-----------------------------------------------------------
# without a logged justification there is no way to audit why the model was used
decision, events = decision_events(decision_id)
if no_rework and decision.get('state', {}).get('failed_with'):
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
    'id':         decision_id,
    'agent':      decision['agent'],
    'result':     result,
    'no_rework':  no_rework,
    'tokens':     tokens,
    'duration_s': duration_s,
})
print(f"Logged: {decision_id} {decision['agent']} {result}")
