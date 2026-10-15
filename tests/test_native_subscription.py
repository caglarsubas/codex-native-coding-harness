"""Subscription ownership never opens, transfers or renews a native connection."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from orchestrator.core import Refusal
from orchestrator.native_read_client import NativeReadFailure, ReadProxy
from orchestrator.native_subscription import SubscriptionOwner


class OwnerTest(unittest.TestCase):
    def test_exact_proxy_and_process_epoch_are_required(self):
        proxy = SimpleNamespace(process=object(), timeout=15)
        owner = SubscriptionOwner(proxy, 75, 'a'*64)
        with self.assertRaises(Refusal): owner.before_rpc(SimpleNamespace(process=proxy.process, timeout=15))
        proxy.process = object()
        with self.assertRaises(Refusal): owner.before_rpc(proxy)

    def test_rpc_deadline_never_renews_the_reviewed_overall_deadline(self):
        proxy = SimpleNamespace(process=object(), timeout=15)
        with patch('orchestrator.native_subscription.time.monotonic', return_value=100):
            owner = SubscriptionOwner(proxy, 75, 'a'*64)
        with patch('orchestrator.native_subscription.time.monotonic', return_value=170):
            owner.before_rpc(proxy)
            self.assertEqual(proxy.deadline, 175)
        with patch('orchestrator.native_subscription.time.monotonic', return_value=175):
            with self.assertRaises(NativeReadFailure): owner.before_rpc(proxy)
        self.assertEqual(owner.deadline, 175)
        self.assertEqual(ReadProxy.query_limit, 128)

    def test_hold_never_sleeps_over_five_seconds_or_reads_after_deadline(self):
        clock, waits, checks = [0], [], []
        def sleep(seconds):
            waits.append(seconds); clock[0] += seconds
        proxy = SimpleNamespace(process=object(), timeout=15)
        with patch('orchestrator.native_subscription.time.monotonic', lambda: clock[0]), \
             patch('orchestrator.native_subscription.time.sleep', sleep):
            owner = SubscriptionOwner(proxy, 16, 'a'*64)
            owner.hold(lambda: checks.append(clock[0]))
        self.assertEqual(checks, [5, 10, 15])
        self.assertEqual(waits, [5, 5, 5, 1])


if __name__ == '__main__': unittest.main()
