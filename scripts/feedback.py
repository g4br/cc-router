"""Correct the no-rework outcome after a result has been recorded."""
import argparse

from common import decision_events, log_event

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('id')
parser.add_argument('no_rework', choices=('true', 'false'))
args = parser.parse_args()

decision, events = decision_events(args.id)
results = [event for event in events if event['event'] == 'result']
if len(results) != 1:
    raise ValueError(f'Decision {args.id} needs exactly one recorded result before feedback')
if args.no_rework == 'true' and results[0]['result'] != 'success':
    raise ValueError('A failed or escalated attempt cannot be marked as no-rework')
if args.no_rework == 'true' and (decision.get('attempt_count', 1) > 1 or decision.get('state', {}).get('failed_with')):
    raise ValueError('A retry cannot be marked as completed without rework')

log_event({
    'event': 'feedback',
    'task_id': decision.get('task_id'),
    'decision_id': args.id,
    'attempt_id': decision.get('attempt_id'),
    'id': args.id,
    'agent': decision['agent'],
    'no_rework': args.no_rework == 'true',
})
print(f'Feedback: {args.id} no_rework={args.no_rework}')
