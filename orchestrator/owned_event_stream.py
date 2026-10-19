"""Bounded I/O for ONE already-owned connection; never an RPC/authority worker.

The reader drains WebSocket control frames while the foreground owner validates
files or services a mailbox. It cannot reconnect, send JSON, or execute callbacks.
Only the foreground owner consumes data events and makes authority decisions.
"""
import queue
import threading
import time

from .core import Refusal, canonical, require


class OwnedEventStream:
    max_events = 4096
    max_bytes = 16_000_000

    def __init__(self, proxy, read, lost):
        self.proxy, self.read, self.lost = proxy, read, lost
        self.deadline = proxy.deadline
        self.stop = threading.Event()
        self.events = queue.Queue(self.max_events)
        self.lock = threading.Lock()
        self.bytes = 0
        self.error = None
        self.thread = threading.Thread(target=self._run, name='owned-websocket-reader', daemon=True)

    def start(self):
        self.thread.start()

    def _run(self):
        try:
            while not self.stop.is_set():
                self.proxy._watch_tick()
                row = self.read()
                size = len(canonical(row).encode('utf-8'))
                with self.lock:
                    require(self.bytes + size <= self.max_bytes, 'Owned observer event buffer full')
                    self.events.put_nowait((row, size))
                    self.bytes += size
        except (queue.Full, Refusal, OSError, ValueError) as error:
            self.error = self.lost('observer_backpressure') if isinstance(error, queue.Full) or (
                isinstance(error, Refusal) and str(error) == 'Owned observer event buffer full') else error
        except Exception:
            self.error = self.lost('observer_reader_failed')

    def next(self, callback, deadline):
        # No file validation or native RPC is ever performed by the I/O reader.
        # A callback can take longer than a heartbeat without blocking pongs.
        self.check()
        if callback is not None:
            callback()
        self.check()
        while True:
            self.check()
            try:
                row, size = self.events.get_nowait()
                with self.lock:
                    self.bytes -= size
                return row
            except queue.Empty:
                require(time.monotonic() < deadline, 'Native read deadline exceeded')
                self.stop.wait(.025)
                self.check()
                if callback is not None:
                    callback()

    def check(self):
        if self.error is not None:
            raise self.error
        if self.stop.is_set():
            raise self.lost('observer_closed')

    def close(self):
        self.stop.set()
        if self.thread is not threading.current_thread():
            self.thread.join(timeout=.5)
