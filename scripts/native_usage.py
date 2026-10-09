"""Read host usage, never infer it from the routing proposal or assistant prose.

Local rollout/transcript formats are versioned by their hosts, not a public stable
API. Unknown or ambiguous scopes fail closed. Nothing here executes an agent.
"""
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

from candidates import require, string

MARKER = re.compile(r'(?<![A-Z_])(?:CC_ROUTER_DECISION|DECISION):\s*([a-zA-Z0-9_-]+)\b')
TOKEN_KEYS = ('input_tokens', 'output_tokens', 'reasoning_tokens', 'cache_tokens', 'cache_write_tokens')


def count(value, field):
    require(value is None or type(value) is int and value >= 0, field, 'expected nonnegative integer or null')
    return value


def metrics(usage, host):
    require(type(usage) is dict, 'usage', 'expected object')
    inp = count(usage.get('input_tokens'), 'input_tokens')
    out = count(usage.get('output_tokens'), 'output_tokens')
    cache = count(usage.get('cache_read_input_tokens' if host == 'claude' else 'cached_input_tokens'), 'cache_tokens')
    write = count(usage.get('cache_creation_input_tokens' if host == 'claude' else 'cache_write_input_tokens'), 'cache_write_tokens')
    reasoning = count(usage.get('reasoning_output_tokens'), 'reasoning_tokens')
    # Claude's input_tokens excludes BOTH cache reads and writes. Missing fields
    # are unknown: silently treating an omitted cache counter as zero undercounts.
    if host == 'claude':
        inp = inp + cache + write if all(v is not None for v in (inp, cache, write)) else None
    require(out is None or reasoning is None or reasoning <= out, 'reasoning_tokens', 'exceeds output')
    require(inp is None or cache is None or cache <= inp, 'cache_tokens', 'exceeds input')
    require(inp is None or write is None or write <= inp, 'cache_write_tokens', 'exceeds input')
    total = inp + out if inp is not None and out is not None else None
    reported = count(usage.get('total_tokens'), 'total_tokens')
    require(reported is None or total is None or reported == total, 'total_tokens', 'inconsistent host counters')
    return dict(input_tokens=inp, output_tokens=out, reasoning_tokens=reasoning,
                cache_tokens=cache, cache_write_tokens=write, total_tokens=total)


def add_metrics(items):
    return {key: sum(item[key] for item in items) if items and all(item[key] is not None for item in items) else None
            for key in (*TOKEN_KEYS, 'total_tokens')}


def text_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(item.get('text', '') for item in content
                         if isinstance(item, dict) and item.get('type') in ('text', 'input_text'))
    return ''


def markers(text):
    return set(MARKER.findall(text))


def seconds(start, end):
    try:
        value = (datetime.fromisoformat(end.replace('Z', '+00:00')) -
                 datetime.fromisoformat(start.replace('Z', '+00:00'))).total_seconds()
        return value if value >= 0 else None
    except (ValueError, TypeError, AttributeError):
        return None


def identifier(value, field):
    string(value, field, 128)
    require(re.fullmatch(r'[a-zA-Z0-9_-]+', value) is not None, field, 'invalid native identifier')
    return value


def locate(host, agent_id):
    identifier(agent_id, 'agent_id')
    if host == 'codex':
        root = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))
        files = [p for folder in ('sessions', 'archived_sessions')
                 for p in (root / folder).rglob(f'*{agent_id}.jsonl')]
    else:
        root = Path(os.environ.get('CLAUDE_CONFIG_DIR', Path.home() / '.claude'))
        files = list((root / 'projects').rglob(f'agent-{agent_id}.jsonl'))
    require(len(files) == 1, 'transcript', 'expected one native transcript; provide --transcript explicitly')
    return files[0]


def read_transcript(path):
    raw = Path(path).read_bytes()
    require(bool(raw) and raw.endswith(b'\n'), 'transcript', 'empty or incomplete JSONL; wait for the host to flush')
    try:
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    except (ValueError, UnicodeError):
        raise ValueError('transcript: invalid JSONL; no usage recorded') from None
    require(all(type(row) is dict for row in rows), 'transcript', 'expected JSON objects')
    return rows, hashlib.sha256(raw).hexdigest()


