import unittest
import copy
import tempfile
from pathlib import Path
from unittest.mock import patch
from accounting import account
from native_request_reconciliation import extra_requests, add_native_usage, KEYS, WIRE


class NativeRequestCoverage(unittest.TestCase):
    def request(self, compact=False):
        return dict(usage=dict(zip(KEYS,[100,80,0,10,2,110])),followed_by_compaction=compact)

    def wire(self):
        return dict(zip(WIRE,[100,80,0,10,2,110]))

    def test_equal_usage_requests_keep_multiplicity(self):
        first,second=self.request(),self.request(True)
        self.assertEqual(extra_requests([first,second],[self.wire()]),[second])
        self.assertEqual(extra_requests([first,second],[self.wire(),self.wire()]),[])

    def test_unclassified_missing_request_and_unmatched_app_request_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'Unclassified'):
            extra_requests([self.request()],[])
        with self.assertRaisesRegex(ValueError,'no matching'):
            extra_requests([],[self.wire()])

    def test_native_merge_keeps_unknown_helper_and_prices_compaction_once(self):
        line=dict(usageLineId='parent',model='gpt-6.1-sol',status='finalized',inputTokens=1000,cachedInputTokens=600,cacheWriteInputTokens=0,outputTokens=200,reasoningOutputTokens=100,totalCostMicros=1)
        base=account({'pricing':{'lines':[line]}});original=copy.deepcopy(base)
        original.update(usage_complete=False,unpriced_models=['unknown-helper'],missing_usage=[{'model':'unknown-helper'}])
        record=dict(run_id='fixture',cell={'model':'gpt-6.1-sol'},agent_status='completed',accounting=original,grade={'success':False})
        request=self.request(True);request['response_id']='compact'
        proof=dict(compaction_requests=[request],native_terminal_event_observed=True,native_request_count=2)
        before=base['estimated_cost_usd']
        with tempfile.TemporaryDirectory() as tmp,patch('native_request_reconciliation.LOCAL',Path(tmp)):
            output=Path(tmp)/'runs/fixture/output';output.mkdir(parents=True);(output/'native-request-reconciliation.json').write_text('{}')
            add_native_usage(record,base,proof)
        self.assertFalse(record['accounting']['usage_complete'])
        self.assertEqual(record['accounting']['unpriced_models'],['unknown-helper'])
        self.assertEqual(record['accounting']['missing_usage'],[{'model':'unknown-helper'}])
        self.assertEqual(record['grade'],{'success':False})
        self.assertAlmostEqual(record['accounting']['estimated_cost_usd'],before+0.000148)
        self.assertEqual(record['accounting']['rows'][-1]['usage_role'],'codex_compaction')
