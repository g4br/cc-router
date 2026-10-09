"""Versioned configuration, legacy migration and host capability contracts.

Model and effort strings are opaque data. No provider inference belongs here.
"""
import copy
import math
import re
from urllib.parse import urlsplit

OPERATIONS = ('read', 'search', 'mechanical_edit', 'tweak', 'implementation', 'writing',
              'data_analysis', 'debugging', 'review', 'architecture', 'long_task',
              'research', 'security', 'investigation')
POLICIES = {
    'economy': {'min_reliability': .7, 'tokens': .8, 'duration': .1, 'failure': .1},
    'balanced': {'min_reliability': .7, 'tokens': .4, 'duration': .2, 'failure': .4},
    'performance': {'min_reliability': .7, 'tokens': .1, 'duration': .3, 'failure': .6},
}
DIFFICULTY = {
    'question': 'How demanding is this task for an AI coding agent?',
    'levels': {
        'trivial': 'single read, lookup or format conversion with a checkable output',
        'mechanical': 'pattern-following edit or small script with a test to run',
        'routine': 'day-to-day coding with a clear scope',
        'complex': 'several modules, design judgment or a non-local cause',
        'open': 'long, ambiguous or autonomous work where errors are costly',
    },
}
LEVEL_TO_CANDIDATE = {
    'claude': dict(zip(DIFFICULTY['levels'], ('exec-haiku-low', 'exec-haiku-high', 'exec-sonnet-medium', 'exec-opus-medium', 'exec-opus-high'))),
    'codex': dict(zip(DIFFICULTY['levels'], ('exec-luna-low', 'exec-sol-low', 'exec-sol-medium', 'exec-astra-medium', 'exec-astra-high'))),
}


def require(ok, field, message='invalid value'):
    if not ok:
        raise ValueError(f'{field}: {message}')


def string(value, field, maximum=200, nullable=False):
    require(nullable and value is None or type(value) is str and 0 < len(value.strip()) <= maximum
            and '\x00' not in value, field, 'expected nonempty bounded string' + (' or null' if nullable else ''))


def number(value, field, low=0, high=1e12, integer=False):
    require(type(value) is int if integer else type(value) in (int, float), field, 'invalid numeric type')
    require(math.isfinite(value) and low <= value <= high, field, 'out of range')


def strings(value, field):
    require(type(value) is list and len(value) <= 10000, field, 'expected list')
    for item in value:
        string(item, field, 4096)
    require(len(set(value)) == len(value), field, 'duplicates')


def migrate(raw):
    """Pure deterministic migration; retain custom fields and original ladders."""
    require(type(raw) is dict and bool(raw), 'config', 'expected nonempty object')
    version = raw.get('schema_version', 1)
    require(type(version) is int and version in (1, 2), 'schema_version', 'unsupported version')
    if version == 2:
        return copy.deepcopy(raw)
    require(type(raw.get('ladders')) is dict and bool(raw['ladders']), 'ladders')
    out = copy.deepcopy(raw)
    out['schema_version'] = 2
    out['hosts'] = {}
    for host, ladder in raw['ladders'].items():
        require(type(ladder) is list and bool(ladder), f'ladders.{host}')
        candidates = []
        for index, rung in enumerate(ladder):
            require(type(rung) is dict, f'ladders.{host}.candidate')
            require(all(k in rung for k in ('agent', 'model', 'effort', 'active', 'approval', 'suited_for')), f'ladders.{host}.candidate', 'missing required fields')
            candidates.append(dict(rung, id=rung['agent'], billing_mode=rung.get('billing_mode', 'subscription' if rung['active'] else 'unknown'),
                                   capabilities=rung.get('capabilities', list(OPERATIONS)),
                                   legacy_rank=index, consumption_tier=rung.get('consumption_tier', index),
                                   availability=rung.get('availability', 'unverified')))
        base = raw.get('base_level_by_operation', {}).get(host)
        require(type(base) is dict and bool(base), f'base_level_by_operation.{host}')
        out['hosts'][host] = {'candidates': candidates, 'base_level_by_operation': base,
                              'ceiling_by_operation': raw.get('ceiling_by_operation', {}).get(host, {}),
                              'capability_source': 'legacy configuration; host confirmation required',
                              'execution': 'native', 'worktree': False}
    out['migration'] = {'source_schema': 1, 'availability_verified': False}
    return out


