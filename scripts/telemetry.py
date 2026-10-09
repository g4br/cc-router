"""Comparable attempt and completion metrics; tokens are never currency."""
import math
from statistics import mean, median


PHASES = ('planning', 'classification', 'delegation', 'execution', 'validation', 'rework')


def check_phase_tokens(values):
    """Optional per-phase tokens: only measured phases appear; an absent phase is unknown, never zero."""
    if type(values) is not dict or not values or not set(values) <= set(PHASES):
        raise ValueError(f'phase_tokens: expected a nonempty object over {PHASES}')
    for phase, value in values.items():
        if type(value) is not int or value < 0:
            raise ValueError(f'phase_tokens.{phase}: expected a nonnegative integer')
    return values


def profile(state, file_limit=3):
    return {'operation': state.get('operation'), 'files_bucket': 'many' if state.get('files', 0) > file_limit else str(state.get('files', 0)),
            'ambiguous': state.get('ambiguous'), 'critical': state.get('critical'),
            'context_class': state.get('context_class')}


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def interval(successes, n):
    """Wilson 95% interval; Laplace posterior mean is reported separately."""
    if not n:
        return [0., 1.]
    z = 1.96
    p = successes / n
    center = (p + z*z/(2*n)) / (1+z*z/n)
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1+z*z/n)
    return [max(0., center-half), min(1., center+half)]


def attempts(events):
    decisions = {e['id']: e for e in events if e.get('event') == 'decision'}
    feedback = {e['id']: e.get('no_rework') for e in events if e.get('event') == 'feedback'}
    seen, rows = set(), []
    for result in events:
        if result.get('event') != 'result' or result['id'] in seen or result['id'] not in decisions:
            continue
        seen.add(result['id'])
        decision = decisions[result['id']]
        verified = result.get('verification', 'passed' if result.get('result') == 'success' else 'failed')
        metrics = result.get('metrics') or {'total_tokens': result.get('tokens'), 'source': 'legacy_host_report', 'unit': 'tokens'}
        rows.append({'decision': decision, 'result': result,
                     'task_id': decision.get('task_id') or decision['id'],
                     'success': result.get('result') == 'success' and verified == 'passed',
                     'no_rework': feedback.get(result['id'], result.get('no_rework')),
                     'tokens': metrics.get('total_tokens'), 'duration_s': result.get('duration_s'),
                     'metric_source': metrics.get('source'), 'metric_unit': metrics.get('unit'),
                     'resolved_model': result.get('resolved_model'), 'effective_effort': result.get('effective_effort'),
                     'effective_candidate': result.get('effective_candidate'),
                     'operator': decision.get('operator'),
                     'host_confirmed': result.get('host_confirmed', False),
                     'profile': decision.get('task_profile') or profile(decision.get('state', {}))})
    return rows


def completions(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row['task_id'], []).append(row)
    summaries = []
    for task_id, group in grouped.items():
        finished = group[-1]['success'] and group[-1]['result'].get('task_complete', True)
        def total(key):
            return sum(r[key] for r in group) if all(numeric(r[key]) for r in group) else None
        units = {(r['operator'], r['metric_source'], r['metric_unit']) for r in group}
        models = {(r['effective_candidate'], r['resolved_model'], r['effective_effort']) for r in group}
        summaries.append({'task_id': task_id, 'completed': finished, 'attempts': len(group),
                          'rework': True if len(group) > 1 or any(r['no_rework'] is False for r in group) else (False if group[0]['no_rework'] is True else None),
                          'tokens': total('tokens') if len(units) == 1 else None,
                          'duration_s': total('duration_s'), 'first': group[0],
                          'execution_segments': len(models)})
    return summaries


