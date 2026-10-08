"""Check actual changed files reported by native agents, before integration tests."""
import argparse
import json
from pathlib import Path
from common import load_config
from state import check_state
from planning import plan, verify_changes

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('states', type=Path)
parser.add_argument('changes', type=Path, help='JSON object mapping step IDs to actual changed paths')
args = parser.parse_args()
config = load_config()
states = json.loads(args.states.read_text())
for state in states:
    check_state(state, config)
plan(states, config)
report = verify_changes(states, json.loads(args.changes.read_text()))
print(json.dumps(report))
raise SystemExit(1 if report['unexpected_steps'] or report['conflicts'] or not report['changes_report_complete'] else 0)
