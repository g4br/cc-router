"""Validate a DAG and schedule dependency-safe native execution waves."""
from pathlib import Path
from candidates import require


def paths(state, kind):
    root = Path(state.get('project_root', '.')).resolve()
    values = state.get('write_targets', state.get('targets', [])) if kind == 'write' else state.get('read_targets', [])
    return [(root / value).resolve() for value in values]


def overlap(a, b):
    return a == b or a in b.parents or b in a.parents


def conflicts(a, b):
    aw, bw = paths(a, 'write'), paths(b, 'write')
    ar, br = paths(a, 'read'), paths(b, 'read')
    return (any(overlap(x, y) for x in aw for y in bw + br)
            or any(overlap(x, y) for x in ar for y in bw)
            or bool(set(a.get('shared_resources', [])) & set(b.get('shared_resources', []))))


def plan(states, config):
    require(bool(states), 'batch', 'must not be empty')
    extended = any('step_id' in s or 'depends_on' in s or s.get('isolation') == 'sequential' for s in states)
    limit = min([config['max_parallel']] + [s.get('host_max_parallel', config['max_parallel']) for s in states])
    require(extended or len(states) <= limit, 'batch', 'exceeds max_parallel; split it or use an explicit DAG')
    ids = [s.get('step_id', f'step-{i+1}') for i, s in enumerate(states)]
    require(len(set(ids)) == len(ids), 'step_id', 'duplicate IDs')
    for state in states:
        require('targets' in state or 'write_targets' in state, 'targets', 'batch steps must declare writes; [] for read-only')
        if state.get('isolation') == 'worktree':
            require(config['host_config']['worktree'], 'isolation', 'worktree support not verified for this host')
    dependencies = {key: set(s.get('depends_on', [])) for key, s in zip(ids, states)}
    for key, deps in dependencies.items():
        require(deps <= set(ids) and key not in deps, 'depends_on', 'unknown dependency or self-cycle')
    remaining, ancestors = set(ids), {}
    while remaining:
        ready = [k for k in ids if k in remaining and dependencies[k] <= ancestors.keys()]
        require(bool(ready), 'depends_on', 'cycle detected')
        for key in ready:
            ancestors[key] = dependencies[key] | set().union(*(ancestors[d] for d in dependencies[key]))
            remaining.remove(key)
    for i, a in enumerate(states):
        for j in range(i+1, len(states)):
            b = states[j]
            ordered = ids[i] in ancestors[ids[j]] or ids[j] in ancestors[ids[i]]
            serial = a.get('isolation') == 'sequential' or b.get('isolation') == 'sequential'
            require(not conflicts(a, b) or ordered or serial, 'write_targets/shared_resources',
                    'conflict between independent steps; declare dependency or sequential isolation')
    waves, done, remaining = [], set(), set(ids)
    while remaining:
        ready = [k for k in ids if k in remaining and dependencies[k] <= done]
        wave = []
        for key in ready:
            state = states[ids.index(key)]
            if wave and (state.get('isolation') == 'sequential' or any(states[ids.index(k)].get('isolation') == 'sequential' for k in wave)):
                continue
            wave.append(key)
            if len(wave) == limit:
                break
        waves.append(wave)
        done.update(wave)
        remaining.difference_update(wave)
    return [{'step_id': key, 'depends_on': sorted(dependencies[key]),
             'wave': next(i for i, wave in enumerate(waves) if key in wave),
             'ready': not dependencies[key] and key in waves[0],
             'isolation': state.get('isolation', 'shared'),
             'isolation_applied': False, 'requires_integration_verification': True}
            for key, state in zip(ids, states)]


def verify_changes(states, changes):
    """Compare host-reported actual changes to declared ownership after execution."""
    ids = [s.get('step_id', f'step-{i+1}') for i, s in enumerate(states)]
    require(type(changes) is dict and set(changes) <= set(ids), 'actual_changes', 'unknown step')
    actual, unexpected, outside = {}, [], {}
    from candidates import strings
    for ident, state in zip(ids, states):
        values = changes.get(ident, [])
        strings(values, 'actual_changes')
        root = Path(state.get('project_root', '.')).resolve()
        actual[ident] = [(root / v).resolve() for v in values]
        declared = paths(state, 'write')
        out = [v for v, p in zip(values, actual[ident]) if not any(p == d or d in p.parents for d in declared)]
        if out:
            unexpected.append(ident)
            outside[ident] = out
    collisions = [{'steps': [a, b]} for i, a in enumerate(ids) for b in ids[i+1:]
                  if any(overlap(x, y) for x in actual[a] for y in actual[b])]
    return {'unexpected_steps': unexpected, 'outside_paths': outside, 'conflicts': collisions,
            'changes_report_complete': set(changes) == set(ids),
            'integration_verification_required': True}