def estimates(events, state, candidates, config, scores=None):
    rows = attempts(events)
    completed = completions(rows)
    task_profile = profile(state, config['file_limit'])
    out = {}
    for c in candidates:
        # Unknown resolved versions must not silently mix across alias upgrades.
        def matches(row):
            return (row['host_confirmed'] and c.get('resolved_model') is not None and row['operator'] == config['operator']
                    and row['profile'] == task_profile and row['effective_candidate'] == c['id']
                    and row['resolved_model'] == c['resolved_model'] and row['effective_effort'] == c['effort'])
        sample = [r for r in rows if matches(r)]
        successes = sum(r['success'] for r in sample)
        n = len(sample)
        result = {'samples': n, 'success_estimate': (successes+1)/(n+2) if n else None,
                  'success_interval': interval(successes, n), 'source': 'observed_verified_results',
                  'sufficient': n >= config['min_cost_samples'], 'completion_samples': 0,
                  'completion_tokens': None, 'completion_duration_s': None, 'metric_source': None,
                  'metric_unit': None, 'calibration': None}
        # Attribute total failure/retry/escalation consumption to the initial choice.
        tasks = [t for t in completed if t['completed'] and matches(t['first'])]
        result['completion_samples'] = len(tasks)
        token_tasks = [t for t in tasks if numeric(t['tokens'])]
        metric_groups = {(t['first']['metric_source'], t['first']['metric_unit']) for t in token_tasks}
        if len(token_tasks) >= config['min_cost_samples'] and len(metric_groups) == 1:
            result['completion_tokens'] = mean(t['tokens'] for t in token_tasks)
            result['metric_source'], result['metric_unit'] = next(iter(metric_groups))
        durations = [t['duration_s'] for t in tasks if numeric(t['duration_s'])]
        if len(durations) >= config['min_cost_samples']:
            result['completion_duration_s'] = mean(durations)
        if scores and c['id'] in scores:
            bucket = min(9, int(scores[c['id']] * 10))
            calibrated = [r for r in sample if numeric((r['decision'].get('scores') or {}).get(c['id']))
                          and min(9, int(r['decision']['scores'][c['id']] * 10)) == bucket
                          and r['no_rework'] is not None]
            if len(calibrated) >= config['min_calibration_samples']:
                good = sum(r['success'] and r['no_rework'] for r in calibrated)
                result['calibration'] = {'samples': len(calibrated), 'score_bin': bucket,
                                         'estimate': (good+1)/(len(calibrated)+2),
                                         'interval': interval(good, len(calibrated)),
                                         'source': 'observed_first_pass_outcomes'}
        out[c['id']] = result
    return out


def summarize(events):
    rows = attempts(events)
    tasks = completions(rows)
    done = [t for t in tasks if t['completed']]
    return {'attempts': len(rows), 'successes': sum(r['success'] for r in rows),
            'failures': sum(r['result'].get('result') == 'failure' for r in rows),
            'escalations': sum(r['result'].get('result') == 'escalated' for r in rows),
            'completed_tasks': len(done), 'tasks': len(tasks),
            'first_attempt_rate': sum(t['attempts'] == 1 and t['first']['no_rework'] is True for t in done)/len(tasks) if tasks and all(t['first']['no_rework'] is not None for t in tasks) else None,
            'completion_rate': len(done)/len(tasks) if tasks else None,
            'mean_attempts_to_completion': mean(t['attempts'] for t in done) if done else None,
            'median_attempts_to_completion': median(t['attempts'] for t in done) if done else None,
            'completion_details': [{k: v for k, v in t.items() if k != 'first'} for t in tasks]}


