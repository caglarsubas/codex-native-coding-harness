"""Foreground ownership of an already claimed native subscription.

This owns a connection, not a brain controller or phase. It never opens a
connection, loads a thread, sends a keepalive turn, or reconnects after failure.
The caller must close its proxy on every exit, including interrupted claims.
"""
import os
import time
import uuid

from .admission import sha
from .core import require
from .native_read_client import NativeReadFailure

MIN_SECONDS = 15
MAX_SECONDS = 300
CHECK_SECONDS = 5


def duration(value):
    require(type(value) is int and MIN_SECONDS <= value <= MAX_SECONDS,
            'Subscription observation window must be 15–300 whole seconds')
    return value


class SubscriptionOwner:
    """One non-renewable deadline on one foreground proxy/process epoch."""
    def __init__(self, proxy, seconds, spec_hash):
        self.seconds = duration(seconds)
        sha(spec_hash)
        self.proxy, self.process = proxy, proxy.process
        self.spec_hash, self.connection_id = spec_hash, str(uuid.uuid4())
        self.started_at, self.started = time.time(), time.monotonic()
        self.deadline = self.started + self.seconds

    def before_rpc(self, proxy):
        require(proxy is self.proxy and proxy.process is self.process,
                'Subscription connection changed; no reconnect or ownership transfer')
        now = time.monotonic()
        if now >= self.deadline:
            raise NativeReadFailure('deadline_exceeded', 'Subscription observation window ended; never reload')
        # Per-RPC deadlines may advance, but never the reviewed overall window.
        proxy.deadline = min(now + proxy.timeout, self.deadline)

    def hold(self, check):
        """Only fixed explicit metadata checks; no model work or detached loop."""
        while True:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(CHECK_SECONDS, remaining))
            if time.monotonic() >= self.deadline:
                return
            self.before_rpc(self.proxy)
            check()

    def record(self):
        return {'specHash': self.spec_hash, 'connectionId': self.connection_id,
                'ownerPid': os.getpid(), 'startedAt': self.started_at, 'maximumSeconds': self.seconds,
                'source': 'original_claimed_resume_connection',
                'automaticReconnect': False, 'deadlineRenewable': False,
                'controllerAuthority': False, 'terminalSafety': 'unknown'}
