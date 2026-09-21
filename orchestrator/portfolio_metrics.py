"""Recorded code-snapshot identity and counting; never execution/admission evidence.

Only observe_identity performs Git/filesystem reads, during an explicit scan.
All selection, grouping and projection functions below are pure.
"""
import math
import re
from pathlib import Path

from .core import canonical, digest, require
from .resources import repository_identity

FIELDS = ("files", "lines", "characters", "bytes")
POLICY = "tracked-utf8-v1"
METHOD = ("Count each recorded repository identity + commit + counting policy once. "
          "Clones with the same conventional origin and commit share a snapshot; linked "
          "worktrees share local identity. Different commits and forks remain separate. "
          "Conflicting or unqualified observations are excluded, not assumed zero. "
          "Workspace and alias rows overlap: do not add them together. These are retained "
          "observations, not a live scan, resource lock or execution evidence.")


def configuration(repo):
    return digest({"path": repo.get("path"), "ref": repo.get("ref")})


def observe_identity(repo):
    """Explicit scan only. No source files, remote requests or raw URLs retained."""
    observed = repository_identity(repo.get("path"))
    local = next((k for k in observed["keys"] if k.startswith("repo-local:")), None)
    remote = next((k for k in observed["keys"] if k.startswith("repo-remote:")), None)
    try:
        checkout = digest(str(Path(repo["path"]).resolve(strict=True))) if local else None
    except (OSError, TypeError, ValueError):
        checkout = None
    return {"version": 1, "configurationHash": configuration(repo), "checkoutHash": checkout,
            "localKey": local, "remoteKey": remote,
            "status": "observed" if local and remote and checkout else "local_only" if local and checkout else "unavailable"}


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def candidates(state, workspace_id="selected"):
    """Latest recorded observation per configured repository; no healthy fallback."""
    configured = {r["id"]: r for r in state["repositories"]}
    latest, invalid_times = {}, set()
    for metric in state["metrics"]:
        rid = metric.get("repository")
        if rid not in configured:
            continue
        if not number(metric.get("at")):
            invalid_times.add(rid)
            continue
        prior = latest.get(rid)
        if prior is None or metric["at"] > prior[0]["at"]:
            latest[rid] = (metric, False)
        elif metric["at"] == prior[0]["at"] and canonical(metric) != canonical(prior[0]):
            # Neither equal-time claim is more current. Preserve a deterministic row
            # for inspection, but do not silently choose its numbers for totals.
            latest[rid] = (min((metric, prior[0]), key=canonical), True)
    rows = []
    for rid, repo in sorted(configured.items()):
        metric, tied = latest.get(rid, ({"repository": rid, "at": None, "commit": None,
            "status": "unavailable", "groups": {}, **{k: None for k in FIELDS}}, False))
        row = {**metric, "workspaceId": workspace_id, "configurationHash": configuration(repo)}
        row["selectionIssues"] = ["equal_time_observations_conflict"] if tied else []
        if rid in invalid_times: row["selectionIssues"].append("observation_time_invalid")
        if row.get("at") is None: row["selectionIssues"].append("observation_missing")
        rows.append(row)
    return rows


def validate(row):
    issues = list(row.get("selectionIssues", []))
    if row.get("status") != "measured": issues.append("measurement_unavailable")
    if row.get("measurementPolicy") != POLICY: issues.append("identity_refresh_required")
    if not isinstance(row.get("commit"), str) or not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", row["commit"]):
        issues.append("commit_unavailable")
    identity = row.get("identity")
    shape = {"version", "configurationHash", "checkoutHash", "localKey", "remoteKey", "status"}
    if not isinstance(identity, dict) or set(identity) != shape:
        issues.append("identity_refresh_required")
    else:
        sha = lambda v: isinstance(v, str) and re.fullmatch(r"[a-f0-9]{64}", v)
        local = lambda v: isinstance(v, str) and re.fullmatch(r"repo-local:[a-f0-9]{64}", v)
        remote = lambda v: isinstance(v, str) and re.fullmatch(r"repo-remote:[a-f0-9]{64}", v)
        if (type(identity["version"]) is not int or identity["version"] != 1 or
                not sha(identity["checkoutHash"]) or not sha(identity["configurationHash"]) or
                not local(identity["localKey"]) or
                not ((identity["status"] == "observed" and remote(identity["remoteKey"])) or
                     (identity["status"] == "local_only" and identity["remoteKey"] is None))):
            issues.append("identity_refresh_required")
        if identity["configurationHash"] != row["configurationHash"]:
            issues.append("repository_configuration_changed")
    groups = row.get("groups")
    valid = all(type(row.get(k)) is int and 0 <= row[k] <= 2**53-1 for k in FIELDS)
    valid = valid and isinstance(groups, dict) and set(groups) <= {"source", "tests", "docs", "config/data"}
    if valid:
        valid = all(isinstance(g, dict) and set(g) == set(FIELDS) and
                    all(type(g[k]) is int and 0 <= g[k] <= 2**53-1 for k in FIELDS) for g in groups.values())
    if valid: valid = all(sum(g[k] for g in groups.values()) == row[k] for k in FIELDS)
    if not valid: issues.append("invalid_measurement")
    return sorted(set(issues))


