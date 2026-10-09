"""Strict public task-state validation. Error messages contain field names only."""
from pathlib import Path
from candidates import require, string, strings, number
from failures import KINDS


def check_state(state, config):
    require(type(state) is dict, 'state', 'expected object')
    required = {'description', 'operation', 'files', 'ambiguous', 'critical'}
    require(required <= state.keys(), 'state', 'missing required fields')
    known = required | {'user_language', 'failed_with', 'user_floor', 'user_ceiling', 'targets',
        'policy', 'task_id', 'attempt_count', 'failure_kind', 'idempotent', 'retry_approved',
        'diff_verified', 'blocked_candidates', 'allowed_candidates', 'required_capabilities',
        'recovery_confirmed', 'context_class', 'step_id', 'depends_on', 'read_targets', 'write_targets', 'shared_resources',
        'isolation', 'project_root', 'outside_root_approved', 'host_max_parallel', 'same_level_retries'}
    require(set(state) <= known, 'state', 'unknown fields')
    string(state['description'], 'description', 8000)
    string(state['operation'], 'operation', 100)
    require(state['operation'] in config['base_level_by_operation'], 'operation', 'unsupported operation')
    number(state['files'], 'files', 0, 1000000, True)
    for key in ('ambiguous', 'critical', 'idempotent', 'retry_approved', 'diff_verified', 'outside_root_approved', 'recovery_confirmed'):
        if key in state:
            require(type(state[key]) is bool, key, 'expected boolean')
    for key in ('user_language', 'task_id', 'context_class', 'step_id'):
        if key in state:
            string(state[key], key, 128)
    candidates = {c['id']: c for c in config['ladder']}
    candidates.update({c['agent']: c for c in config['ladder']})
    for key in ('failed_with', 'user_floor', 'user_ceiling'):
        if state.get(key) is not None:
            string(state[key], key)
            require(state[key] in candidates, key, 'unknown candidate')
            require(candidates[state[key]]['active'], key, 'inactive candidate')
    for key in ('blocked_candidates', 'allowed_candidates', 'required_capabilities', 'targets',
                'read_targets', 'write_targets', 'shared_resources', 'depends_on'):
        if key in state:
            strings(state[key], key)
    for key in ('blocked_candidates', 'allowed_candidates'):
        if key in state:
            require(all(c in candidates for c in state[key]), key, 'unknown candidate')
    if 'allowed_candidates' in state:
        require(bool(state['allowed_candidates']), 'allowed_candidates', 'empty allowlist')
    if 'attempt_count' in state:
        number(state['attempt_count'], 'attempt_count', 1, 10000, True)
    if 'same_level_retries' in state:
        number(state['same_level_retries'], 'same_level_retries', 0, 10000, True)
    if 'host_max_parallel' in state:
        number(state['host_max_parallel'], 'host_max_parallel', 1, 10000, True)
    if 'policy' in state:
        require(type(state['policy']) is str and state['policy'] in (*config['policies'], 'legacy'), 'policy')
    if 'failure_kind' in state:
        require(type(state['failure_kind']) is str and state['failure_kind'] in KINDS, 'failure_kind')
        require(bool(state.get('failed_with')), 'failed_with', 'required for failure diagnosis')
    if 'isolation' in state:
        require(type(state['isolation']) is str and state['isolation'] in ('shared', 'sequential', 'worktree'), 'isolation')
        require(state['isolation'] != 'worktree' or config['host_config']['worktree'], 'isolation', 'worktree support not verified for this host')
    if 'project_root' in state:
        string(state['project_root'], 'project_root', 4096)
    if 'targets' in state and 'write_targets' in state:
        require(state['targets'] == state['write_targets'], 'targets', 'alias conflicts with write_targets')
    root = Path(state.get('project_root', '.')).resolve()
    require(root.is_dir(), 'project_root', 'directory does not exist')
    for key in ('targets', 'write_targets', 'read_targets'):
        for target in state.get(key, []):
            path = (root / target).resolve()
            require(not any(c in target for c in '*?[]'), key, 'use literal paths, not globs')
            if key != 'read_targets':
                require(path == root or root in path.parents or state.get('outside_root_approved', False),
                        key, 'write outside project_root requires approval')
