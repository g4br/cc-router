"""Laya difficulty mode: one choice question, asked in rotated option orders, one batch request.

laya-serve renders options in criteria key order. Key Lk always stands for level k; each
rotation lists the keys in a cyclic shift, so every level takes every slot once (K = 5) and
position bias averages out. All rotations of all tasks travel in ONE /batch request.
"""
import sys
import time

from candidates import require, number
from common import post_json

KEYS = ('L1', 'L2', 'L3', 'L4', 'L5')
MAX_STATES = 64   # laya-serve MAX_BATCH_STATES
MAX_WORDS = 60
SUM_TOLERANCE = 0.02


def rotation_name(r):
    return f'difficulty#r{r}'


def difficulty_state(state):
    # only the description and the operation reach Laya; flags and file counts stay with the heuristic
    words = state['description'].split()
    description = state['description']
    if len(words) > MAX_WORDS:
        print(f'cc-router: description truncated to {MAX_WORDS} words for Laya ({len(words)} words)', file=sys.stderr)
        description = ' '.join(words[:MAX_WORDS])
    return {'description': description, 'operation': state['operation']}


def questions(config):
    difficulty = config['laya_difficulty']
    texts = list(difficulty['levels'].values())
    n = len(texts)
    return {rotation_name(r): {'type': 'choice', 'instructions': difficulty['question'],
                               'criteria': {KEYS[(i + r) % n]: texts[(i + r) % n] for i in range(n)}}
            for r in range(config['laya_rotations'])}


def parse(result, config):
    names = list(config['laya_difficulty']['levels'])
    rotations = config['laya_rotations']
    totals = [0.0] * len(names)
    for r in range(rotations):
        probabilities = result['answers'][rotation_name(r)]['probabilities']
        require(set(probabilities) == set(KEYS), 'probabilities')
        values = [probabilities[key] for key in KEYS]
        for value in values:
            number(value, 'probability', 0, 1)
        require(abs(sum(values) - 1) <= SUM_TOLERANCE, 'probabilities', 'must sum to 1')
        totals = [t + v for t, v in zip(totals, values)]
    distribution = [t / rotations for t in totals]
    confidence = max(distribution)
    return {'level': names[distribution.index(confidence)],  # a tie goes to the lower level
            'distribution': dict(zip(names, distribution)),
            'answer_confidence': confidence,
            'expected_level': sum(i * p for i, p in enumerate(distribution)),
            'rotations': rotations}


def request(states, config):
    """One HTTP request for all states; returns one parsed answer per state, in order."""
    require(0 < len(states) <= MAX_STATES, 'batch', f'Laya difficulty mode accepts 1 to {MAX_STATES} tasks per request')
    body = {'states': [difficulty_state(s) for s in states], 'questions': questions(config), 'model': config['laya_checkpoint']}
    started = time.monotonic()
    try:
        # the timeout is per task: a 64-task batch with 5 rotations takes about 70 s on CPU (references/laya.md)
        response = post_json(config['laya_url'].rstrip('/') + '/batch', body, config['laya_timeout_s'] * len(states))
        elapsed = time.monotonic() - started
        results = response['results']
        require(type(results) is list and len(results) == len(states), 'results')
        answers = [parse(r, config) for r in results]
    except (KeyError, TypeError, ValueError):
        raise ValueError('laya response: invalid difficulty contract') from None
    for answer in answers:
        answer.update(batch_states=len(states), request_s=round(elapsed, 4))
    return answers


def combine(answer, heuristic_rank, state, config):
    """Laya level + heuristic rung -> preferred rung. Deterministic; every branch is recorded."""
    names = list(config['laya_difficulty']['levels'])
    ladder = {c['id']: c for c in config['ladder']}
    candidates = [ladder[config['level_to_candidate'][config['operator']][n]] for n in names]
    # heuristic rung -> level: the highest level whose candidate rung is <= the heuristic rung (level 0 if none)
    heuristic = max([i for i, c in enumerate(candidates) if c['legacy_rank'] <= heuristic_rank], default=0)
    laya = names.index(answer['level'])
    gap = laya - heuristic
    base = {'min_confidence': config['laya_min_confidence'],
            'min_confidence_calibrated': config['laya_min_confidence_calibrated'],
            'heuristic_level': names[heuristic]}
    applied = answer['answer_confidence'] >= config['laya_min_confidence'] and abs(gap) <= 1
    if answer['answer_confidence'] < config['laya_min_confidence']:
        combination, final = 'abstained', heuristic
    elif gap == 0:
        combination, final = 'agree', laya
    elif abs(gap) == 1:
        final = max(laya, heuristic) if state['critical'] else min(laya, heuristic)
        combination = 'differ by 1: higher (critical)' if state['critical'] else 'differ by 1: lower (not critical)'
    else:
        combination, final = 'conflict: heuristic used', heuristic
    # applied: the level's candidate becomes the preferred rung; otherwise the heuristic rung stays
    return dict(answer, **base, combination=combination, final_level=names[final],
                preferred=candidates[final]['id'] if applied else None,
                baseline=candidates[final]['legacy_rank'] if applied else heuristic_rank)
