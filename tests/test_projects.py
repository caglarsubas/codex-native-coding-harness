import copy
import json
import time
import unittest

from orchestrator import projects
from orchestrator.core import Refusal
import test_workspaces
import test_workspace_server


def inventory():
    return {"schemaVersion": 2, "projects": [
        {"projectId": "native-a", "projectKind": "local", "label": "Codex Alpha", "hostId": "local",
         "path": "/private/source-a", "isGitRepository": True},
        {"projectId": "native-b", "projectKind": "local", "label": "Codex Beta", "hostId": "local",
         "path": "/private/source-b", "isGitRepository": False},
        {"projectId": "chat", "projectKind": "chatgpt", "label": "Not a Codex project"}]}


class ProjectCatalogTest(unittest.TestCase):
    setUp = test_workspaces.WorkspaceTest.setUp
    tearDown = test_workspaces.WorkspaceTest.tearDown
    make = test_workspaces.WorkspaceTest.make
    contents = test_workspaces.WorkspaceTest.contents
    def test_read_does_not_create_catalog(self):
        self.assertEqual(projects.catalog(self.registry)["status"], "not_synced")
        with self.registry.tx() as db:
            self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='project_catalog'").fetchone())

    def test_import_binding_rename_removal_preserves_ledger(self):
        self.registry.register("a", "Existing history", self.a.root)
        before = self.contents(self.a)
        data = inventory(); at = time.time()
        saved = projects.record(self.registry, data, at)
        unbound = projects.catalog(self.registry)
        self.assertEqual([p["name"] for p in unbound["projects"]], ["Codex Alpha", "Codex Beta"])
        self.assertFalse(any(p["managed"] for p in unbound["projects"]))
        self.assertNotIn("/private", json.dumps(unbound))
        projects.bind(self.registry, "a", "local", "native-a", saved["hash"])
        linked = projects.catalog(self.registry)
        self.assertEqual(linked["projects"][0]["id"], "a")
        self.assertTrue(linked["projects"][0]["managed"])
        self.assertEqual(linked["unlisted"], [])
        data["projects"][0]["label"] = "Renamed in Codex"
        projects.record(self.registry, data, at + 1)
        self.assertEqual(projects.display_name(self.registry, "a", "old"), "Renamed in Codex")
        self.assertEqual(self.registry.list()[0]["name"], "Existing history")
        projects.record(self.registry, {"schemaVersion": 2, "projects": []}, at + 2)
        removed = projects.catalog(self.registry)
        self.assertEqual(removed["projects"], [])
        self.assertEqual(removed["unlisted"][0]["id"], "a")
        self.assertEqual(before, self.contents(self.a))

    def test_identity_changes_require_review_not_retarget(self):
        self.registry.register("a", "A", self.a.root)
        data = inventory(); at = time.time()
        saved = projects.record(self.registry, data, at)
        projects.bind(self.registry, "a", "local", "native-a", saved["hash"])
        with self.assertRaises(Refusal): projects.bind(self.registry, "a", "local", "native-b", saved["hash"])
        with self.assertRaises(Refusal): projects.bind(self.registry, "a", "local", "native-a", "old-hash")
        data["projects"][0]["path"] = "/private/different"
        projects.record(self.registry, data, at + 1)
        view = projects.catalog(self.registry)
        self.assertFalse(view["projects"][0]["managed"])
        self.assertEqual(view["projects"][0]["bindingStatus"], "needs_review")
        self.assertEqual(view["unlisted"][0]["id"], "a")

    def test_bad_and_out_of_order_inventory_cannot_replace_good(self):
        data = inventory(); at = time.time()
        saved = projects.record(self.registry, data, at)
        bad = [None, {}, {"schemaVersion": 2, "projects": data["projects"] * 2}]
        for field, value in [("label", "bad\nname"), ("projectId", ""), ("hostId", None), ("isGitRepository", 1), ("projectKind", "unknown")]:
            x = copy.deepcopy(data); x["projects"][0][field] = value; bad.append(x)
        for x in bad:
            with self.assertRaises(Refusal): projects.record(self.registry, x, at + 1)
        with self.assertRaises(Refusal): projects.record(self.registry, data, at - 1)
        with self.assertRaises(Refusal): projects.record(self.registry, data, float("nan"))
        with self.assertRaises(Refusal): projects.record(self.registry, data, float("inf"))
        self.assertEqual(projects.record(self.registry, data, at), saved)
        self.assertEqual(projects.catalog(self.registry)["observedAt"], at)

    def test_same_path_different_native_ids_are_not_merged(self):
        data = inventory(); data["projects"][1]["path"] = data["projects"][0]["path"]
        projects.record(self.registry, data, time.time())
        self.assertEqual(len(projects.catalog(self.registry)["projects"]), 2)


class ProjectServerTest(unittest.TestCase):
    setUp = test_workspace_server.WorkspaceServerTest.setUp
    tearDown = test_workspace_server.WorkspaceServerTest.tearDown
    request = test_workspace_server.WorkspaceServerTest.request
    login = test_workspace_server.WorkspaceServerTest.login
    def test_catalog_authenticated_scoped_and_inert(self):
        saved = projects.record(self.registry, inventory(), time.time())
        projects.bind(self.registry, "a", "local", "native-a", saved["hash"])
        self.assertEqual(self.request("/api/workspaces")[0], 401)
        auth = self.login()
        status, _, raw = self.request("/api/workspaces", headers=auth)
        self.assertEqual(status, 200)
        view = json.loads(raw)["catalog"]
        self.assertEqual(view["projects"][0]["name"], "Codex Alpha")
        unconfigured = view["projects"][1]["id"]
        self.assertEqual(self.request("/api/workspaces/" + unconfigured + "/state", headers=auth)[0], 400)
        _, _, state = self.request("/api/workspaces/a/state", headers=auth)
        self.assertEqual(json.loads(state)["workspace"]["name"], "Codex Alpha")
        self.assertNotIn(b"/private/source", raw)
        self.assertEqual(self.ledgers["a"].snapshot()["commands"], [])
