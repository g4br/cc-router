"""Reproducible offline policy comparison. Synthetic observations, no model calls."""
import argparse
import json
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from candidates import for_host
from route import heuristic_level
from selection import select
from telemetry import estimates, profile

OPERATIONS = ('search', 'mechanical_edit', 'implementation', 'debugging', 'review', 'architecture')
CRITERIA = ('exact symbol locations', 'expected diff and formatter pass', 'roundtrip tests pass',
            'regression test passes', 'planted defect identified', 'dependency invariants pass')


def run():
    rows = []
    for host in ('claude', 'codex'):
        candidates = [{'id': ident, 'model': model, 'effort': effort, 'active': True,
                       'approval': False, 'billing_mode': 'subscription', 'capabilities': list(OPERATIONS),
                       'resolved_model': model + '-v1', 'legacy_rank': index}
                      for index, (ident, model, effort) in enumerate([
                          ('baseline', 'fixture-model-a', 'deep'), ('measured', 'fixture-model-b', None)])]
        config = for_host({'schema_version': 2, 'hosts': {host: {'candidates': candidates}}}, host)
        for operation, criterion in zip(OPERATIONS, CRITERIA):
            state = {'description': f'Offline reference: {operation}', 'operation': operation,
                     'files': 2, 'ambiguous': False, 'critical': False}
            events = []
            # Deliberately synthetic: costlier first attempts can have cheaper completion.
            for c in candidates:
                for i in range(40):
                    task = f'{c["id"]}-{i}'
                    retried = c['id'] == 'baseline' and i % 8 == 0
                    for attempt in range(2 if retried else 1):
                        ident = f'{task}-{attempt}'
                        success = not retried or attempt == 1
                        events.extend([
                            {'event': 'decision', 'id': ident, 'task_id': task, 'operator': host,
                             'task_profile': profile(state)},
                            {'event': 'result', 'id': ident, 'result': 'success' if success else 'failure',
                             'verification': 'passed' if success else 'failed', 'task_complete': success,
                             'no_rework': not retried, 'host_confirmed': True, 'effective_candidate': c['id'],
                             'resolved_model': c['resolved_model'], 'effective_effort': c['effort'],
                             'tokens': None, 'duration_s': 4 if c['id'] == 'baseline' else 3,
                             'metrics': {'total_tokens': 100 if c['id'] == 'baseline' else 105,
                                         'source': 'synthetic_fixture', 'unit': 'tokens'}}])
            baseline, _ = heuristic_level(state, config)
            evidence = estimates(events, state, candidates, config)
            for policy in ('legacy', 'economy', 'balanced', 'performance'):
                start = perf_counter()
                selected, reasons, confidence, _ = select(dict(state, policy=policy), config, candidates, evidence, baseline)
                elapsed = (perf_counter()-start)*1000
                e = evidence[selected['id']]
                retried_counts = [2 if selected['id'] == 'baseline' and i % 8 == 0 else 1 for i in range(40)]
                rows.append({'host': host, 'operation': operation, 'criterion': criterion, 'policy': policy,
                             'selected': selected['id'], 'confidence': confidence,
                             'completion_tokens': e['completion_tokens'], 'completion_duration_s': e['completion_duration_s'],
                             'first_attempt_rate': sum(n == 1 for n in retried_counts)/40, 'completion_rate': 1.,
                             'mean_attempts': mean(retried_counts), 'median_attempts': median(retried_counts),
                             'laya_fallbacks': 0, 'host_incompatibilities': 0, 'approval_required': False,
                             'write_conflicts': 0, 'test_regressions': None,
                             'selection_ms': round(elapsed, 4), 'reason': '; '.join(reasons)})
    assert len(rows) == 48
    assert all(row['selected'] == ('baseline' if row['policy'] == 'legacy' else 'measured') for row in rows)
    return {'schema_version': 2, 'source': 'synthetic_fixture_only',
            'real_model_runs': 0, 'api_calls': 0,
            'limitations': 'Synthetic replay demonstrates policy behavior, not real savings or model quality. Timing is local selector latency.',
            'rows': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = json.dumps(run(), indent=2) + '\n'
    if args.output:
        args.output.write_text(report)
    else:
        print(report, end='')
