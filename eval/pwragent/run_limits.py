"""Benchmark time allowances; no default cumulative-token cutoff.

Exact historical protocol hashes retain their old limits for reproduction only.
New cohorts must disclose any additional limits explicitly in their protocol.
"""

LEGACY_STAGE1 = '1683ec327cdfdd2b97c106e41a0c2e37f4f84a31a1d2847e999a4fb566829e46'
LEGACY_TIME_CAPPED = {
    LEGACY_STAGE1,
    '1d77c9efb7099ac2931f15f55083b931b6f92e4cd9a4d2ec650981935d22b72b',
    '38f942f967fd1dafaaf6fcf54335c32e3c684755206ae6ee224013e376688029',
}


def run_limits(protocol, task_metadata, model, protocol_hash=None):
    timeout = float(task_metadata.get('agent', {}).get('timeout_sec', 900))
    if protocol_hash in LEGACY_TIME_CAPPED:
        timeout = min(timeout, 1200)
    if timeout <= 0:
        raise ValueError('Positive benchmark agent timeout required')
    if timeout > 86400:
        raise ValueError('Frozen driver supports at most 24 hours; amend the protocol before admission')
    limits = {'timeoutMs': round(timeout * 1000)}
    cost_stop = protocol.get('observed_cost_stops_usd', {}).get(model)
    if cost_stop is not None:
        if cost_stop <= 0:
            raise ValueError('Positive observed cost guard required')
        limits['maxObservedCostUsd'] = cost_stop
    token_stop = protocol.get('inclusive_token_stop')
    if protocol_hash == LEGACY_STAGE1 and token_stop is None:
        token_stop = 750000  # Historical pilot only; never a new-cohort default.
    if token_stop is not None:
        if token_stop <= 0:
            raise ValueError('Positive explicit token stop required')
        limits['maxObservedTokens'] = token_stop
    return limits