def codex(rows, agent_id, decision_id, turn_id=None):
    metas = [r['payload'] for r in rows if r.get('type') == 'session_meta']
    require(len(metas) == 1 and metas[0].get('id') == agent_id, 'agent_id', 'Codex thread identity mismatch')
    source = metas[0].get('source')
    require(isinstance(source, dict) and 'subagent' in source, 'transcript', 'expected a dedicated Codex subagent')
    turns, current = {}, None
    for row in rows:
        p = row.get('payload', {})
        kind = p.get('type') if row.get('type') == 'event_msg' else row.get('type')
        if kind in ('task_started', 'turn_context'):
            current = p.get('turn_id')
            require(bool(current), 'turn_id', 'missing Codex turn identity')
            turns.setdefault(current, [])
        # Native usage carries its own turn ID; do not assign another agent's use
        # to the current turn just because it occurs nearby in the log.
        target = p.get('turn_id', current) if kind == 'token_usage_record' else current
        if target is not None:
            turns.setdefault(target, []).append(row)
    def decisions(events):
        found = set()
        for row in events:
            p = row.get('payload', {})
            if row.get('type') == 'event_msg' and p.get('type') == 'user_message':
                found |= markers(p.get('message', ''))
            elif row.get('type') == 'response_item' and p.get('role') == 'user':
                found |= markers(text_content(p.get('content')))
        return found
    matching = [key for key, value in turns.items() if decisions(value) == {decision_id}]
    if turn_id is None:
        require(len(matching) == 1, 'turn_id', 'expected one turn containing the decision marker; provide --turn-id')
        turn_id = matching[0]
    require(turn_id in matching, 'decision_id', 'decision marker missing or ambiguous in the requested Codex turn')
    events = turns[turn_id]
    require(not any(r.get('payload', {}).get('type') == 'model_rerouted' for r in events),
            'model', 'host reported a reroute; per-response model attribution is required')
    endings = [r for r in events if r.get('type') == 'event_msg' and
               r.get('payload', {}).get('type') in ('task_complete', 'turn_aborted')]
    require(bool(endings), 'transcript', 'Codex turn is not finished')
    contexts = [r['payload'] for r in events if r.get('type') == 'turn_context']
    require(bool(contexts), 'transcript', 'missing Codex runtime context')
    models = {(c.get('model'), c.get('effort')) for c in contexts}
    # No safe per-response attribution in older rollouts when the model changed.
    require(len(models) == 1, 'transcript', 'model/effort changed within turn; split the execution')
    model, effort = next(iter(models))
    calls = {}
    for row in events:
        if row.get('type') != 'token_usage_record':
            continue
        p = row['payload']
        require(p.get('thread_id') == agent_id and p.get('turn_id') == turn_id,
                'usage', 'Codex usage identity mismatch')
        response = p.get('response_id')
        string(response, 'response_id')
        value = metrics(p.get('usage'), 'codex')
        require(response not in calls or calls[response] == value, 'usage', 'conflicting duplicate response')
        calls[response] = value
    if calls:
        totals = add_metrics(list(calls.values()))
        records = [r['payload'] for r in events if r.get('type') == 'token_usage_record']
        final = records[-1].get('turn_token_usage')
        if final is not None:
            require(metrics(final, 'codex') == totals, 'usage', 'incomplete per-response coverage')
    else:
        # Legacy token_count contains repeated cumulative snapshots. Use the
        # first snapshot minus last_token_usage as baseline (forks may inherit
        # parent totals), then differences; never sum repeated snapshots.
        baseline, previous = None, None
        for row in rows:
            if row is events[0]:
                break
            p = row.get('payload', {})
            if row.get('type') == 'event_msg' and p.get('type') == 'token_count' and p.get('info'):
                baseline = metrics(p['info'].get('total_token_usage'), 'codex')
        saw_response = False
        for row in events:
            p = row.get('payload', {})
            if row.get('type') == 'response_item' and p.get('role') == 'assistant':
                saw_response = True
            if row.get('type') != 'event_msg' or p.get('type') != 'token_count' or not p.get('info'):
                continue
            info = p['info']
            total = metrics(info.get('total_token_usage'), 'codex')
            if baseline is None:
                require(saw_response, 'usage', 'no reliable initial counter baseline')
                last = metrics(info.get('last_token_usage'), 'codex')
                baseline = {k: total[k] - last[k] if total[k] is not None and last[k] is not None else None for k in total}
                require(all(v is None or v >= 0 for v in baseline.values()), 'usage', 'invalid cumulative baseline')
            if previous:
                require(all(total[k] is None or previous[k] is None or total[k] >= previous[k] for k in total),
                        'usage', 'counters reset within turn; cannot safely aggregate')
            previous = total
        require(previous is not None, 'usage', 'Codex supplied no token counters')
        totals = {k: previous[k] - baseline[k] if previous[k] is not None and baseline[k] is not None else None for k in previous}
        require(all(v is None or v >= 0 for v in totals.values()), 'usage', 'counters reset across turns')
    end = endings[-1]
    start = next((r.get('timestamp') for r in events if r.get('payload', {}).get('type') == 'task_started'), None)
    return [{'model': model, 'effort': effort, 'metrics': totals}], turn_id, seconds(start, end.get('timestamp')), 'turn_context'


