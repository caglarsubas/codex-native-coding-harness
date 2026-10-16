"""Private SQLite identity validation, distinct from bounded runtime JSON."""
import os
import contextlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from orchestrator.core import Refusal
from orchestrator.host_lifecycle import private_file
from orchestrator.workspaces import private_database


class PrivateDatabaseTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve(); self.root.chmod(0o700)
        self.path = self.root/'registry.sqlite3'
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE example(data TEXT)')
            db.execute('INSERT INTO example VALUES(?)', ('bounded fixture'*10000,))
        self.path.chmod(0o600)

    def test_grown_database_has_no_small_runtime_record_cap(self):
        self.assertGreater(self.path.stat().st_size, 65536)
        self.assertEqual(private_database(self.path), self.path)
        with self.assertRaises(Refusal): private_file(self.path)

    def test_non_database_and_public_permissions_refuse(self):
        self.path.chmod(0o644)
        with self.assertRaises(Refusal): private_database(self.path)
        self.path.chmod(0o600); self.path.write_bytes(b'not SQLite')
        with self.assertRaises(Refusal): private_database(self.path)

    def test_symlink_hardlink_and_unsafe_ancestor_refuse(self):
        alias = self.root/'alias'; alias.symlink_to(self.path)
        with self.assertRaises(Refusal): private_database(alias)
        alias.unlink(); os.link(self.path, alias)
        with self.assertRaises(Refusal): private_database(self.path)
        alias.unlink(); self.root.chmod(0o777)
        with self.assertRaises(Refusal): private_database(self.path)
        self.root.chmod(0o700)

    def test_replacement_during_header_read_refuses(self):
        other = self.root/'replacement.sqlite3'
        with contextlib.closing(sqlite3.connect(other)) as db, db: db.execute('CREATE TABLE other(id INTEGER)')
        other.chmod(0o600); original = os.pread
        def replace(fd, size, offset):
            data = original(fd, size, offset); os.replace(other, self.path); return data
        with patch('orchestrator.workspaces.os.pread', side_effect=replace), self.assertRaises(Refusal):
            private_database(self.path)
