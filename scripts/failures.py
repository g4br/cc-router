"""Explicit failure taxonomy. Free text never authorizes a retry."""
KINDS = ('transient_host', 'rate_limit', 'permission_denied', 'missing_context',
         'syntax_or_local_fix', 'verification_failed', 'design_or_reasoning_failure',
         'unavailable_model_or_effort', 'unknown')


def diagnose(state, config):
    kind = state.get('failure_kind')
    if not kind and not state.get('failed_with'):
        return {'kind': None, 'action': 'select', 'retry_allowed': False}
    kind = kind or 'unknown'
    actions = {'rate_limit': 'stop_or_reschedule', 'permission_denied': 'request_authorization',
               'missing_context': 'obtain_context', 'unknown': 'inspect_failure',
               'transient_host': 'recover_same_candidate', 'syntax_or_local_fix': 'fix_same_candidate',
               'verification_failed': 'reassess_candidates', 'design_or_reasoning_failure': 'reassess_strategy',
               'unavailable_model_or_effort': 'exclude_unavailable_candidate'}
    action = actions[kind]
    allowed = kind in ('transient_host', 'syntax_or_local_fix', 'verification_failed',
                       'design_or_reasoning_failure', 'unavailable_model_or_effort')
    if kind in ('rate_limit', 'permission_denied', 'missing_context') and state.get('recovery_confirmed', False):
        allowed, action = True, 'recover_same_candidate'
    if state.get('attempt_count', 1) >= config['max_attempts']:
        allowed, action = False, 'attempt_limit_reached'
    elif allowed and not state.get('idempotent', False) and not state.get('retry_approved', False):
        allowed, action = False, 'approve_non_idempotent_retry'
    elif allowed and not state.get('diff_verified', False):
        allowed, action = False, 'inspect_worktree_diff'
    return {'kind': kind, 'action': action, 'retry_allowed': allowed}
