"""Offline unit tests for the aiwork/dtcoder per-call usage parser.

No model call, no container: a synthetic dtcoder.txt with known token_usage,
plus an assertion against a captured real sample when present.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from usage_details import _aiwork, REGISTRY, extract_usage_details, _empty  # noqa: E402


def _event(rounds):
    return json.dumps({
        "kind": "event", "category": "agent", "operation": "chat.send",
        "event": {"name": "stream.profiling", "phase": "result"},
        "data": {"agent_id": "tb", "rounds": rounds},
    })


def _round(n, inp, read, write, out):
    return {"round": n, "token_usage": {
        "input_tokens": inp, "output_tokens": out, "total_tokens": inp + out,
        "cache_read_tokens": read, "cache_write_tokens": write}}


class AiworkUsage(unittest.TestCase):
    def test_registry_entry(self):
        self.assertIn("aiwork-code", REGISTRY)
        self.assertEqual(REGISTRY["aiwork-code"][0], "dtcoder.txt")

    def test_convention_excludes_cache_write_keeps_cache_read(self):
        # element[0] = input - cache_write = fresh + cache_read ; element[1] = cache_read
        text = "\n".join([
            '{"event":{"name":"stream.started"}}',
            'plain stderr line that is not json',  # tee 2>&1 noise -> must be skipped
            '{"event":{"name":"stream.text_delta"},"data":{"text":"hi"}}',
            _event([_round(1, 6858, 0, 6678, 6239),      # -> (180, 0)
                    _round(2, 11577, 9659, 1916, 125)]), # -> (9661, 9659)
            '{"event":{"name":"stream.completed"}}',
        ])
        d = _aiwork(text)
        self.assertEqual(d["calls"], 2)
        self.assertEqual(d["first_input"], 6858 - 6678)   # 180
        self.assertEqual(d["first_cached"], 0)

    def test_call_counts_all_rounds(self):
        text = _event([_round(i, 1000 + i, 0, 0, 10) for i in range(1, 8)])
        self.assertEqual(_aiwork(text)["calls"], 7)

    def test_no_profiling_returns_empty(self):
        text = '{"event":{"name":"stream.text_delta"},"data":{"text":"x"}}'
        self.assertEqual(_aiwork(text), _empty())

    def test_cold_cost_gate_satisfied(self):
        # calculate-cost.py gates `cold` on first_cached is not None; a hit must
        # yield non-None first_input/first_cached so cost_first_cold_usd exists.
        d = _aiwork(_event([_round(1, 5000, 0, 4000, 50)]))
        self.assertIsNotNone(d["first_input"])
        self.assertIsNotNone(d["first_cached"])

    def test_extract_usage_details_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Path(tmp)
            (agent / "dtcoder.txt").write_text(_event([_round(1, 6858, 0, 6678, 6239)]))
            d = extract_usage_details(agent, "aiwork-code")
            self.assertEqual(d["calls"], 1)
            self.assertEqual(d["first_input"], 180)

    def test_real_sample_ground_truth(self):
        sample = Path("/tmp/dtcoder_sample.txt")
        if not sample.exists():
            self.skipTest("real sample not present")
        d = _aiwork(sample.read_text(errors="replace"))
        self.assertEqual(d["calls"], 14)
        self.assertEqual(d["first_input"], 6858 - 6678)  # 180
        self.assertEqual(d["first_cached"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
