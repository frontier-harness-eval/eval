import json
import tempfile
import unittest
from pathlib import Path
from protocol_usage_audit import audit


class ProtocolUsageAudit(unittest.TestCase):
    def fixture(self, root, missing_helper):
        output=root/'output';output.mkdir()
        total=dict(inputTokens=100,cachedInputTokens=20,cacheWriteInputTokens=0,
                   outputTokens=10,reasoningOutputTokens=4,totalTokens=110)
        events=[];rows=[]
        for index,label in enumerate(['parent','helper']):
            turn=label+'-turn';request=index+1
            def event(direction,envelope):
                events.append(dict(direction=direction,envelope=envelope,backendInstance='codex',sequence=len(events)+1))
            event('outbound',dict(id=request,method='turn/start',params={'threadId':label}))
            event('inbound',dict(id=request,result={'turn':{'id':turn}}))
            missing=label=='helper' and missing_helper
            if not missing:
                event('inbound',dict(method='thread/tokenUsage/updated',params=dict(threadId=label,turnId=turn,tokenUsage={'total':total})))
                rows.append(dict(threadId=label,turnId=turn,usageLineId=label,
                                 status='pending' if label=='parent' else 'finalized',model='test',**total))
            event('inbound',dict(method='turn/completed',params=dict(threadId=label,turn={'id':turn,'status':'interrupted' if missing else 'completed'})))
        (output/'protocol.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        (output/'result.json').write_text(json.dumps(dict(runId='fixture',pricing={'lines':rows})))

    def test_pending_pricing_label_can_match_completed_provider_counters(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root,False)
            self.assertTrue(audit(root)['all_observed_turns_reconciled'])

    def test_missing_interrupted_helper_is_not_zero_cost(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root,True);proof=audit(root)
            self.assertFalse(proof['all_observed_turns_reconciled'])
            self.assertEqual(proof['turns'][1]['terminal_status'],'interrupted')
            self.assertEqual(len(proof['turns'][1]['counter_mismatches']),6)


if __name__=='__main__':unittest.main()
