"""Prospectively bound native-item lifecycle, never OS cleanup attestation.

Reuse the original owned stream/capture, without another RPC or subscription.
The immutable lifecycle contract is bound before turn/start. Old captures never
acquire this marker retroactively. Missing process/descendant facts stay unknown.
"""
import hashlib
from pathlib import Path
import time

from .core import digest, require
from . import effect_capture as capture

PROTOCOL = 'owned_native_item_lifecycle_v1'
FIELD = 'nativeLifecycleCapture'
FIELDS = {'version', 'protocol', 'sourceHash', 'commandId', 'brainId', 'runId',
          'bindingHash', 'requestHash', 'captureHeaderHash', 'captureSourceHash', 'boundAt'}
BOUNDARY = {'completeEffectInventory': False, 'processBirthVerified': False,
            'completeDescendantLifecycle': False, 'historicalCleanupVerified': False,
            'continuationAuthorized': False, 'pilotAccepted': False}


def source_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def bind(command, meta):
    """Called inside the original one-shot sending transaction, never an importer."""
    note = command.get('notification') or {}; run = meta.get('standardRun') or {}
    anchor = note.get(capture.FIELD) or {}
    require(command.get('kind') in capture.CONTROL_KINDS and note.get('status') == 'sending' and
            note.get('hostInspectionTransport') == 'owned_observer_v1' and FIELD not in note and
            run.get('protocol') == 'standard_cooperative_v1' and
            run.get('brainId') == meta.get('brainId') == note.get('brainId') and
            run.get('id') == note.get('hostRunId') and
            anchor.get('source') == capture.SOURCE and anchor.get('sourceHash') == capture.source_hash() and
            anchor.get('status') == 'open' and 'nativeTurnId' not in note,
            'Lifecycle capture requires its original pre-turn sending anchor; no retrospective bind')
    return {'version': 1, 'protocol': PROTOCOL, 'sourceHash': source_hash(),
            'commandId': command['id'], 'brainId': meta['brainId'], 'runId': run['id'],
            'bindingHash': note['hostBindingHash'], 'requestHash': capture.request_hash(command),
            'captureHeaderHash': anchor['headerHash'], 'captureSourceHash': anchor['sourceHash'],
            'boundAt': time.time()}


def assess(events, turn_id):
    """Positive item lifecycle accounting only; arbitrary programs are never parsed."""
    starts, completions, gaps = {}, {}, []
    ended = False
    for event in events:
        require(event['turnId'] == turn_id, 'Foreign lifecycle turn')
        if ended:
            gaps.append('events_after_turn_completion')
        if event['kind'] == 'turn_completed':
            if ended: gaps.append('duplicate_turn_completion')
            ended = True
            continue
        key = event['itemId']
        if event['kind'] == 'item_started':
            if key in starts: gaps.append('duplicate_start:'+key)
            if key in completions: gaps.append('start_after_completion:'+key)
            starts[key] = event
        else:
            if key in completions: gaps.append('duplicate_completion:'+key)
            if key not in starts: gaps.append('completion_without_start:'+key)
            completions[key] = event
    rows = []
    for key in sorted(starts.keys() | completions.keys()):
        first, last = starts.get(key), completions.get(key)
        if last is None: gaps.append('completion_missing:'+key)
        if first and last and any(first[k] != last[k] for k in ('itemType', 'commandHash', 'cwdHash')):
            gaps.append('item_scope_changed:'+key)
        if first and last and first['nativeHandleHash'] is not None and last['nativeHandleHash'] is not None and first['nativeHandleHash'] != last['nativeHandleHash']:
            gaps.append('native_handle_changed:'+key)
        if first and last and first['osPidHash'] is not None and last['osPidHash'] is not None and first['osPidHash'] != last['osPidHash']:
            gaps.append('os_pid_observation_changed:'+key)
        sample = last or first
        if sample['itemType'] == 'unsupported' or sample['status'] == 'unknown':
            gaps.append('unsupported_item:'+key)
        if last and last['status'] not in {'completed', 'failed', 'declined'}:
            gaps.append('nonterminal_completion:'+key)
        rows.append({'itemId': key, 'itemType': sample['itemType'], 'startObserved': first is not None,
                     'completionObserved': last is not None, 'completionStatus': last['status'] if last else None,
                     'firstObservedAt': first['observedAt'] if first else None,
                     'lastObservedAt': last['observedAt'] if last else None,
                     'nativeHandleObserved': sample['nativeHandleHash'] is not None,
                     'osPidObserved': sample['osPidHash'] is not None,
                     'processBirthEpoch': None, 'descendantLifecycle': 'unknown', 'cleanup': 'unknown'})
    if not ended: gaps.append('turn_completion_missing')
    return {'items': rows, 'turnCompletionObserved': ended, 'gaps': sorted(set(gaps)),
            'processLifecycleCoverage': 'unavailable', 'terminalSafety': 'unknown',
            'boundary': BOUNDARY.copy()}


def retained(ledger, command):
    note = command.get('notification') or {}; marker = note.get(FIELD)
    if marker is None:
        return {'status': 'not_enabled_at_original_boundary', 'terminalSafety': 'unknown',
                'boundary': BOUNDARY.copy()}
    anchor = note.get(capture.FIELD) or {}
    require(isinstance(marker, dict) and set(marker) == FIELDS and
            type(marker['version']) is int and marker['version'] == 1 and marker['protocol'] == PROTOCOL and
            marker['sourceHash'] == source_hash() and marker['commandId'] == command['id'] and
            marker['brainId'] == note.get('brainId') and marker['runId'] == note.get('hostRunId') and
            marker['bindingHash'] == note.get('hostBindingHash') and
            marker['requestHash'] == capture.request_hash(command) and
            marker['captureHeaderHash'] == anchor.get('headerHash') and
            marker['captureSourceHash'] == anchor.get('sourceHash') and
            capture.finite(marker['boundAt']) and marker['boundAt'] >= anchor.get('startedAt', float('inf')),
            'Original lifecycle contract or capture anchor changed')
    value = capture.retained(ledger, command)
    if value['status'] != 'observed':
        return {'status': 'incomplete', 'captureStatus': value['status'], 'terminalSafety': 'unknown',
                'boundary': BOUNDARY.copy()}
    require(all(e['observedAt'] >= marker['boundAt'] for e in value['events']),
            'Lifecycle contract was not bound before its observed effects')
    result = assess(value['events'], note['nativeTurnId'])
    return {'status': 'recorded_item_lifecycles_observed' if not result['gaps'] else 'incomplete',
            'protocol': PROTOCOL, 'originalBoundAt': marker['boundAt'], 'captureHash': digest(value), **result}
