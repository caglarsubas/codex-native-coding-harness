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
  roadmap:["Roadmap", "Published plans, recorded milestones and separate proposals."]
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

const roadmapOpen = new Set();
function roadmapChecklist(root,items,proposal=false) {
  if(!items.length){root.append(el('p','Checklist completion not available — this source uses narrative or tables, not checkboxes.','metric-note'));return;}
  const done=items.filter(i=>i.checked).length;
  root.append(el('p',`${done} / ${items.length} ${proposal?'proposal checkboxes marked':'source checkboxes marked complete'} · ${Math.round(100*done/items.length)}% of this checklist only`,'metric-note'));
  const progress=el('progress');progress.max=items.length;progress.value=done;progress.setAttribute('aria-label','Source checklist completion, not project acceptance');root.append(progress);
  const details=el('details');details.append(el('summary','Read checklist items'),table(['Recorded state','Item','Section / line'],items.map(i=>[i.checked?'Marked complete':'Open',i.label,textCell(i.section,'Line '+i.line)])));root.append(details);
}
function roadmapTables(root,tables) {
  for(const t of tables){
    root.append(el('h4',t.heading+' · line '+t.line),table(t.headers,t.rows));
    if(t.omittedRows)root.append(el('p',t.omittedRows+' rows omitted or unsupported. Read the retained source for the complete table.','muted'));
  }
}
function roadmapDocument(root,plan,proposal=false,index=0) {
  const key=(workspaceId||'')+':'+plan.repository+':'+plan.path;
  const details=el('details',null,'roadmap-document');details.open=roadmapOpen.has(key)||(!proposal&&index===0&&!roadmapOpen.has(key+':closed'));
  details.addEventListener('toggle',()=>{if(!details.isConnected)return;if(details.open){roadmapOpen.add(key);roadmapOpen.delete(key+':closed');}else{roadmapOpen.delete(key);roadmapOpen.add(key+':closed');}});
  details.append(el('summary',plan.title||plan.path.split('/').pop()));
  details.append(el('p',plan.repository+' · '+(proposal?'Private proposal · not published':(plan.ref||'Configured Git ref')+' · '+(plan.commit?.slice(0,12)||'revision unavailable'))+' · observed '+when(plan.at),'muted'));
  root.append(details);
  if(plan.status!=='observed'){details.append(el('p','Source unavailable: '+(plan.reason||'No observation retained.')));return details;}
  const content=plan.content;
  if(!content)details.append(el('p','Legacy snapshot: refresh local observations to classify current sections and historical checkpoints. No table is assumed current.','muted'));
  const items=(plan.items||[]).filter(i=>i.scope!=='historical');
  if(content?.classificationComplete===false)details.append(el('p','Checklist summary withheld until the source mapping is repaired. Read the retained source.','metric-note'));
  else roadmapChecklist(details,items,proposal);
  if(content){
    for(const issue of content.issues)details.append(el('p',issue,'muted'));
    if(content.highlights.length){
      details.append(el('h3',proposal?'Proposal excerpts — not adopted':'Current sections — as recorded in this source'));
      for(const h of content.highlights){
        details.append(el('h4',h.heading+' · line '+h.line));
        // Tables have their own readable rendering below, with the same source lines.
        const prose=h.text.split('\n').filter(line=>!line.trim().startsWith('|')).join('\n').trim();
        if(prose)details.append(el('p',prose,'roadmap-excerpt'));
        if(h.truncated)details.append(el('p','Excerpt shortened. Read the full retained source.','muted'));
      }
    }
    roadmapTables(details,content.tables.filter(t=>t.scope==='current'));
    const other=content.tables.filter(t=>t.scope==='document');
    if(other.length){const d=el('details');d.append(el('summary','Other source tables · currency not classified'));roadmapTables(d,other);details.append(d);}
    const historical=content.tables.filter(t=>t.scope==='historical'),oldItems=(plan.items||[]).filter(i=>i.scope==='historical');
    if(content.historyStart){const d=el('details');d.append(el('summary','Historical checkpoints · not current status'),el('p','The configured history boundary starts at line '+content.historyStart+'. Historical claims are excluded from the checklist above.','muted'));roadmapTables(d,historical);if(oldItems.length)roadmapChecklist(d,oldItems,proposal);if(!historical.length&&!oldItems.length)d.append(el('p','Read the source to inspect historical narrative checkpoints.'));details.append(d);}
    if(content.omittedTables||content.omittedHighlights)details.append(el('p','Display limits reached: '+content.omittedTables+' tables and '+content.omittedHighlights+' excerpts omitted. Read the full source.','muted'));
  }else if(plan.statusTable){const d=el('details');d.append(el('summary','Previously captured table · currency unknown'),table(plan.statusTable.headers,plan.statusTable.rows));details.append(d);}
  if(proposal)details.append(el('p','Retaining or reading this proposal does not publish it, approve a packet or start development.','muted'));
  const actions=el('div',null,'inline-actions');
  actions.append(button('Read source'+(plan.documentVersion?' · v'+plan.documentVersion:''),()=>navigateView('artifacts',plan.documentId)));
  details.append(actions);
  const current=state.observations.artifacts.find(a=>a.id===plan.documentId);
  const versions=current?state.observations.artifacts.filter(a=>a.key===current.key):[];
  if(versions.length>1){const d=el('details');d.append(el('summary','Retained source versions · '+versions.length));for(const a of versions)d.append(button('Read v'+a.version+' · '+when(a.observedAt),()=>navigateView('artifacts',a.id)));details.append(d);}
  return details;
}
function roadmapReviewPlay(root) {
  const workspace=state.workspace, standard=state.standard;
  if(!workspace)return;
  if(workspace.projectProfile!=='standard'){
    root.append(section('Review & Play','Unavailable for this project'));
    root.append(el('p','This project is not configured for the cooperative standard policy. Roadmap records remain read-only; they cannot opt a Harness or other project into standard Play.','muted'));
    return;
  }
  const mission=state.mission, document=mission?.document, delegated=document?.spec?.authority?.approvalMode==='phase_delegated';
  const catalog=standard?.catalog;
  const run=standard?.run;
  root.append(section('Review & Play','Prepare one bounded next phase — never the whole roadmap.'));
  const panel=el('section',null,'detail roadmap-review-play');
  if(run){
    panel.append(el('h3','A cooperative phase is already recorded'),el('p','Review, Pause and checkpoint controls for this exact phase remain on Overview. A roadmap item cannot restart it, reset its allowance, or authorize another phase.','muted'));
    panel.append(button('Open current phase',()=>navigateView('overview')));
  }else{
    panel.append(el('h3',standard?.available?'Ready to review Play':'Review the prerequisites first'));
    panel.append(el('p','Reviewing a mission does not start work. After the separate Review Play preview, the owner must explicitly confirm the exact phase, observed-usage boundary, limits and recorded model/effort catalog.','muted'));
    const phaseState=mission?.effectiveStatus==='reviewed'&&document?'Reviewed exact phase':'Missing: review an exact mission phase';
    const catalogState=catalog?'Recorded native model/effort catalog':'Missing: the designated brain must record the native catalog';
    panel.append(table(['Prerequisite','Recorded state'],[
      ['Project policy','Standard cooperative project'],
      ['Exact mission',phaseState],
      ['Phase delegation',delegated?'Phase-delegated authority recorded':'Missing: phase-delegated authority is required'],
      ['Native catalog',catalogState],
      ['Dispatch / run',state.meta.paused?'Paused · no run started':'Resolve dispatch state before review']
    ]));
    if(standard?.blocker)panel.append(el('p','Current gate: '+standard.blocker,'checkpoint'));
    const actions=el('div',null,'inline-actions');
    actions.append(button('Review mission & prerequisites',()=>navigateView('mission')));
    if(standard?.available)actions.append(button('Open Review Play',()=>navigateView('overview'),'primary'));
    panel.append(actions);
  }
  root.append(panel);
}
function roadmap(root) {
  observationFilters(root);
  const data=state.observations.roadmaps,plans=data.plans.filter(inRepo),drafts=(data.drafts||[]).filter(inRepo);
  root.append(el('p','Source claims, not execution authority. Published documents, historical checkpoints and private proposals remain separate. No item is automatically approved or completed.','roadmap-boundary'));
  roadmapReviewPlay(root);
  root.append(section('Published roadmap sources',plans.filter(p=>p.status==='observed').length+' / '+plans.length+' configured sources readable · '+drafts.length+' configured private proposals'));
  root.append(el('p','Coverage is limited to explicitly configured sources; linked documents and Codex conversations are not imported automatically. Git refs may be stale; the observation time is not a publication date.','muted'));
  if(!plans.length)root.append(empty('No published roadmap sources configured','Add the repository-relative Markdown paths in observations.json. Narrative plans and tables are supported; checkboxes are optional.'));
  const documents=el('div');
  const rows=plans.map((plan,index)=>{const panel=roadmapDocument(documents,plan,false,index);return [button(plan.title||plan.path,()=>{panel.open=true;roadmapOpen.add((workspaceId||'')+':'+plan.repository+':'+plan.path);panel.scrollIntoView({block:'start'});panel.querySelector('summary').focus();}),plan.repository,plan.status==='observed'?'Readable':'Unavailable',plan.commit?.slice(0,12)||'Unknown'];});
  if(rows.length)root.append(table(['Document','Repository','Coverage','Source revision'],rows));
  root.append(documents);
  root.append(section('Private proposals — not published','Separate from the published roadmap and its completion counts.'));
  if(!drafts.length)root.append(el('p','No private proposals configured. This does not mean no drafts exist in Codex. An operator can add an exact Markdown path from an approved artifact root to roadmapDrafts in observations.json.','muted'));
  drafts.forEach((p,index)=>roadmapDocument(root,p,true,index));
}

setInterval(() => {
  if (autoObserve && connected && !selected && !busy && document.visibilityState === "visible" && state.observationJob?.status !== "running" && Date.now() - lastAutoAttempt > 60000) {
    lastAutoAttempt=Date.now(); observe(false, true);
  }
}, 5000);