def claude(rows, agent_id, decision_id):
    messages = [r for r in rows if r.get('type') in ('user', 'assistant')]
    require(bool(messages) and all(r.get('agentId') == agent_id and r.get('isSidechain') is True for r in messages),
            'agent_id', 'expected only the requested Claude subagent, not the parent session')
    found = set()
    for r in messages:
        if r['type'] == 'user':
            found |= markers(text_content(r.get('message', {}).get('content')))
    require(found == {decision_id}, 'decision_id', 'decision marker missing or multiple decisions in Claude transcript')
    calls = {}
    for row in messages:
        if row['type'] != 'assistant':
            continue
        m = row.get('message', {})
        if m.get('model') == '<synthetic>':
            continue
        ident = m.get('id')
        string(ident, 'message.id')
        value = metrics(m.get('usage', {}), 'claude')
        # perTurnEffort is the per-request override; effort is the host setting.
        effort = row.get('perTurnEffort') if row.get('perTurnEffort') is not None else row.get('effort')
        item = {'model': m.get('model'), 'effort': effort, 'metrics': value}
        if ident in calls:
            old = calls[ident]
            require((old['model'], old['effort']) == (item['model'], item['effort']), 'usage', 'conflicting message identity')
            for key in ('input_tokens', 'cache_tokens', 'cache_write_tokens'):
                require(old['metrics'][key] is None or value[key] is None or old['metrics'][key] == value[key],
                        'usage', 'conflicting duplicate input counters')
            # Streaming chunks share a message ID. Keep the largest reported
            # cumulative output; never count each content block as a new call.
            value = {key: max(v for v in (old['metrics'][key], value[key]) if v is not None)
                     if old['metrics'][key] is not None or value[key] is not None else None for key in value}
            value['total_tokens'] = value['input_tokens'] + value['output_tokens'] if value['input_tokens'] is not None and value['output_tokens'] is not None else None
            item['metrics'] = value
        calls[ident] = item
    require(bool(calls), 'usage', 'Claude supplied no model responses')
    groups = {}
    for item in calls.values():
        groups.setdefault((item['model'], item['effort']), []).append(item['metrics'])
    segments = [{'model': model, 'effort': effort, 'metrics': add_metrics(values)} for (model, effort), values in groups.items()]
    return segments, None, seconds(messages[0].get('timestamp'), messages[-1].get('timestamp')), 'assistant.message.model; perTurnEffort/effort'


def collect(host, path, agent_id, decision_id, config, turn_id=None, agent_type=None):
    identifier(agent_id, 'agent_id')
    require(host in ('codex', 'claude'), 'host')
    require(host == config['operator'], 'host', 'configuration mismatch')
    rows, digest = read_transcript(path)
    if host == 'codex':
        segments, turn_id, duration, model_source = codex(rows, agent_id, decision_id, turn_id)
    else:
        require(turn_id is None, 'turn_id', 'only supported for Codex')
        segments, turn_id, duration, model_source = claude(rows, agent_id, decision_id)
    for segment in segments:
        string(segment['model'], 'reported model', nullable=True)
        string(segment['effort'], 'reported effort', nullable=True)
    single = segments[0] if len(segments) == 1 else {'model': None, 'effort': None}
    candidate = None
    if single['model'] is not None and single['effort'] is not None:
        matches = [c for c in config['ladder'] if c['effort'] == single['effort'] and
                   (single['model'] in (c['model'], c.get('resolved_model')) or
                    host == 'claude' and agent_type == c['agent'])]
        if len(matches) == 1:
            candidate = matches[0]['id']
    totals = add_metrics([s['metrics'] for s in segments])
    source = f'{host}_native_transcript_v1'
    return {'host_confirmed': True, 'effective_candidate': candidate,
            'resolved_model': single['model'], 'effective_effort': single['effort'],
            'metrics': dict(totals, source=source, unit='tokens'),
            'duration_s': duration, 'duration_source': 'transcript_timestamps' if duration is not None else None,
            'execution_segments': segments,
            'host_usage': {'host': host, 'agent_id': agent_id, 'turn_id': turn_id,
                           'agent_type': agent_type, 'transcript_sha256': digest, 'model_source': model_source}}
