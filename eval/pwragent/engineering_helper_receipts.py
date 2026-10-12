"""Whitelist retained native-helper counters for one explicitly selected owner turn."""
import argparse
import datetime
import json
import sqlite3
from pathlib import Path
from accounting import CARD


def export(database, thread_id, turn_id, output):
    connection = sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True)
    selected = []
    for (payload,) in connection.execute(
            'select payload from token_miser_objects where thread_id=? order by created_at,object_id',
            (thread_id,)):
        obj = json.loads(payload)
        if obj.get('turnId') == turn_id:
            selected.append(obj)
    connection.close()
    rows, seen, unknown = [], {}, []
    fields = ['totalTokens', 'inputTokens', 'cachedInputTokens', 'cacheWriteInputTokens',
              'outputTokens', 'reasoningOutputTokens']
    for obj in selected:
        helper = obj.get('helperUsage')
        if not helper:
            continue
        identity = (helper.get('helperThreadId'), helper.get('helperTurnId'))
        usage = (helper.get('tokenUsage') or {}).get('total') or {}
        tokens = {key: usage.get(key) for key in fields}
        model = helper.get('model')
        if not all(identity) or model not in CARD['models'] or not all(
                isinstance(value, int) and value >= 0 for value in tokens.values()):
            unknown.append(obj['objectId'])
            continue
        if identity in seen:
            if seen[identity] != (model, tokens):
                raise ValueError('Conflicting retained helper counters')
            continue
        seen[identity] = (model, tokens)
        inp, cache, write, out, reason = [tokens[key] for key in fields[1:]]
        if cache + write > inp or reason > out or inp + out != tokens['totalTokens']:
            raise ValueError('Inconsistent helper counters')
        # Each retained helper is one turn, not necessarily one provider request.
        # A total below the threshold proves every request was short-context.
        if inp > CARD['long_context_threshold_input_tokens']:
            unknown.append(obj['objectId'])
            continue
        rates = CARD['models'][model]['short']
        cost = ((inp-cache-write)*rates[0] + cache*rates[1] + write*rates[2] + out*rates[3])/1e6
        rows.append(dict(object_id=obj['objectId'], helper_thread_id=identity[0],
                         helper_turn_id=identity[1], model=model, tokens=tokens,
                         estimated_cost_usd=cost))
    result = dict(captured_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  scope='Retained native helper objects for this exact engineering thread and turn only.',
                  thread_id=thread_id, turn_id=turn_id, objects=len(selected),
                  helper_rows=rows, unpriced_object_ids=unknown,
                  reported_helper_cost_usd=sum(row['estimated_cost_usd'] for row in rows),
                  limitation='Standard-card API-equivalent estimate. Retained objects do not prove coverage of deleted, failed or unattributed helpers; a separate uncertainty allowance remains. No auth, account identifiers, prompts or content exported.')
    Path(output).write_text(json.dumps(result, indent=2) + '\n')
    return dict(objects=len(selected), helper_rows=len(rows), unpriced=len(unknown),
                reported_helper_cost_usd=result['reported_helper_cost_usd'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', required=True, type=Path)
    parser.add_argument('--thread', required=True)
    parser.add_argument('--turn', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.database, args.thread, args.turn, args.output)))
