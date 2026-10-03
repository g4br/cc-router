import sys

from common import decision_events, log_event

#-----------------------------------------------------------
# Input and paths
#-----------------------------------------------------------
valid_results = ['success', 'failure', 'escalated']

if len(sys.argv) < 3: raise ValueError('usage: python record.py <id> <success|failure|escalated> [tokens] [duration_s]')

decision_id = sys.argv[1]
result      = sys.argv[2]
tokens      = int(sys.argv[3]) if len(sys.argv) > 3 else None
duration_s  = float(sys.argv[4]) if len(sys.argv) > 4 else None

if result not in valid_results: raise ValueError(f"Invalid result '{result}'. Accepted: {valid_results}")
#-----------------------------------------------------------
# Check decision, justification and approval
#-----------------------------------------------------------
# without a logged justification there is no way to audit why the model was used
decision, events = decision_events(decision_id)
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
    'tokens':     tokens,
    'duration_s': duration_s,
})
print(f"Logged: {decision_id} {decision['agent']} {result}")
