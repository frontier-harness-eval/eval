import unittest
from usage_report import breakdown


class UsageReportTests(unittest.TestCase):
    def test_parent_summary_and_other_helper_remain_separate(self):
        row=dict(model='gpt-6.1-sol',usage_role='parent',usage_line_id='a',input_tokens=1000,
                 cached_input_tokens=600,uncached_input_tokens=400,cache_write_tokens=100,
                 output_tokens=200,reasoning_tokens=150,nonreasoning_output_tokens=50,
                 estimated_cost_usd=.003)
        record=dict(run_id='run',cell=dict(task='task',model='gpt-6.1-sol',token_miser=True),
                    accounting=dict(usage_complete=True,rows=[row,
                    dict(row,model='gpt-6-luna',usage_role='token_miser_summary',usage_line_id='b'),
                    dict(row,model='gpt-6-luna',usage_role='other_helper',usage_line_id='c')]))
        result=breakdown([record])
        self.assertEqual(len(result),3)
        self.assertEqual(result[0]['input_tokens'],1000)
        self.assertEqual(result[0]['output_tokens'],200)
        self.assertEqual(result[0]['reasoning_tokens'],150)
        self.assertEqual(result[1]['usage_line_ids'],['b'])

