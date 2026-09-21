/* Read-only portfolio views. No native task tools or arbitrary file access. */
let observationRepo = "all";
let observationPage = 0;
let artifactQuery = "";
let autoObserve = false;
let lastAutoAttempt = 0;
Object.assign(titles, {
  usage:["Token usage", "Local usage by repository, task, model and reasoning effort."],
  gitStatus:["Git & delivery", "From working tree to remote branch and pull request."],
  artifacts:["Artifact library", "Read preserved outputs across tasks, in order and by version."],
  roadmap:["Roadmap", "Versioned plans and recorded checklist progress."]
});

function observationFilters(root) {
  const bar = el("div", null, "observation-toolbar");
  const label = el("label", "Repository ");
  const select = el("select");
  select.setAttribute("aria-label", "Observation repository");
  if(view!=='artifacts'&&observationRepo==='@portfolio')observationRepo='all';
  [["all", "All repositories"], ...(view==='artifacts'?[["@portfolio","Portfolio-wide reports"]]:[]), ...state.repositories.map(r => [r.id, r.id])].forEach(([id, name]) => {
    const option = el("option", name); option.value = id; select.append(option);
  });
  select.value = observationRepo;
  select.onchange = () => { observationRepo = select.value; observationPage = 0; selected = null; render(); };
  label.append(select); bar.append(label);
  const job = state.observationJob || {};
  const local = button("Refresh local observations", () => observe(false));
  const remote = button("Refresh GitHub status", () => observe(true));
  local.disabled = remote.disabled = job.status === "running";
  bar.append(local, remote);
  const autoLabel = el("label"); const auto = el("input"); auto.type="checkbox"; auto.checked=autoObserve;
  auto.onchange = () => { autoObserve=auto.checked; };
  autoLabel.append(auto, el("span", "Monitor locally every minute while visible")); bar.append(autoLabel);
  root.append(bar);
  const last = state.observations.refresh;
  root.append(el("p", job.status === "running" ? "Reading local evidence… Dispatch and heartbeat are unchanged." :
    job.status === "failed" ? "Refresh failed: " + job.error :
    "Last observation: " + when(last?.at) + ". GitHub is queried only when requested; timestamps show freshness.", "muted"));
  if (last?.errors?.length) {
    const detail = el("details", null, "coverage-details");
    detail.append(el("summary", last.errors.length + " source gaps / unavailable artifacts"));
    detail.append(table(["Source", "Reason"], last.errors.map(e => [e.path || e.source, e.reason])));
    root.append(detail);
  }
}

async function observe(remote, quiet=false) {
  try {
    await api("/api/observe", {method:"POST", headers:{"Content-Type":"application/json", "X-CSRF-Token":csrf}, body:JSON.stringify({remote})});
    if (!quiet) showNotice("Read-only refresh started. No task creation, fetch, push or merge will run.");
    await refresh();
  } catch (error) { showNotice(error.message, true); }
}

function inRepo(row) { return observationRepo === "all" || row.repository === observationRepo; }
function ratio(cached, input) { return input ? (100 * cached / input).toFixed(2) + "%" : "—"; }
function paginated(root, rows, headers, cells) {
  const pages = Math.max(1, Math.ceil(rows.length / 40));
  observationPage = Math.min(observationPage, pages - 1);
  root.append(table(headers, rows.slice(observationPage * 40, (observationPage + 1) * 40).map(cells)));
  const actions = el("div", null, "pagination");
  const previous = button("Previous", () => { observationPage--; render(); });
  const next = button("Next", () => { observationPage++; render(); });
  previous.disabled = observationPage === 0; next.disabled = observationPage === pages - 1;
  actions.append(previous, el("span", `Page ${observationPage + 1} / ${pages} · ${rows.length} records`), next);
  root.append(actions);
}