def summarize(rows):
    """One deterministic grouping for workspace, portfolio and exported counts."""
    require(len(rows) <= 10000, "Portfolio metric projection exceeds 10,000 repository rows")
    rows = [{**r, "counting": {"status": "excluded", "issues": validate(r)}} for r in rows]
    rows.sort(key=lambda r: (r["workspaceId"], r["repository"]))
    origins = {}
    for row in rows:
        if row["counting"]["issues"]: continue
        identity = row["identity"]
        origins.setdefault(identity["localKey"], set())
        if identity["remoteKey"]: origins[identity["localKey"]].add(identity["remoteKey"])
    groups = {}
    for row in rows:
        if row["counting"]["issues"]: continue
        identity = row["identity"]; remotes = origins[identity["localKey"]]
        if len(remotes) > 1:
            row["counting"]["issues"] = ["shared_local_origin_conflict"]
            continue
        remote = next(iter(remotes), None)
        key = (remote or identity["localKey"], row["commit"], row["measurementPolicy"])
        groups.setdefault(key, []).append(row)
    snapshots = []
    for key, aliases in sorted(groups.items()):
        vectors = {canonical({**{k: r[k] for k in FIELDS}, "groups": r["groups"]}) for r in aliases}
        conflict = len(vectors) != 1
        snapshot_id = digest(key)
        for index, row in enumerate(aliases):
            row["counting"] = {"status": "excluded" if conflict else "included" if not index else "alias",
                               "snapshotId": snapshot_id, "issues": ["conflicting_snapshot_measurements"] if conflict else []}
        snapshots.append({"id": snapshot_id, "commit": key[1], "measurementPolicy": key[2],
            "identityBasis": "conventional_origin" if key[0].startswith("repo-remote:") else "local_common_directory",
            "status": "conflict" if conflict else "counted", "observedAt": max(r["at"] for r in aliases),
            "aliases": [{"workspaceId": r["workspaceId"], "repository": r["repository"], "observedAt": r["at"]} for r in aliases],
            **{k: None if conflict else aliases[0][k] for k in FIELDS}})
    counted = [s for s in snapshots if s["status"] == "counted"]
    excluded = [r for r in rows if r["counting"]["status"] == "excluded"]
    coverage = {"status": "partial" if excluded else "recorded" if counted else "unavailable",
        "configuredRows": len(rows), "excludedRows": len(excluded),
        "duplicateAliases": sum(r["counting"]["status"] == "alias" for r in rows),
        "conflictingSnapshots": sum(s["status"] == "conflict" for s in snapshots),
        "localOnlySnapshots": sum(s["identityBasis"] == "local_common_directory" for s in counted),
        "refreshRequired": bool(excluded),
        "issues": [{"workspaceId": r["workspaceId"], "repository": r["repository"], "codes": r["counting"]["issues"]} for r in excluded]}
    return {"aggregate": {**{k: sum(s[k] for s in counted) if counted else None for k in FIELDS},
                          "measuredRepositories": len(counted), "uniqueRepositorySnapshots": len(snapshots)},
            "repositories": rows, "snapshots": snapshots, "coverage": coverage, "method": METHOD}
