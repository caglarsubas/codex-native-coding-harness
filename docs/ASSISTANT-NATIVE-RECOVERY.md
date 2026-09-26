# Assistant and desktop delivery qualification — 2026-09-27

## Diagnosed separately

- An app update moved the installed CLI into a nested `CodexCLI.app` bundle.
  The previous native backend startup path no longer existed. The compatibility
  resolver accepts only the signed replacement in the same known desktop bundle.
- `codex queue` acknowledged a real unloaded desktop brain without starting a
  turn. Loading that exact existing chat consumed the already saved notification;
  no resend was needed. An optional background desktop-open step now composes
  with the existing one-shot queue claim for standard projects only.
- The advisory assistant used an external tunnel to reach an engine running on
  the same Mac. The original screenshot question failed on that route. The same
  tenant key and configured model succeeded through explicit literal loopback.
- Local generation can legitimately exceed the old 90-second socket timeout.
  The successful rendered request took about 101 seconds, including about 92
  seconds to first token. The client now budgets its existing 240-second window
  across reads rather than failing at 90 seconds or renewing a timeout per chunk.
- Basic control guidance and exact brain messages unnecessarily depended on an
  advisory generation. They now prepare the existing signed confirmations without
  inference. Natural-language advice still uses the configured local service.

## Live evidence, not merely queue acknowledgment

The configured local dashboard and unchanged Compose gateway were exercised
through browser sign-in, not bypassed with a backend-only request:

1. The original question about the last phase returned a validated advisory
   answer, source navigation and 8,025 service-reported tokens. This is a single
   successful request, not a performance SLA or complete usage/billing accounting.
2. An exact read-only brain diagnostic was confirmed in the assistant. Queue
   acknowledgment alone left the task unloaded; native navigation started it.
   Its independently observed completed turn retained a dashboard reply and
   released the designated controller.
3. After enabling the background-open companion, a second preparation-only
   request was confirmed in the dashboard. Its desktop-open request succeeded;
   the native turn started approximately three seconds after submission. The
   brain checked four configured roadmap sources against `origin/main` at
   `9792cf0b794a`, reused mission v10 unchanged, retained a reply, and released.
   This second task was already loaded; the cold-task diagnosis and native-open
   recovery in step 2 are separate evidence, not a second cold-start claim.
4. The real mission remained draft, with no new Play, worker, merge or budget
   reset. Prior blocked-run usage and its gap were preserved. Source correctness,
   PR merge, this local installation and strict Harness qualification are separate.

The separately explored owned app-server host did not expose working desktop
native task tools and was not adopted. Its unused test process was stopped.
No app database edits, private API, background dispatcher, skill installation,
GitHub Actions or paid service was introduced.

## Local verification

- Complete Python discovery: **1,773 tests**, successful; one optional pinned
  Graphify subprocess integration skipped because no reviewed executable was
  configured. Runtime downloads were not used to fill that optional gap.
- All **27 JavaScript suites**, browser-script syntax checks, Python compilation
  and `git diff --check` passed on the final source.
- GitHub workflow inventory was inspected read-only before publication: zero
  configured workflows. No job was dispatched, rerun or added.

Automated coverage includes signed CLI relocation, signature/path failures,
exact deep-link target, one-shot acknowledgment/open behavior, uncertain delivery,
strict-project exclusion, late SSE completion, explicit loopback configuration,
unchanged authority facts in compact prompts, authenticated exact-text previews,
project/session isolation, stale/replayed confirmations and retained owner text.

Rendered disposable-ledger verification used **no inference and no native
notifier**: “Help me continue development” prepared mission review, `confirm
review` did not start Play, a second starter prepared Play, `confirm play` recorded
the synthetic run, and “Pause the project safely” plus `confirm pause` fenced new
work. Missing usage stayed unknown; unavailable fixture delivery was not shown
as a completed brain receipt. These are control/UI tests, not native worker
execution or settled-Pause qualification.

See [assistant workflow](ASSISTANT-LED-WORKFLOW.md) for operator controls and
[inference configuration](INFERENCE.md) for transport and data boundaries.
