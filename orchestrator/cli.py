"""Machine-readable brain ledger; optional fixed native notification on dashboard answers."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid

from .core import Ledger, Refusal, canonical
from .repository import aggregate, measure, prepare_packet, report, verify_git_inputs

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--platform", type=Path, help="Private workspace registry directory")
    parser.add_argument("--workspace", help="Exact registered workspace ID; never inferred from cwd")
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("status", "inbox", "process", "scan", "export", "inference-check", "inference-status", "readiness", "doctor", "rehearse"):
        sub.add_parser(name)
    for name in ("workspace-list", "workspace-verify-backup", "workspace-profile"):
        sub.add_parser(name)
    sub.add_parser("platform-resources", help="Explicit read-only repository identity and ownership audit; not admission")
    sub.add_parser("platform-enrollment-preview", help="Review exact workspace enrollment scope; no writes or activation")
    sub.add_parser("platform-enrollment-status", help="Inspect retained enrollment stages and owners")
    p = sub.add_parser("platform-enroll", help="Explicit owner operation: fence legacy dispatch, never activate Play")
    p.add_argument("preview", type=Path); p.add_argument("--id", required=True); p.add_argument("--confirm", action="store_true")
    p = sub.add_parser("platform-enrollment-recover", help="Continue the exact enrollment fence without releasing owners")
    p.add_argument("id"); p.add_argument("--confirm", action="store_true")
    p = sub.add_parser("platform-adoption-preview", help="Review retained ownership and explicit canonical mappings; no import")
    p.add_argument("configuration", type=Path)
    sub.add_parser("platform-adoption-status", help="Inspect the historical ownership import receipt; not native activity")
    p = sub.add_parser("platform-adopt", help="Owner-confirmed quarantined ownership import; no activation or budgets")
    p.add_argument("preview", type=Path); p.add_argument("--id", required=True); p.add_argument("--confirm", action="store_true")
    p = sub.add_parser("platform-adoption-recover", help="Recover the exact quarantined ownership import")
    p.add_argument("id"); p.add_argument("--confirm", action="store_true")
    p = sub.add_parser("platform-reconciliation-preview", help="Compare external observations with retained ownership; no state change")
    p.add_argument("evidence", type=Path)
    p = sub.add_parser("platform-reconciliation-record", help="Owner-reviewed evidence receipt; no release or activation")
    p.add_argument("preview", type=Path); p.add_argument("--id", required=True); p.add_argument("--confirm", action="store_true")
    sub.add_parser("platform-reconciliation-status", help="Inspect historical review and current evidence freshness")
    p = sub.add_parser("workspace-register"); p.add_argument("id"); p.add_argument("name"); p.add_argument("state_root", type=Path)
    p.add_argument("--apply", action="store_true", help="Register in place after a verified SQLite backup; default is preview")
    p = sub.add_parser("workspace-profile-set"); p.add_argument("profile", type=Path); p.add_argument("--version", type=int, required=True)
    sub.add_parser("mission-state", help="Read workspace mission configuration; not execution authority")
    sub.add_parser("run-readiness", help="Read-only mission/packet/platform preflight; never activation")
    p = sub.add_parser("task-contract-propose", help="Brain-only phase-bound task declaration; invalidates legacy approval, not activation")
    p.add_argument("spec", type=Path); p.add_argument("--revision", type=int, required=True); p.add_argument("--id", required=True)
    p = sub.add_parser("task-contract-state", help="Read current binding and immutable declaration history")
    p.add_argument("queue_id")
    for name in ("native-create-begin", "native-create-record", "native-create-check", "native-create-state", "native-create-recover"):
        p = sub.add_parser(name, help="Designated-brain one-use native handoff; no transport or run activation")
        p.add_argument("worker_id")
        if name in ("native-create-begin", "native-create-record"): p.add_argument("request", type=Path)
        if name == "native-create-check": p.add_argument("handoff_hash")
    for name in ("native-task-plan", "native-task-record", "native-task-state"):
        p = sub.add_parser(name, help="Read-only native observation handoff/record; no worker effects")
        p.add_argument("worker_id")
        if name == "native-task-record": p.add_argument("request", type=Path)
    p = sub.add_parser("native-account-record", help="Record native account limits; unavailable evidence fences new work")
    p.add_argument("request", type=Path)
    sub.add_parser("native-account-state", help="Read retained native account headroom; not phase token counters")
    for name in ("phase-usage-state", "phase-usage-record"):
        p = sub.add_parser(name, help="Brain-owned cumulative phase accounting; no native collection or activation")
        p.add_argument("allocation_id")
        if name.endswith("-record"): p.add_argument("request", type=Path)
    p = sub.add_parser("mission-draft", help="Designated brain proposes a version; owner reviews in the dashboard")
    p.add_argument("spec", type=Path); p.add_argument("--revision", type=int, required=True); p.add_argument("--id", required=True)
    p = sub.add_parser("native-observe"); p.add_argument("observation", type=Path)
    p = sub.add_parser("decision-publish"); p.add_argument("spec", type=Path)
    p = sub.add_parser("decision-resolve"); p.add_argument("id"); p.add_argument("result", type=Path)
    p = sub.add_parser("continuation-publish"); p.add_argument("id"); p.add_argument("spec", type=Path)
    p = sub.add_parser("brain-park"); p.add_argument("id"); p.add_argument("checkpoint", type=Path)
    p = sub.add_parser("brain-stop-observe", help="Retain bounded worker/descendant evidence for the current workspace Pause")
    p.add_argument("id"); p.add_argument("evidence", type=Path)
    p = sub.add_parser("executive-summary"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("observe"); p.add_argument("--remote", action="store_true")
    p = sub.add_parser("artifact-add"); p.add_argument("path", type=Path); p.add_argument("--repo", required=True); p.add_argument("--session"); p.add_argument("--created-at", type=float)
    p = sub.add_parser("init"); p.add_argument("config", type=Path)
    p = sub.add_parser("acquire"); p.add_argument("owner")
    p = sub.add_parser("release"); p.add_argument("checkpoint")
    p = sub.add_parser("recover"); p.add_argument("owner"); p.add_argument("observation")
    p = sub.add_parser("heartbeat"); p.add_argument("id"); p.add_argument("status", choices=["ACTIVE", "PAUSED"])
    p = sub.add_parser("prepare"); p.add_argument("manifest", type=Path); p.add_argument("--repo", required=True); p.add_argument("--catalog", required=True)
    p = sub.add_parser("prepare-seed"); p.add_argument("seed", type=Path)
    p = sub.add_parser("document"); p.add_argument("hash")
    p = sub.add_parser("command"); p.add_argument("kind"); p.add_argument("--payload", default="{}"); p.add_argument("--revision", type=int, required=True); p.add_argument("--id", default=None)
    p = sub.add_parser("preflight"); p.add_argument("queue_id"); p.add_argument("observation", type=Path); p.add_argument("--catalog", required=True)
    for name in ("reserve", "begin"):
        p = sub.add_parser(name); p.add_argument("id")
    p = sub.add_parser("bind"); p.add_argument("id"); p.add_argument("--thread-id"); p.add_argument("--client-id"); p.add_argument("--host-id", default="local")
    p = sub.add_parser("transition"); p.add_argument("id"); p.add_argument("status"); p.add_argument("note"); p.add_argument("--no-progress", action="store_true")
    p = sub.add_parser("runner"); p.add_argument("id"); p.add_argument("operation", choices=["acquire", "release"]); p.add_argument("observation")
    p = sub.add_parser("complete"); p.add_argument("id"); p.add_argument("envelope", type=Path)
    p = sub.add_parser("ack"); p.add_argument("id"); p.add_argument("result"); p.add_argument("--failed", action="store_true")
    p = sub.add_parser("pilot"); p.add_argument("id"); p.add_argument("evidence")
    p = sub.add_parser("serve"); p.add_argument("--port", type=int, default=8768)
    p.add_argument("--notify-brain", type=Path, metavar="CODEX_CLI", help="Opt in to immediate decision notification using an absolute installed Codex CLI path")
    args = parser.parse_args()
    from .workspaces import Registry
    if args.workspace and not args.platform:
        raise Refusal("--workspace requires --platform")
    if args.state and (args.workspace or args.platform):
        raise Refusal("Choose a registered workspace or --state, not both")
    if (args.action == "run-readiness" or args.action.startswith(("task-contract-", "native-create-", "native-task-", "native-account-", "phase-usage-"))) and not (args.platform and args.workspace):
        raise Refusal("This operation requires an explicit registered workspace")
    registry = Registry(args.platform, create=args.action == "workspace-register") if args.platform else None
    if args.action.startswith("platform-reconciliation-"):
        if not registry or args.workspace:
            raise Refusal("Reconciliation is platform-wide: supply --platform and omit --workspace")
        from . import reconciliation
        def evidence_input(path):
            with path.open("rb") as handle: raw = handle.read(3_000_001)
            if len(raw) > 3_000_000: raise Refusal("Evidence review exceeds its bound")
            return json.loads(raw)
        if args.action == "platform-reconciliation-preview": out = reconciliation.preview(registry, evidence_input(args.evidence))
        elif args.action == "platform-reconciliation-status": out = reconciliation.status(registry)
        else:
            if not args.confirm: raise Refusal("Explicit --confirm required; evidence review does not activate a run")
            out = reconciliation.record(registry, {"id": args.id, "confirmed": True, "preview": evidence_input(args.preview)})
        print(json.dumps(out, ensure_ascii=False, indent=2)); return
    if args.action in ("platform-adoption-preview", "platform-adoption-status", "platform-adopt", "platform-adoption-recover"):
        if not registry or args.workspace:
            raise Refusal("Ownership adoption is platform-wide: supply --platform and omit --workspace")
        from . import adoption
        def private_input(path):
            with path.open("rb") as handle:
                raw = handle.read(2_000_001)
            if len(raw) > 2_000_000: raise Refusal("Adoption input is too large")
            return json.loads(raw)
        if args.action == "platform-adoption-preview": out = adoption.preview(registry, private_input(args.configuration))
        elif args.action == "platform-adoption-status": out = adoption.status(registry)
        elif args.action == "platform-adoption-recover": out = adoption.recover(registry, args.id, confirmed=args.confirm)
        else:
            if not args.confirm: raise Refusal("Explicit --confirm required; ownership import remains quarantined")
            out = adoption.apply(registry, {"id": args.id, "confirmed": True, "preview": private_input(args.preview)})
        print(json.dumps(out, ensure_ascii=False, indent=2)); return
    if args.action in ("platform-enrollment-preview", "platform-enrollment-status", "platform-enroll", "platform-enrollment-recover"):
        if not registry or args.workspace:
            raise Refusal("Enrollment is platform-wide: supply --platform and omit --workspace")
        from . import enrollment
        if args.action == "platform-enrollment-preview": out = enrollment.preview(registry)
        elif args.action == "platform-enrollment-status": out = enrollment.status(registry)
        elif args.action == "platform-enrollment-recover": out = enrollment.recover(registry, args.id, confirmed=args.confirm)
        else:
            if not args.confirm:
                raise Refusal("Explicit --confirm is required; enrollment fences dispatch and does not activate Play")
            if args.preview.stat().st_size > 2_000_000:
                raise Refusal("Enrollment preview is too large")
            out = enrollment.apply(registry, {"id": args.id, "confirmed": args.confirm, "preview": json.loads(args.preview.read_text())})
        print(json.dumps(out, ensure_ascii=False, indent=2)); return
    if args.action == "platform-resources":
        if not registry or args.workspace:
            raise Refusal("platform-resources requires --platform and audits all workspaces; omit --workspace")
        from .resources import audit
        print(json.dumps(audit(registry), ensure_ascii=False, indent=2)); return
    if args.action.startswith("workspace-"):
        if not registry:
            raise Refusal("Workspace operations require --platform")
        if args.action == "workspace-list": out = registry.list()
        elif args.action == "workspace-register":
            out = (registry.register if args.apply else registry.preview)(args.id, args.name, args.state_root)
        elif not args.workspace: raise Refusal("Select an exact --workspace")
        elif args.action == "workspace-verify-backup": out = registry.verify_backup(args.workspace)
        elif args.action == "workspace-profile": out = registry.profile(args.workspace)
        else: out = registry.save_profile(args.workspace, json.loads(args.profile.read_text()), args.version)
        print(json.dumps(out, ensure_ascii=False, indent=2)); return
    if registry and args.action == "serve" and not args.workspace:
        from .server import serve
        workspaces = registry.list()
        if not workspaces:
            raise Refusal("Register at least one workspace before serving")
        serve(registry.ledger(workspaces[0]["id"]), args.port, notification_cli=args.notify_brain, registry=registry)
        return
    if registry and not args.workspace:
        raise Refusal("Select an exact --workspace; no default portfolio is inferred")
    ledger = registry.ledger(args.workspace) if registry else Ledger(args.state or ROOT / ".state")
    token = os.environ.get("ORCHESTRATOR_CONTROLLER_TOKEN", "")
    read = lambda path: json.loads(path.read_text())
    action = args.action
    if action == "init": out = ledger.initialize(read(args.config))
    elif action == "status":
        out = ledger.snapshot(); out["summary"] = aggregate(out)
    elif action == "inbox":
        from .decisions import inbox
        out = inbox(ledger.snapshot())
    elif action == "acquire": out = {"controllerToken": ledger.acquire(args.owner)}
    elif action == "release": out = ledger.release(token, args.checkpoint)
    elif action == "recover": out = ledger.recover(args.owner, args.observation)
    elif action == "heartbeat": out = ledger.heartbeat(args.id, args.status)
    elif action == "prepare-seed": out = ledger.prepare(read(args.seed))
    elif action == "prepare":
        repo = next(r for r in ledger.snapshot()["repositories"] if r["id"] == args.repo)
        out = ledger.prepare(prepare_packet(args.catalog, repo, read(args.manifest)))
    elif action == "document": out = ledger.document(args.hash)
    elif action == "command":
        out = ledger.submit({"id": args.id or str(uuid.uuid4()), "kind": args.kind,
            "expectedRevision": args.revision, "payload": json.loads(args.payload)}, actor="explicit_user_via_brain")
    elif action == "process": out = ledger.process(token)
    elif action == "decision-publish":
        from .decisions import publish
        out = publish(ledger, token, read(args.spec))
    elif action == "decision-resolve":
        from .decisions import resolve
        out = resolve(ledger, token, args.id, read(args.result))
    elif action == "continuation-publish":
        from .continuation import publish
        out = publish(ledger, token, args.id, read(args.spec))
    elif action == "brain-park":
        from .brain_control import park
        out = park(ledger, token, args.id, read(args.checkpoint))
    elif action == "brain-stop-observe":
        from .workspace_pause import observe
        with args.evidence.open("rb") as handle: raw = handle.read(512_001)
        if len(raw) > 512_000: raise Refusal("Pause evidence exceeds its bound")
        out = observe(ledger, token, args.id, json.loads(raw))
    elif action == "mission-state":
        from .missions import read as read_mission
        out = read_mission(ledger)
    elif action.startswith("native-create-"):
        from .admission import AdmissionStore
        from .dispatch_admission import DispatchAdmission
        from .native_creation import NativeCreation
        from .observations import read_regular
        api = NativeCreation(DispatchAdmission(registry, args.workspace, AdmissionStore(registry.root)))
        if action in ("native-create-begin", "native-create-record"):
            path = args.request.absolute()
            request = json.loads(read_regular(path, path.parent, 16000))
            out = getattr(api, action.removeprefix("native-create-"))(token, args.worker_id, request)
        elif action == "native-create-check": out = api.check(token, args.worker_id, args.handoff_hash)
        else: out = getattr(api, action.removeprefix("native-create-"))(token, args.worker_id)
    elif action.startswith("phase-usage-"):
        from .admission import AdmissionStore
        from .dispatch_admission import DispatchAdmission
        from .phase_usage import PhaseUsage
        from .observations import read_regular
        api = PhaseUsage(DispatchAdmission(registry, args.workspace, AdmissionStore(registry.root)))
        if action == "phase-usage-record":
            path = args.request.absolute()
            out = api.record(token, args.allocation_id, json.loads(read_regular(path, path.parent, 128000)))
        else: out = api.state(token, args.allocation_id)
    elif action.startswith(("native-task-", "native-account-")):
        from .admission import AdmissionStore
        from .dispatch_admission import DispatchAdmission
        from .native_supervision import NativeSupervision
        from .observations import read_regular
        api = NativeSupervision(DispatchAdmission(registry, args.workspace, AdmissionStore(registry.root)))
        if action.endswith("-record"):
            path = args.request.absolute()
            request = json.loads(read_regular(path, path.parent, 128000))
            out = api.account_record(token, request) if action == "native-account-record" else api.record(token, args.worker_id, request)
        elif action == "native-account-state": out = api.account_state(token)
        else: out = getattr(api, action.removeprefix("native-task-"))(token, args.worker_id)
    elif action == "task-contract-propose":
        from .task_contracts import propose
        with args.spec.open("rb") as handle: raw = handle.read(16001)
        if len(raw) > 16000: raise Refusal("Task contract spec exceeds 16 KiB")
        out = propose(ledger, token, {"id": args.id, "expectedRevision": args.revision, "spec": json.loads(raw)})
    elif action == "task-contract-state":
        from .task_contracts import read as read_task_contract
        out = read_task_contract(ledger, args.queue_id)
    elif action == "run-readiness":
        from .run_readiness import inspect
        if not registry or not args.workspace: raise Refusal("Run readiness requires an explicit registered workspace")
        out = inspect(registry, ledger)
    elif action == "mission-draft":
        from .missions import change
        out = change(ledger, {"id": args.id, "operation": "save", "expectedRevision": args.revision,
                             "spec": read(args.spec)}, actor="designated_brain", token=token)
    elif action == "preflight":
        state = ledger.snapshot()
        q = next(q for q in state["queue"] if q["id"] == args.queue_id)
        repo = next(r for r in state["repositories"] if r["id"] == q["repository"])
        seed = ledger.document(q["seedHash"])
        observation = read(args.observation)
        observation["checks"].update(verify_git_inputs(args.catalog, repo, seed))
        out = ledger.preflight(token, args.queue_id, observation)
    elif action == "reserve": out = ledger.reserve(token, args.id)
    elif action == "begin": out = ledger.begin_creation(token, args.id)
    elif action == "bind": out = ledger.bind(token, args.id, args.thread_id, args.client_id, args.host_id)
    elif action == "transition": out = ledger.transition(token, args.id, args.status, args.note, not args.no_progress)
    elif action == "runner": out = ledger.runner(token, args.id, args.operation, args.observation)
    elif action == "complete": out = ledger.complete(token, args.id, read(args.envelope))
    elif action == "ack": out = ledger.acknowledge(token, args.id, not args.failed, args.result)
    elif action == "pilot": out = ledger.pilot(token, args.id, args.evidence)
    elif action == "scan":
        out = []
        for repo in ledger.snapshot()["repositories"]:
            record = measure(repo); ledger.metric(record)
            out.append({k: record[k] for k in ("repository", "status", "commit", "files", "lines", "characters", "reason")})
    elif action == "observe":
        from .observations import refresh_observations
        out = refresh_observations(ledger, args.remote)
    elif action in ("readiness", "doctor", "native-observe"):
        from .readiness import collect, diagnose, native_observation
        if action == "doctor": collect(ledger)
        if action == "native-observe": out = native_observation(ledger, read(args.observation))
        else: out = diagnose(ledger)
    elif action == "rehearse":
        from .rehearsal import run
        out = run(ledger)
    elif action == "inference-check":
        from .inference import Client, settings
        out = Client(settings()).check()
    elif action == "inference-status":
        from .inference import public_status
        out = public_status(ledger)
    elif action == "executive-summary":
        from .inference import generate
        out = generate(ledger, force=args.force)
    elif action == "artifact-add":
        from .observations import register_artifact
        out = register_artifact(ledger, args.path, args.repo, args.session, args.created_at)
    elif action == "export":
        state = ledger.snapshot()
        folder = ledger.root / "reports"; folder.mkdir(exist_ok=True, mode=0o700)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:6]
        path = folder / f"portfolio-{stamp}.md"
        path.write_text(report(state)); path.with_suffix(".json").write_text(json.dumps({"state": state, "summary": aggregate(state)}, indent=2))
        out = {"markdown": str(path), "json": str(path.with_suffix(".json"))}
    elif action == "serve":
        from .server import serve
        serve(ledger, args.port, notification_cli=args.notify_brain, registry=registry); return
    print(json.dumps(out if out is not None else {"ok": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (Refusal, ValueError, OSError, KeyError, StopIteration) as error:
        print(json.dumps({"error": str(error) or "Unknown repository or queue item"}), file=sys.stderr)
        sys.exit(2)