def validate_config(raw):
    config = migrate(raw)
    require(type(config.get('hosts')) is dict and bool(config['hosts']), 'hosts')
    config.setdefault('backend', 'heuristic')
    require(config['backend'] in ('heuristic', 'laya'), 'backend')
    config.setdefault('policy', 'balanced')
    require(config['policy'] in (*POLICIES, 'legacy'), 'policy')
    for key, default, low in [('file_limit', 3, 0), ('max_parallel', 8, 1), ('max_attempts', 3, 1),
                              ('escalation_jump', 2, 1), ('min_cost_samples', 20, 2), ('min_calibration_samples', 20, 2)]:
        config.setdefault(key, default)
        number(config[key], key, low, 10000, True)
    config.setdefault('success_threshold', .8)
    number(config['success_threshold'], 'success_threshold', 0, 1)
    config.setdefault('laya_timeout_s', 30)
    number(config['laya_timeout_s'], 'laya_timeout_s', .01, 300)
    config.setdefault('laya_url', 'http://127.0.0.1:8001/v1/systemone')
    config.setdefault('laya_urls', {})
    require(type(config['laya_urls']) is dict, 'laya_urls')
    for url in [config['laya_url'], *config['laya_urls'].values()]:
        string(url, 'laya_url', 2000)
        parts = urlsplit(url)
        require(parts.scheme == 'http' and parts.hostname in ('127.0.0.1', '::1', 'localhost')
                and not parts.username and not parts.password and not parts.query and not parts.fragment,
                'laya_url', 'only local HTTP service is permitted')
        try:
            require(parts.port is not None and 0 < parts.port < 65536, 'laya_url.port')
        except ValueError:
            raise ValueError('laya_url.port: invalid port') from None
    config.setdefault('laya_enabled_operators', list(config['hosts']))
    strings(config['laya_enabled_operators'], 'laya_enabled_operators')
    require(set(config['laya_enabled_operators']) <= {'claude', 'codex'}, 'laya_enabled_operators')
    config.setdefault('laya_checkpoint', 'english')
    string(config['laya_checkpoint'], 'laya_checkpoint')
    config.setdefault('laya_question', 'Is this profile suited to completing the task without rework? {suited_for}')
    string(config['laya_question'], 'laya_question', 4000)
    try:
        config['laya_question'].format(label='profile', suited_for='capabilities')
    except (KeyError, ValueError, IndexError, AttributeError):
        raise ValueError('laya_question: unsupported format fields') from None
    config.setdefault('laya_criteria', {'A': 'yes', 'B': 'no'})
    require(type(config['laya_criteria']) is dict and set(config['laya_criteria']) == {'A', 'B'}, 'laya_criteria')
    for value in config['laya_criteria'].values():
        string(value, 'laya_criteria', 2000)
    config.setdefault('laya_mode', 'per_candidate')
    require(config['laya_mode'] in ('per_candidate', 'difficulty'), 'laya_mode')
    config.setdefault('laya_difficulty', copy.deepcopy(DIFFICULTY))
    difficulty = config['laya_difficulty']
    require(type(difficulty) is dict and set(difficulty) == {'question', 'levels'}, 'laya_difficulty')
    string(difficulty['question'], 'laya_difficulty.question', 2000)
    require(type(difficulty['levels']) is dict and len(difficulty['levels']) == 5, 'laya_difficulty.levels', 'expected exactly 5 ordered levels')
    for name, text in difficulty['levels'].items():
        string(name, 'laya_difficulty.levels', 64)
        string(text, f'laya_difficulty.levels.{name}', 2000)
    config.setdefault('laya_rotations', 5)
    number(config['laya_rotations'], 'laya_rotations', 1, 5, True)
    config.setdefault('laya_min_confidence', .5)
    number(config['laya_min_confidence'], 'laya_min_confidence', 0, 1)
    config.setdefault('laya_min_confidence_calibrated', False)
    require(type(config['laya_min_confidence_calibrated']) is bool, 'laya_min_confidence_calibrated')
    for key, default in [('gate_token_saving_min', .10), ('gate_under_routing_max_increase', .02)]:
        config.setdefault(key, default)
        number(config[key], key, 0, 1)
    config.setdefault('gate_min_tasks_per_level', 10)
    number(config['gate_min_tasks_per_level'], 'gate_min_tasks_per_level', 1, 100000, True)
    config.setdefault('agent_skills', [])
    strings(config['agent_skills'], 'agent_skills')
    policies = copy.deepcopy(POLICIES)
    require(type(config.get('policies', {})) is dict, 'policies')
    for name, policy in config.get('policies', {}).items():
        require(name in policies and type(policy) is dict, 'policies')
        require(set(policy) <= set(policies[name]), f'policies.{name}')
        policies[name].update(policy)
    for name, policy in policies.items():
        for key, value in policy.items():
            number(value, f'policies.{name}.{key}', 0, 1)
        require(sum(policy[k] for k in ('tokens', 'duration', 'failure')) > 0, f'policies.{name}')
    config['policies'] = policies
    for host, data in config['hosts'].items():
        require(host in ('claude', 'codex'), 'hosts', 'unsupported host adapter')
        require(type(data) is dict, f'hosts.{host}')
        require(data.get('execution', 'native') == 'native', f'hosts.{host}.execution', 'only native execution supported')
        data.setdefault('capability_source', 'configuration; host confirmation required')
        string(data['capability_source'], f'hosts.{host}.capability_source', 500)
        data.setdefault('worktree', False)
        require(type(data['worktree']) is bool, f'hosts.{host}.worktree')
        if 'max_parallel' in data:
            number(data['max_parallel'], f'hosts.{host}.max_parallel', 1, 10000, True)
        candidates = data.get('candidates')
        require(type(candidates) is list and bool(candidates), f'hosts.{host}.candidates')
        ids, agents, aliases = set(), set(), {}
        for index, c in enumerate(candidates):
            field = f'hosts.{host}.candidates[{index}]'
            require(type(c) is dict, field)
            for key in ('id', 'model'):
                string(c.get(key), f'{field}.{key}')
            require(re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}', c['id']) is not None, f'{field}.id')
            require(c['id'] not in ids, f'{field}.id', 'duplicate ID')
            ids.add(c['id'])
            c.setdefault('agent', c['id'])
            require(type(c['agent']) is str and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}', c['agent']) is not None, f'{field}.agent')
            require(c['agent'] not in agents, f'{field}.agent', 'duplicate agent')
            agents.add(c['agent'])
            for alias in (c['id'], c['agent']):
                require(alias not in aliases or aliases[alias] == c['id'], f'{field}.agent', 'ambiguous ID/agent alias')
                aliases[alias] = c['id']
            require(re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_./:@+-]*', c['model']) is not None, f'{field}.model', 'invalid host model identifier')
            c.setdefault('effort', None)
            string(c['effort'], f'{field}.effort', nullable=True)
            require(c['effort'] is None or re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', c['effort']) is not None, f'{field}.effort')
            for key in ('active', 'approval'):
                require(type(c.get(key)) is bool, f'{field}.{key}', 'expected boolean')
            require(c.get('billing_mode') in ('subscription', 'external', 'unknown'), f'{field}.billing_mode')
            strings(c.get('capabilities'), f'{field}.capabilities')
            c.setdefault('suited_for', ', '.join(c['capabilities']))
            string(c['suited_for'], f'{field}.suited_for', 4000)
            c.setdefault('label', c['id'])
            string(c['label'], f'{field}.label', 300)
            c.setdefault('availability', 'unverified')
            require(c['availability'] in ('unverified', 'supported', 'unavailable'), f'{field}.availability')
            c.setdefault('restrictions', {})
            require(type(c['restrictions']) is dict and set(c['restrictions']) <= {'operations', 'max_files', 'allow_critical'}, f'{field}.restrictions')
            r = c['restrictions']
            if 'operations' in r:
                strings(r['operations'], f'{field}.restrictions.operations')
                require(set(r['operations']) <= set(OPERATIONS), f'{field}.restrictions.operations')
            if 'max_files' in r:
                number(r['max_files'], f'{field}.restrictions.max_files', 0, 1000000, True)
            if 'allow_critical' in r:
                require(type(r['allow_critical']) is bool, f'{field}.restrictions.allow_critical')
            for key in ('legacy_rank', 'consumption_tier'):
                c.setdefault(key, index if key == 'legacy_rank' else 0)
                number(c[key], f'{field}.{key}', 0, 10000, True)
            if 'escalation_only' in c:
                require(type(c['escalation_only']) is bool, f'{field}.escalation_only')
            if 'skills' in c:
                strings(c['skills'], f'{field}.skills')
            string(c.get('resolved_model'), f'{field}.resolved_model', nullable=True)
            supported = data.get('supported_combinations')
            if supported is not None:
                require(type(supported) is list, f'hosts.{host}.supported_combinations')
                for pair in supported:
                    require(type(pair) is dict and set(pair) == {'model', 'effort'}, f'hosts.{host}.supported_combinations')
                    string(pair['model'], 'supported_combinations.model')
                    string(pair['effort'], 'supported_combinations.effort', nullable=True)
                require(not c['active'] or c['availability'] == 'unavailable' or {'model': c['model'], 'effort': c['effort']} in supported,
                        f'{field}.effort', 'active combination unsupported by configured host capabilities')
        require(any(c['active'] for c in candidates), f'hosts.{host}.candidates', 'no active candidates')
        base = data.setdefault('base_level_by_operation', {op: 0 for op in OPERATIONS})
        require(type(base) is dict and bool(base) and set(base) <= set(OPERATIONS), f'hosts.{host}.base_level_by_operation')
        ceilings = data.setdefault('ceiling_by_operation', {})
        require(type(ceilings) is dict and set(ceilings) <= set(base), f'hosts.{host}.ceiling_by_operation')
        for key, table in [('base_level_by_operation', base), ('ceiling_by_operation', ceilings)]:
            for value in table.values():
                number(value, f'hosts.{host}.{key}', 0, 10000, True)
    # fallback for scripts/eval_difficulty.py when history has no tokens for a candidate; null = unknown
    expected = config.setdefault('expected_tokens_by_candidate', {})
    require(type(expected) is dict and set(expected) <= set(config['hosts']), 'expected_tokens_by_candidate', 'unknown host')
    for host, table in expected.items():
        require(type(table) is dict, f'expected_tokens_by_candidate.{host}')
        for name, value in table.items():
            if value is not None:
                number(value, f'expected_tokens_by_candidate.{host}.{name}', 1, 1e9)
    levels = list(difficulty['levels'])
    mapping = config.setdefault('level_to_candidate', {})
    require(type(mapping) is dict and set(mapping) <= set(config['hosts']), 'level_to_candidate', 'unknown host')
    for host, data in config['hosts'].items():
        ids = {c['id']: c for c in data['candidates']}
        ids.update({c['agent']: c for c in data['candidates']})
        default = LEVEL_TO_CANDIDATE.get(host)
        if host not in mapping and default and set(default.values()) <= set(ids) and levels == list(default):
            mapping[host] = dict(default)
        if host not in mapping:
            require(config['laya_mode'] != 'difficulty' or host not in config['laya_enabled_operators'],
                    f'level_to_candidate.{host}', 'required for difficulty mode')
            continue
        field = f'level_to_candidate.{host}'
        require(type(mapping[host]) is dict and list(mapping[host]) == levels, field, 'expected one candidate per level, in level order')
        for level, name in mapping[host].items():
            require(type(name) is str and name in ids, f'{field}.{level}', 'not a candidate on this host ladder')
            mapping[host][level] = ids[name]['id']
        ranks = [ids[name]['legacy_rank'] for name in mapping[host].values()]
        require(ranks == sorted(ranks), field, 'candidate rungs must not decrease with difficulty')
    return config


def for_host(raw, host):
    config = validate_config(raw)
    require(host in config['hosts'], 'operator', 'host missing from configuration; no cross-host fallback')
    data = config['hosts'][host]
    config.update(operator=host, ladder=data['candidates'], host_config=data,
                  base_level_by_operation=data['base_level_by_operation'],
                  ceiling_by_operation=data['ceiling_by_operation'])
    config['laya_url'] = config['laya_urls'].get(host, config['laya_url'])
    config['max_parallel'] = min(config['max_parallel'], data.get('max_parallel', config['max_parallel']))
    return config
