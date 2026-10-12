import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from engineering_helper_receipts import export


class EngineeringHelperReceipts(unittest.TestCase):
    def test_scope_dedup_missing_usage_and_reasoning_subset(self):
        with tempfile.TemporaryDirectory() as folder:
            database, output = Path(folder)/'state.db', Path(folder)/'receipt.json'
            connection = sqlite3.connect(database)
            connection.execute('create table token_miser_objects (thread_id text, created_at integer, object_id text, payload text)')
            total = dict(totalTokens=110, inputTokens=100, cachedInputTokens=20,
                         cacheWriteInputTokens=0, outputTokens=10, reasoningOutputTokens=4)
            for index, turn, usage in [(1, 'selected', total), (2, 'selected', total),
                                        (3, 'selected', None), (4, 'unrelated', total)]:
                obj = dict(objectId=str(index), turnId=turn,
                           helperUsage=dict(helperThreadId='helper', helperTurnId='turn' if usage else 'missing',
                                            model='gpt-6-luna', accountKey='MUST_NOT_EXPORT',
                                            tokenUsage={'total': usage}))
                connection.execute('insert into token_miser_objects values (?,?,?,?)',
                                   ('owner', index, str(index), json.dumps(obj)))
            connection.commit(); connection.close()
            summary = export(database, 'owner', 'selected', output)
            self.assertEqual((summary['objects'], summary['helper_rows'], summary['unpriced']), (3, 1, 1))
            self.assertAlmostEqual(summary['reported_helper_cost_usd'], (80*.1 + 20*.01 + 10*.5)/1e6)
            self.assertNotIn('MUST_NOT_EXPORT', output.read_text())


if __name__ == '__main__':
    unittest.main()
