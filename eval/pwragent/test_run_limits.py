import unittest
from run_limits import LEGACY_STAGE1, run_limits


class ExecutionLimitTests(unittest.TestCase):
    def test_unsupported_timeout_is_rejected_without_silent_shortening(self):
        self.assertEqual(run_limits({}, {'agent':{'timeout_sec':86400}}, 'gpt-6.1-sol')['timeoutMs'],86400000)
        with self.assertRaisesRegex(ValueError,'24 hours'):
            run_limits({}, {'agent':{'timeout_sec':129600}}, 'gpt-6.1-sol')

    def test_new_cohort_keeps_benchmark_time_and_has_no_token_cutoff(self):
        limits = run_limits({}, {'agent': {'timeout_sec': 10800}}, 'gpt-6-astra')
        self.assertEqual(limits, {'timeoutMs': 10800000})

    def test_immutable_historical_pilot_can_be_reproduced(self):
        limits = run_limits({}, {'agent': {'timeout_sec': 10800}}, 'gpt-6-astra', LEGACY_STAGE1)
        self.assertEqual(limits, {'timeoutMs': 1200000, 'maxObservedTokens': 750000})

    def test_only_explicit_limits_apply_to_new_protocol(self):
        pr = {'inclusive_token_stop': None, 'observed_cost_stops_usd': {'gpt-6-astra': 24}}
        limits = run_limits(pr, {'agent': {'timeout_sec': 900}}, 'gpt-6-astra')
        self.assertEqual(limits, {'timeoutMs': 900000, 'maxObservedCostUsd': 24})
        pr['inclusive_token_stop'] = 2000000
        self.assertEqual(run_limits(pr, {}, 'gpt-6-astra')['maxObservedTokens'], 2000000)


if __name__ == '__main__':
    unittest.main()
