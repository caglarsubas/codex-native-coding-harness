"""Original-bound native item lifecycle is never retrospective OS safety."""
import copy
import unittest
from unittest.mock import patch

from orchestrator import prospective_lifecycle as lifecycle, effect_capture as capture
from orchestrator.core import Refusal, canonical
import test_independent_effects as fixture


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.EffectCaptureTest(methodName='runTest'); self.f.setUp()
        self.addCleanup(self.f.tearDown)

    def begin(self):
        self.f.begin()
        self.f.command['notification'][lifecycle.FIELD] = lifecycle.bind(self.f.command, self.f.meta)

    def events(self, *, start=True, end=True, turn=True):
        if start: capture.append(self.f.ledger, 'control', fixture.BRAIN, self.f.event('item/started', status='inProgress', exitCode=None))
        if end: capture.append(self.f.ledger, 'control', fixture.BRAIN, self.f.event())
        if turn: capture.append(self.f.ledger, 'control', fixture.BRAIN, {'method': 'turn/completed', 'params': {
            'threadId': fixture.BRAIN, 'turn': {'id': 'turn', 'status': 'completed'}}})

    def result(self): return lifecycle.retained(self.f.ledger, self.f.command)

    def test_future_lifecycle_is_bound_before_effect_and_preserves_privacy(self):
        self.begin(); self.events(); self.f.seal()
        r = self.result(); self.assertEqual(r['status'], 'recorded_item_lifecycles_observed')
        self.assertTrue(r['items'][0]['startObserved']); self.assertTrue(r['items'][0]['completionObserved'])
        self.assertEqual(r['items'][0]['cleanup'], 'unknown')
        self.assertIsNone(r['items'][0]['processBirthEpoch'])
        self.assertFalse(any(r['boundary'].values()))
        self.assertNotIn('PRIVATE', canonical(r)); self.assertNotIn('native-handle', canonical(r))

    def test_legacy_capture_cannot_get_a_retroactive_lifecycle_contract(self):
        self.f.begin(); self.events(); self.f.seal(); self.f.command['notification']['status'] = 'accepted'
        self.assertEqual(self.result()['status'], 'not_enabled_at_original_boundary')
        with self.assertRaises(Refusal): lifecycle.bind(self.f.command, self.f.meta)

    def test_bound_after_existing_event_cannot_manufacture_first_effect_coverage(self):
        self.f.begin(); self.events()
        self.f.command['notification'][lifecycle.FIELD] = lifecycle.bind(self.f.command, self.f.meta)
        self.f.seal()
        with self.assertRaisesRegex(Refusal, 'before its observed effects'): self.result()

    def test_missing_start_completion_or_turn_stays_partial(self):
        self.begin(); self.events(start=False, turn=False); self.f.seal()
        r = self.result(); self.assertEqual(r['status'], 'incomplete')
        self.assertIn('completion_without_start:item-1', r['gaps']); self.assertIn('turn_completion_missing', r['gaps'])

    def test_unfinished_item_and_duplicate_events_stay_partial(self):
        self.begin(); self.events(end=False, turn=False)
        capture.append(self.f.ledger, 'control', fixture.BRAIN, self.f.event('item/started', status='inProgress', exitCode=None))
        self.f.seal(); r = self.result()
        self.assertIn('completion_missing:item-1', r['gaps']); self.assertIn('duplicate_start:item-1', r['gaps'])

    def test_inconsistent_item_scope_and_pid_are_not_clean(self):
        self.begin(); self.events(end=False, turn=False)
        capture.append(self.f.ledger, 'control', fixture.BRAIN, self.f.event(command='changed', osPid=456))
        self.f.seal(); r = self.result()
        self.assertIn('item_scope_changed:item-1', r['gaps']); self.assertIn('os_pid_observation_changed:item-1', r['gaps'])

    def test_open_or_interrupted_stream_never_qualifies(self):
        self.begin(); self.assertEqual(self.result()['status'], 'incomplete')
        self.events(); self.f.seal(failed=True); self.assertEqual(self.result()['status'], 'incomplete')

    def test_changed_contract_identity_producer_or_clean_flags_refuse(self):
        self.begin(); self.events(); self.f.seal(); old = copy.deepcopy(self.f.command)
        for key, value in [('brainId', 'foreign'), ('sourceHash', 'a'*64), ('cleanupVerified', True)]:
            self.f.command['notification'][lifecycle.FIELD][key] = value
            with self.assertRaises(Refusal): self.result()
            self.f.command = copy.deepcopy(old)

    def test_no_os_pid_or_forged_extra_native_fields_are_not_safety(self):
        self.begin()
        capture.append(self.f.ledger, 'control', fixture.BRAIN, self.f.event('item/started', status='inProgress', exitCode=None,
            osPid=None, processStartTime=1, descendants=[], descendantCoverage=True, cleanupVerified=True))
        capture.append(self.f.ledger, 'control', fixture.BRAIN, self.f.event(osPid=None))
        self.f.seal(); r = self.result()
        self.assertFalse(r['items'][0]['osPidObserved']); self.assertFalse(any(r['boundary'].values()))
        self.assertEqual(r['processLifecycleCoverage'], 'unavailable')


if __name__ == '__main__': unittest.main()
