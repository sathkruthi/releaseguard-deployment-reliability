import unittest

from releaseguard.metrics import delta


class MetricTests(unittest.TestCase):
    def test_window_and_bucket_quantile(self):
        before = {
            "requests": {"success": 100, "dependency": 10},
            "buckets": {"0.1": 100, "0.5": 110, "+Inf": 110},
        }
        after = {
            "requests": {"success": 138, "dependency": 12},
            "buckets": {"0.1": 137, "0.5": 150, "+Inf": 150},
        }
        result = delta(before, after)
        self.assertEqual(result["requests"], 40)
        self.assertEqual(result["error_rate"], 0.05)
        self.assertEqual(result["p95_seconds"], 0.5)
        self.assertFalse(result["counter_reset"])

    def test_reset_and_infinite_bucket_are_inconclusive(self):
        first = {"requests": {"success": 20}, "buckets": {"1": 20, "+Inf": 20}}
        reset = {"requests": {"success": 1}, "buckets": {"1": 1, "+Inf": 1}}
        self.assertTrue(delta(first, reset)["counter_reset"])
        slow = {"requests": {"success": 40}, "buckets": {"1": 20, "+Inf": 40}}
        self.assertTrue(delta(first, slow)["counter_reset"])

    def test_instance_reset_cannot_hide_in_increasing_aggregate(self):
        before = {
            "requests": {"success": 100},
            "buckets": {"1": 100, "+Inf": 100},
            "series": {"a|success": 80, "b|success": 20},
        }
        after = {
            "requests": {"success": 120},
            "buckets": {"1": 120, "+Inf": 120},
            "series": {"a|success": 1, "b|success": 119},
        }
        self.assertTrue(delta(before, after)["counter_reset"])
