"""Provider-neutral eligibility and transparent policy selection."""
from candidates import require


def needs_approval(candidate):
    return candidate['approval'] or candidate['billing_mode'] != 'subscription'


def eligible_candidates(state, config, diagnosis):
    catalog = config['ladder']
    lookup = {c['id']: c for c in catalog}
    lookup.update({c['agent']: c for c in catalog})
    ceiling = lookup.get(state.get('user_ceiling'))
    floor = lookup.get(state.get('user_floor'))
    if ceiling and floor:
        require(floor['consumption_tier'] <= ceiling['consumption_tier'], 'user_floor', 'exceeds user_ceiling')
    blocked = {lookup[i]['id'] for i in state.get('blocked_candidates', [])}
    allowed = {lookup[i]['id'] for i in state['allowed_candidates']} if 'allowed_candidates' in state else None
    failed = lookup.get(state.get('failed_with'))
    excluded, eligible = [], []
    for c in catalog:
        reasons = []
        r = c['restrictions']
        if not c['active']:
            reasons.append('inactive')
        if c['availability'] == 'unavailable':
            reasons.append('unavailable_model_or_effort')
        if c['billing_mode'] == 'external':
            reasons.append('external_billing_not_supported')
        if c['id'] in blocked or allowed is not None and c['id'] not in allowed:
            reasons.append('candidate_restricted')
        if not ({state['operation']} | set(state.get('required_capabilities', []))) <= set(c['capabilities']):
            reasons.append('missing_capability')
        if state['operation'] not in r.get('operations', [state['operation']]):
            reasons.append('operation_restricted')
        if state['files'] > r.get('max_files', 1000000):
            reasons.append('file_limit')
        if state['critical'] and not r.get('allow_critical', True):
            reasons.append('critical_restricted')
        if ceiling and c['consumption_tier'] > ceiling['consumption_tier']:
            reasons.append('user_ceiling')
        if floor and c['consumption_tier'] < floor['consumption_tier']:
            reasons.append('user_floor')
        if c['legacy_rank'] > config['ceiling_by_operation'].get(state['operation'], 10000):
            reasons.append('operation_ceiling')
        if c.get('escalation_only') and not failed and (not floor or c['id'] != floor['id']):
            reasons.append('escalation_only')
        if failed and diagnosis['retry_allowed']:
            if diagnosis['action'] in ('recover_same_candidate', 'fix_same_candidate') and c['id'] != failed['id']:
                reasons.append('recover_same_candidate')
            if diagnosis['kind'] in ('verification_failed', 'design_or_reasoning_failure', 'unavailable_model_or_effort') and c['id'] == failed['id']:
                reasons.append('failed_candidate')
        if reasons:
            excluded.append({'id': c['id'], 'reasons': reasons})
        else:
            eligible.append(c)
    return eligible, excluded


def fallback(state, config, eligible, baseline):
    """Legacy role/flags are only a conservative cold-start prior."""
    failed = next((c for c in config['ladder'] if state.get('failed_with') in (c['id'], c['agent'])), None)
    if failed and state.get('failure_kind') in ('verification_failed', 'design_or_reasoning_failure'):
        baseline = max(baseline, failed['legacy_rank'] + 1)
    return min(eligible, key=lambda c: (abs(c['legacy_rank']-baseline), c['legacy_rank']))


def select(state, config, eligible, evidence, baseline, scores=None):
    policy_name = state.get('policy', config['policy'])
    chosen = fallback(state, config, eligible, baseline)
    pool = eligible
    reasons = []
    if scores:
        above = [c for c in pool if scores[c['id']] >= config['success_threshold']]
        if above:
            pool = above
            chosen = fallback(state, config, pool, baseline)
            reasons.append('uncalibrated Laya score threshold used as transitional heuristic')
        else:
            reasons.append('no uncalibrated Laya score above threshold; heuristic decides')
    if policy_name == 'legacy':
        return chosen, reasons + ['legacy operation/flags fallback'], 'heuristic', None
    policy = config['policies'][policy_name]
    # Complete comparable coverage is required; a few lucky samples cannot dominate.
    enough = all(evidence[c['id']]['sufficient'] and
                 evidence[c['id']]['completion_tokens'] is not None and
                 evidence[c['id']]['completion_duration_s'] is not None for c in pool)
    comparable = len({(evidence[c['id']]['metric_source'], evidence[c['id']]['metric_unit']) for c in pool}) == 1
    if not enough or not comparable:
        return chosen, reasons + ['insufficient comparable completion evidence; conservative legacy role/flags fallback'], 'low', None
    reliable = [c for c in pool if (evidence[c['id']]['calibration'] or {'interval': evidence[c['id']]['success_interval']})['interval'][0] >= policy['min_reliability']]
    if not reliable:
        return chosen, reasons + ['reliability lower bounds below policy minimum; heuristic proposal requires verification'], 'low', None
    max_tokens = max(evidence[c['id']]['completion_tokens'] for c in reliable) or 1
    max_time = max(evidence[c['id']]['completion_duration_s'] for c in reliable) or 1
    objectives = {}
    for c in reliable:
        e = evidence[c['id']]
        objectives[c['id']] = (policy['tokens']*e['completion_tokens']/max_tokens +
                                policy['duration']*e['completion_duration_s']/max_time +
                                policy['failure']*(1-e['success_estimate']))
    chosen = min(reliable, key=lambda c: objectives[c['id']])
    reasons.append(f'{policy_name}: observed tokens and duration until completion, with verified reliability lower bound')
    return chosen, reasons, 'observational', objectives
