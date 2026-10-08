import sys
import hashlib

from common import decision_events, log_event

#-----------------------------------------------------------
# Input and paths
#-----------------------------------------------------------
# auto: rung without approval; approved/declined: the user's answer to the question
valid_answers = ['auto', 'approved', 'declined']

if len(sys.argv) not in (3, 4): raise ValueError("usage: python justify.py <id> <auto|approved|declined> [justification]")

decision_id   = sys.argv[1]
answer        = sys.argv[2]
justification = sys.argv[3].strip() if len(sys.argv) == 4 else None

if answer not in valid_answers: raise ValueError(f"Invalid answer '{answer}'. Accepted: {valid_answers}")
if justification == '': raise ValueError('Empty justification')
#-----------------------------------------------------------
# Check the decision
#-----------------------------------------------------------
decision, events = decision_events(decision_id)
justification = justification or decision.get('reason') or 'Recorded selection policy'
if decision.get('execution', {}).get('status') == 'blocked':
    raise ValueError('Decision is blocked; resolve the failure and route again')
if any(e.get('answer') == 'declined' for e in events):
    raise ValueError('Decision was declined; route a new decision under the granted ceiling')
if decision['needs_approval'] and answer == 'auto': raise ValueError(f"{decision['agent']} needs the user's approval: ask first and record approved or declined")
#-----------------------------------------------------------
# Log the justification
#-----------------------------------------------------------
log_event({
    'event':         'justification',
    'id':            decision_id,
    'agent':         decision['agent'],
    'answer':        answer,
    'justification': justification if decision.get('schema_version', 1) < 2 else None,
    'justification_sha256': hashlib.sha256(justification.encode()).hexdigest(),
    'task_id': decision.get('task_id'),
    'decision_id': decision_id,
    'attempt_id': decision.get('attempt_id'),
})
print(f"Logged: {decision_id} {decision['agent']} {answer}")