def workflow_efficiency(events, task_ids, validated, overhead):
    """All workflow tokens, including unfinished/failed attempts; unknown != zero.

    Overhead contains cumulative, disjoint host measurements. Retry execution is
    the rework phase; planning/delegation/validation for retries stay in their phase.
    """
    task_set = set(task_ids)
    decisions = {e['id']: e for e in events if e.get('event') == 'decision'
                 and e.get('task_id') in task_set and e.get('selected') is not None
                 and e.get('execution', {}).get('status') != 'blocked'}
    results = {e['id']: e for e in events if e.get('event') == 'result' and e['id'] in decisions}
    declined = {e['id'] for e in events if e.get('event') == 'justification' and e.get('answer') == 'declined'}
    phases = {**overhead, 'execution': 0, 'rework': 0}
    missing, known = [], sum(v for v in overhead.values() if numeric(v))
    missing.extend(k for k, v in overhead.items() if not numeric(v))
    for ident, decision in decisions.items():
        if ident in declined:
            continue
        phase = 'rework' if decision.get('attempt_count', 1) > 1 else 'execution'
        result = results.get(ident, {})
        metrics = result.get('metrics') or {}
        tokens = metrics.get('total_tokens', result.get('tokens'))
        if not numeric(tokens) or metrics.get('unit', 'tokens') != 'tokens':
            missing.append(ident)
            phases[phase] = None
        else:
            known += tokens
            if phases[phase] is not None:
                phases[phase] += tokens
    total = known if not missing else None
    return {'validated_tasks': validated, 'planned_tasks': len(task_ids), 'phase_tokens': phases,
            'known_tokens': known, 'total_tokens': total, 'missing_measurements': missing,
            'tasks_per_token': validated / total if total else None,
            'coverage_complete': not missing, 'source': 'host_report', 'unit': 'tokens'}


def segmented_report(events):
    rows = attempts(events)
    tasks = completions(rows)
    groups = {}
    for row in rows:
        key = (row['operator'], row['effective_candidate'], row['resolved_model'], row['effective_effort'],
               tuple(sorted(row['profile'].items())), row['metric_source'], row['metric_unit'])
        groups.setdefault(key, []).append(row)
    segments = []
    for key, group in groups.items():
        ids = {r['decision']['id'] for r in group}
        completed = [t for t in tasks if t['completed'] and t['first']['decision']['id'] in ids]
        def average(values):
            known = [v for v in values if numeric(v)]
            return {'samples': len(known), 'mean': mean(known) if known else None,
                    'median': median(known) if known else None}
        segments.append({'host': key[0], 'effective_candidate': key[1], 'resolved_model': key[2],
                         'effective_effort': key[3], 'profile': dict(key[4]), 'source': key[5], 'unit': key[6],
                         'attempts': len(group), 'successes': sum(r['success'] for r in group),
                         'failures': sum(r['result'].get('result') == 'failure' for r in group),
                         'escalations': sum(r['result'].get('result') == 'escalated' for r in group),
                         'completed_tasks': len(completed),
                         'attempt_tokens': average(r['tokens'] for r in group),
                         'completion_tokens': average(t['tokens'] for t in completed),
                         'completion_duration_s': average(t['duration_s'] for t in completed)})
    workflows = []
    starts = {e['id']: e for e in events if e.get('event') == 'workflow_started'}
    for run_id, start in starts.items():
        run_events = [e for e in events if e.get('run_id') == run_id]
        reports = [e for e in run_events if e.get('event') == 'workflow_usage']
        overhead = reports[-1]['overhead'] if reports else {
            key: None for key in ('planning', 'classification', 'delegation', 'validation')}
        done = {e['task_id'] for e in run_events if e.get('event') == 'task_completed'}
        workflows.append({'run_id': run_id, **workflow_efficiency(events, start['task_ids'], len(done), overhead)})
    # Mixed-model executions retain each native segment instead of attributing
    # the whole attempt to the intended candidate. This is a breakdown only;
    # attempt/workflow totals above already include these tokens exactly once.
    native = [{'decision_id': r['decision']['id'], 'host': r['operator'],
               'execution': r['result']['host_usage'], 'segments': r['result']['execution_segments']}
              for r in rows if r['result'].get('host_usage') and r['result'].get('execution_segments')]
    return {'summary': summarize(events), 'segments': segments, 'workflows': workflows,
            'native_executions': native}


if __name__ == '__main__':
    import json
    from common import detect_operator, history_path, read_history
    print(json.dumps(segmented_report(read_history(history_path(detect_operator()))), indent=2))