function usage(root) {
  if(state.standard?.run)standardPanel(root);else budgetView(root);
  root.append(section("Historical log analytics", "Separate from phase admission accounting. Refreshing logs does not change a budget or reconcile reservations."));
  observationFilters(root);
  const usage = state.observations.usage;
  if (!usage || usage.status === "unavailable") {
    root.append(empty("No measured token usage yet", "Configure the local Codex log source, then refresh observations. Missing usage is not zero.")); return;
  }
  root.append(callout("Local observations, not a bill", usage.reason));
  const rows = usage.repositories.filter(inRepo);
  if (!rows.some(r => r.samples > 0)) {
    root.append(empty("No attributable token records for this repository", "This is unavailable, not zero usage. Work performed by a shared brain is attributed to its task working directory, not inferred from the files it edited.")); return;
  }
  const sum = key => rows.reduce((n, r) => n + r[key], 0);
  root.append(section("Token and conversation totals", "Cached input and reasoning are subsets, not extra tokens."));
  root.append(table(["Total", "Input", "Cached input", "Cache hit rate", "Output", "Reasoning output"], [[
    num(sum("total_tokens")), num(sum("input_tokens")), num(sum("cached_input_tokens")), ratio(sum("cached_input_tokens"), sum("input_tokens")),
    num(sum("output_tokens")), num(sum("reasoning_output_tokens"))]]));
  const sessions = usage.sessions.filter(s => observationRepo === "all" || s.repositories.includes(observationRepo));
  root.append(el("p", `${num(sessions.length)} observed tasks · ${num(sessions.filter(s => !s.agent).length)} user tasks · ${num(sessions.filter(s => s.agent).length)} agent tasks · ${num(sum("userMessages"))} user messages · ${num(sum("assistantMessages"))} assistant messages`, "metric-note"));
  root.append(section("Repository distribution"));
  root.append(table(["Repository", "Input", "Cached", "Output", "Total", "Cache rate"], rows.map(r => [r.repository, num(r.input_tokens), num(r.cached_input_tokens), num(r.output_tokens), num(r.total_tokens), ratio(r.cached_input_tokens, r.input_tokens)])));
  root.append(section("Model × effort", "Per observed turn. Changing settings does not relabel earlier usage."));
  const modelTotals = new Map();
  for (const row of usage.modelEffort.filter(inRepo).filter(r => r.samples > 0)) {
    const key = row.model + " / " + row.effort;
    if (!modelTotals.has(key)) modelTotals.set(key, {input:0, cached:0, output:0, total:0});
    const target = modelTotals.get(key); target.input+=row.input_tokens; target.cached+=row.cached_input_tokens; target.output+=row.output_tokens; target.total+=row.total_tokens;
  }
  root.append(table(["Model / effort aggregate", "Input", "Output", "Total", "Cache rate"], [...modelTotals].map(([label,r]) => [label,num(r.input),num(r.output),num(r.total),ratio(r.cached,r.input)])));
  root.append(section("Model / effort repository detail"));
  root.append(table(["Repository", "Model", "Effort", "Input", "Output", "Total", "Cache rate"], usage.modelEffort.filter(inRepo).filter(r => r.samples > 0).map(r => [r.repository, r.model, r.effort, num(r.input_tokens), num(r.output_tokens), num(r.total_tokens), ratio(r.cached_input_tokens, r.input_tokens)])));
  root.append(section("Tasks", "Newest activity first. Task totals include all observed repositories for that task."));
  paginated(root, [...sessions].sort((a,b) => b.lastAt-a.lastAt), ["Task / kind", "Repository", "Model / effort", "Tokens", "Messages", "Latest activity"], s => [
    textCell(s.id, s.agent ? "Agent task" : "User task"), s.repositories.join(", "), s.models.join(", "), num(s.total_tokens), `${num(s.userMessages)} user / ${num(s.assistantMessages)} assistant`, when(s.lastAt)]);
  const coverage = usage.coverage;
  if (observationRepo === "all") {
    root.append(section("Daily usage", "Latest 14 observed UTC dates across this portfolio."));
    root.append(table(["UTC date", "Input", "Output", "Total", "Cache rate"], usage.days.slice(-14).reverse().map(d => [d.day,num(d.input_tokens),num(d.output_tokens),num(d.total_tokens),ratio(d.cached_input_tokens,d.input_tokens)])));
  }
  root.append(section("Coverage diagnostics"), el("p", `${coverage.missingPrefixes} missing prefixes · ${coverage.counterResets} counter resets · ${coverage.ambiguousDeltas} ambiguous deltas · ${coverage.repeatedCountersIgnored} repeated counters ignored · ${coverage.malformed} malformed records · ${coverage.oversized} oversized records · ${coverage.invalidUsage} unsupported usage records`, "muted"));
  root.append(el("p", "For a cache fraction c and cached/uncached price ratio r, input-only savings are c × (1 − r). At 97.5% caching and a hypothetical 10% cached-input price, input savings are 87.75%; output and subscription charges are not included.", "metric-note"));
}

