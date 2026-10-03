import sys

from common import decision_events, log_event

#-----------------------------------------------------------
# Input and paths
#-----------------------------------------------------------
# auto: rung without approval; approved/declined: the user's answer to the question
valid_answers = ['auto', 'approved', 'declined']

if len(sys.argv) != 4: raise ValueError("usage: python justify.py <id> <auto|approved|declined> '<justification>'")

decision_id   = sys.argv[1]
answer        = sys.argv[2]
justification = sys.argv[3].strip()

if answer not in valid_answers: raise ValueError(f"Invalid answer '{answer}'. Accepted: {valid_answers}")
if not justification: raise ValueError('Empty justification: say why this rung and why not the one below')
#-----------------------------------------------------------
# Check the decision
#-----------------------------------------------------------
decision, _ = decision_events(decision_id)
if decision['needs_approval'] and answer == 'auto': raise ValueError(f"{decision['agent']} needs the user's approval: ask first and record approved or declined")
#-----------------------------------------------------------
# Log the justification
#-----------------------------------------------------------
log_event({
    'event':         'justification',
    'id':            decision_id,
    'agent':         decision['agent'],
    'answer':        answer,
    'justification': justification,
})
print(f"Logged: {decision_id} {decision['agent']} {answer}")