function gitStatus(root) {
  observationFilters(root);
  const records = state.observations.git.filter(inRepo);
  if (!records.length) { root.append(empty("No Git observations yet", "Refresh to read registered worktrees, branches and commits. GitHub status is an explicit read-only request.")); return; }
  root.append(callout("Commit, push and merge are separate", "Local tracking refs can be stale. A remote SHA match proves the remote contains that branch tip, not who pushed it. A merged PR does not prove CI, deployment or tenant acceptance. GitHub lists are bounded to the 100 most recently updated PRs and first 100 branches per repo."));
  root.append(section("Repository observations"));
  root.append(table(["Repository", "Local state", "Worktrees", "Branches", "GitHub", "Remote observed"], records.map(r => [r.repository,badge(r.status),num(r.worktrees.length),num(r.branches.length),textCell(r.remoteStatus === "not_requested" ? r.previousRemote?.remoteStatus || "not_requested" : r.remoteStatus,r.reason),when(r.remoteAt || r.previousRemote?.remoteAt)])));
  root.append(section("Worktrees"));
  root.append(table(["Repository / observed", "Worktree", "Branch", "Commit", "Working tree"], records.flatMap(r => r.worktrees.length ? r.worktrees.map(w => [textCell(r.repository, when(r.at)), w.path, w.branch, w.commit?.slice(0,12) || "—", badge(w.status)]) : [[r.repository, r.reason || "Unavailable", "—", "—", badge("unavailable")]])));
  root.append(section("Branches & push observations"));
  root.append(table(["Repository / branch", "Local commit", "Upstream / cached divergence", "Remote comparison", "Remote observed"], records.flatMap(r => r.branches.map(b => {
    const prior = r.previousRemote;
    const old = prior?.branches?.find(p => p.branch === b.branch);
    const remoteCommit = b.remoteCommit || old?.remoteCommit;
    const status = remoteCommit ? (remoteCommit === b.commit ? "matches_remote" : "differs_remote") : b.pushStatus;
    return [textCell(r.repository, b.branch), b.commit.slice(0,12), textCell(b.upstream || "No upstream", b.tracking || "No divergence recorded"), status, when(r.remoteAt || prior?.remoteAt)];
  }))));
  root.append(section("Pull requests", "Open, closed and merged remain distinct; exact merge commits are shown when available."));
  const pulls = records.flatMap(r => (r.remoteAt ? r.pullRequests : r.previousRemote?.pullRequests || []).map(p => ({...p, repository:r.repository, at:r.remoteAt || r.previousRemote?.remoteAt})));
  if (!pulls.length) root.append(el("p", "No retained PR observations. Use Refresh GitHub status; unavailable authentication or network is reported explicitly.", "muted"));
  else paginated(root, pulls, ["PR / repository", "Branch / head", "State", "Merge commit", "Observed"], p => {
    const link = el("a", `#${p.number} ${p.title}`);
    if (/^https:\/\/github\.com\//.test(p.url)) { link.href=p.url; link.target="_blank"; link.rel="noopener noreferrer"; }
    const name = el("div"); name.append(link, el("span", p.repository, "subline"));
    return [name, textCell(p.branch, p.head.slice(0,12)), badge(p.draft ? p.state + " · draft" : p.state), p.mergeCommit?.slice(0,12) || "—", when(p.at)];
  });
}

function artifactReader(root, identity) {
  const panel = el("section", null, "artifact-reader");
  panel.tabIndex=-1;
  panel.append(section("Artifact reader", "Immutable captured bytes. Active HTML/SVG is shown as source, never executed."));
  const pre = el("pre", "Loading preserved version…");
  const download = el("a", "Download this version", "button"); download.href=workspacePath("/api/artifacts/" + identity + "/download"); download.download="";
  panel.append(download, button("Close reader", () => { selected=null; render(); }), pre); root.append(panel);
  api("/api/artifacts/" + identity).then(result => {
    pre.textContent = result.text === null ? "Binary artifact. Download the preserved file to read it in its native application." : result.text;
    panel.prepend(el("h3", result.metadata.name + " · version " + result.metadata.version));
    panel.append(el("p", "SHA-256 " + result.metadata.sha256 + (result.truncated ? " · preview limited to 500,000 characters" : ""), "subline"));
  }).catch(error => { pre.textContent=error.message; });
}

function artifacts(root) {
  observationFilters(root);
  root.append(callout("A versioned library, with honest history", "Files linked by scoped local tasks and explicitly registered artifacts are captured from allowlisted roots. Ordered by supplied creation date, otherwise earliest retained reference or first observation. Existing bytes cannot reconstruct overwritten historical versions. Missing files remain coverage gaps. Native attachments without local references are not automatically included."));
  const search = el("input"); search.type="search"; search.placeholder="Filter by artifact name or task ID"; search.value=artifactQuery; search.setAttribute("aria-label", "Filter artifacts");
  const filter = button("Apply filter", () => { artifactQuery=search.value; observationPage=0; render(); });
  const controls = el("div", null, "observation-toolbar"); controls.append(search, filter); root.append(controls);
  const rows = state.observations.artifacts.filter(inRepo).filter(a => !artifactQuery || (a.name + " " + a.references.map(r => r.session).join(" ")).toLowerCase().includes(artifactQuery.toLowerCase()));
  root.append(section("Creation / reference order", rows.length + " retained versions · oldest first"));
  paginated(root, rows, ["Artifact / repository", "Version", "Order date / basis", "Captured", "Task references"], a => {
    const generated=['local_inference_advisory','synthetic_lifecycle_rehearsal'].includes(a.provenance);
    const name = textCell(a.name, a.repository==='@portfolio'?'Portfolio-wide':a.repository); name.append(button("Read v" + a.version, () => { selected=a.id; render(); }));
    return [name, "v" + a.version, textCell(when(a.orderAt), generated?"Generated report":a.createdAt ? "Supplied creation time" : a.references.length ? "First retained reference" : "First observed"), when(a.observedAt), [...new Set(a.references.map(r => r.session).filter(Boolean))].join(", ") || (generated?'Local report · not a native task':"Not linked")];
  });
  if (selected) artifactReader(root, selected);
}

function roadmap(root) {
  observationFilters(root);
  const plans = state.observations.roadmaps.plans.filter(inRepo);
  root.append(callout("Recorded progress is not execution authority", "Checklists are read from configured Git revisions. A checked item is the plan author's recorded claim, not independent acceptance. Update the plan in its repository; this view never approves work or checks off items automatically."));
  if (!plans.length) { root.append(empty("No roadmap sources configured", "Add explicit repository-relative Markdown checklist paths in observations.json. Plans without checkboxes remain readable source documents.")); return; }
  for (const plan of plans) {
    root.append(section(plan.title || plan.path, plan.repository + " · " + (plan.commit?.slice(0,12) || "unavailable") + " · " + when(plan.at)));
    if (plan.status === "unavailable") { root.append(el("p", plan.reason, "muted")); continue; }
    const done = plan.items.filter(i => i.checked).length;
    root.append(el("p", `${done} / ${plan.items.length} recorded complete${plan.items.length ? " · " + Math.round(100 * done / plan.items.length) + "%" : " · no Markdown checkboxes in this source"}`, "metric-note"));
    if (plan.items.length) {
      const progress = el("progress"); progress.max=plan.items.length; progress.value=done; progress.setAttribute("aria-label", "Recorded checklist completion"); root.append(progress);
      root.append(table(["Recorded state", "Checklist item", "Section / line"], plan.items.map(item => [item.checked ? "☑ Recorded complete" : "☐ Open", item.label, textCell(item.section, "Line " + item.line)])));
    }
    if (plan.statusTable) {
      root.append(el("p", "First status table, recorded verbatim; older tables are not combined.", "metric-note"));
      root.append(table(plan.statusTable.headers, plan.statusTable.rows));
    }
    root.append(button("Read plan source", () => { selected=plan.documentId; render(); }));
  }
  if (selected) artifactReader(root, selected);
}

setInterval(() => {
  if (autoObserve && connected && !selected && !busy && document.visibilityState === "visible" && state.observationJob?.status !== "running" && Date.now() - lastAutoAttempt > 60000) {
    lastAutoAttempt=Date.now(); observe(false, true);
  }
}, 5000);
