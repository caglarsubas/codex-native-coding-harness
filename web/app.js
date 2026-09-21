"use strict";
const $ = (id) => document.getElementById(id);
let state = null, csrf = null, view = "overview", selected = null, busy = false, connected = false;
const titles = {overview:["Operations overview","A clear view of what is authorized, active, and proven."],queue:["Approved queue","Approval is bound to exact packet and inheritance hashes."],workers:["Workers & evidence","Native Codex tasks. Separate ownership and acceptance states."],knowledge:["Knowledge continuity","Decisions survive the conversation. Workers inherit only what they need."],metrics:["Portfolio metrics","Aggregate and repository-level measurements, with explicit coverage."]};
function el(tag, text, cls) {const e=document.createElement(tag);if(text!==undefined&&text!==null)e.textContent=String(text);if(cls)e.className=cls;return e;}
function button(text, action, cls="") {const b=el("button",text,cls);b.type="button";b.addEventListener("click",action);return b;}
function badge(text) {return el("span",text,"badge "+(["complete","completed","verified","measured"].includes(text)?"good":["paused","blocked","unavailable","held","starting"].includes(text)?"warn":""));}
function num(n) {return n===null||n===undefined?"—":new Intl.NumberFormat().format(n);}
function when(ts) {return ts?new Date(ts*1000).toLocaleString():"Not yet observed";}
function age(ts) {return ts?Math.max(0,Math.floor((Date.now()/1000-ts)/60))+" min ago":"Never reconciled";}
function showNotice(text,error=false) {$('notice').hidden=false;$('notice').textContent=text;$('notice').dataset.error=String(error);}
function table(headers, rows) {const wrap=el("div",null,"table-wrap"),t=el("table"),head=el("thead"),tr=el("tr");headers.forEach(h=>tr.append(el("th",h)));head.append(tr);t.append(head);const body=el("tbody");rows.forEach(row=>{const r=el("tr");row.forEach(value=>{const cell=el("td");cell.append(value instanceof Node?value:el("span",value));r.append(cell);});body.append(r);});t.append(body);wrap.append(t);return wrap;}
function section(title,detail) {const e=el("div",null,"section-heading");e.append(el("h2",title));if(detail)e.append(el("p",detail));return e;}
function empty(title,body) {const e=el("div",null,"empty");e.append(el("h2",title),el("p",body));return e;}
function callout(title,body) {const e=el("div",null,"callout");e.append(el("h3",title),el("p",body));return e;}
function textCell(main,sub) {const e=el("div");e.append(el("span",main));if(sub)e.append(el("span",sub,"subline"));return e;}
async function api(path,options={}) {
 const generation=workspaceGeneration,write=options.method==='POST',global=options.global===true;
 const requestOptions={...options};delete requestOptions.global;
 if(write){workspaceWrites++;updateWorkspaceSelector();}
 try{
  const r=await fetch(global?path:workspacePath(path),{credentials:"same-origin",cache:"no-store",...requestOptions});
  const body=await r.json();
  if(generation!==workspaceGeneration&&!global){const error=new Error("Workspace changed; old response discarded");error.workspaceChanged=true;throw error;}
  if(!r.ok){const error=new Error(body.error||"Local request failed");error.status=r.status;throw error;}return body;
 }catch(error){if(generation!==workspaceGeneration&&!global)error.workspaceChanged=true;throw error;}
 finally{if(write){workspaceWrites--;updateWorkspaceSelector();}}
}
const controlRequests=new Map();
async function command(kind,payload={}) {
 if(!state||busy)return;
 if(!connected){showNotice("Refresh the local connection before issuing a control request.",true);return;}
 const key=JSON.stringify([kind,payload]);
 if(!controlRequests.has(key))controlRequests.set(key,{id:crypto.randomUUID(),kind,expectedRevision:state.meta.revision,payload});
 busy=true;
 try {
  const result=await api("/api/commands",{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify(controlRequests.get(key))});
  controlRequests.delete(key);
  const delivery=commandPresentation(result);
  showNotice(delivery.label+". "+delivery.detail);
  selected=null;await refresh();
 }catch(e){if(e.message.includes("State changed"))controlRequests.delete(key);showNotice(e.message+" Refresh before retrying; uncertain requests retain the same ID.",true);}
 finally{busy=false;render();updateWorkspaceSelector();}
}
async function refresh() {try{state=await api("/api/state");connected=true;$('connection').textContent="Ledger connected · "+new Date().toLocaleTimeString();render();}catch(e){if(e.workspaceChanged)return;connected=false;$('connection').textContent="Ledger disconnected";showNotice(e.message,true);$('pause').disabled=true;$('reconcile').disabled=true;}finally{if(typeof assistantConnectionChanged==='function')assistantConnectionChanged();}}
function overview(root) {
 const m=state.meta,active=state.workers.filter(w=>!['complete'].includes(w.status));
 projectIntroduction(root);
 workspacePausePanel(root);
 missionSummary(root);
 workflowSummary(root);
 brainActivity(root);
 readinessSummary(root);
 runtimeSummary(root);
 executiveSummary(root);
 if(m.paused&&!state.workspace)root.append(callout("Dispatch is paused", "No new implementation tasks will be created. Existing work is not cancelled. Approve exact queue items, then request resume when their prerequisites are verified."));
 if(!m.lastReconciled||Date.now()/1000-m.lastReconciled>1800)root.append(callout("Saved checkpoint is old", "Checkpoint age is not live task status. Check Brain activity above and open the Codex task before requesting another reconciliation."));
 const strip=el("div",null,"summary-strip");[[active.length+" / "+m.concurrency,"worker slots"],[state.queue.filter(q=>q.status==='approved').length,"approved packets"],[state.repositories.length,"repositories"],[m.runner?"Reserved":"Unreserved","managed runner"]].forEach(([v,l])=>{const s=el("div");s.append(el("strong",v),el("span",l));strip.append(s);});root.append(strip);
 root.append(section("Repository readiness","Missing mappings never become automatic approvals."));
 root.append(table(["Repository","Policy","Native project","Latest measurement"],state.repositories.map(r=>{const metric=state.summary.repositories.find(x=>x.repository===r.id);return[textCell(r.id,r.mergePolicy==='manual'?"Manual merge":"Required checks before merge"),r.policyProfile,badge(r.projectId?"mapped":"unmapped"),metric?textCell(metric.status,metric.commit?.slice(0,12)||metric.reason):"Not measured"];})));
 const split=el("div",null,"split"),left=el("section"),right=el("section");left.append(section("Brain checkpoint",age(m.lastReconciled)),el("p",m.checkpoint,"checkpoint"));right.append(section("Control state"));right.append(table(["Setting","Value"],[["Heartbeat",m.heartbeat.status],["Pilot",m.pilotPassed?"Verified · two slots enabled":"Pending · one slot limit"],["Controller",m.controller?m.controller.owner:"No active cycle"],["Revision",m.revision]]));split.append(left,right);root.append(split);
}
function queue(root) {
 if(!state.queue.length){root.append(empty("No packets approved for dispatch", "A roadmap entry is not an authorization. Prepare an inheritance seed in the brain, review its scope and hashes here, then explicitly approve it. Current design blockers stay outside the executable queue."));return;}
 root.append(table(["Packet / repository","State","Priority","Inheritance","Actions"], [...state.queue].sort((a,b)=>a.priority-b.priority).map(q=>{
 const actions=el("div",null,"inline-actions");actions.append(button("Review",()=>{selected=q.id;render();}));if(['proposed','approved'].includes(q.status)){actions.append(button(q.held?"Release hold":"Hold",()=>command("hold",{queueId:q.id,held:!q.held})));const input=el("input");input.type="number";input.min="0";input.max="999";input.value=q.priority;input.setAttribute("aria-label","Priority for "+q.packetId);actions.append(input,button("Set",()=>command("prioritize",{queueId:q.id,priority:Number(input.value)})));}
 return[textCell(q.packetId,q.repository),textCell(q.held?'held':q.status,q.reason),num(q.priority),el("span",q.seedHash.slice(0,12),"mono"),actions];
 })));
 if(selected){
  const q=state.queue.find(x=>x.id===selected);if(!q)return;
  const d=el("section",null,"detail task-review");d.append(el("h3","Review "+q.packetId));taskContractPanel(d,q);
  d.append(el("p","Packet SHA-256: "+q.packetDigest,"mono"),el("p","Inheritance SHA-256: "+q.seedHash,"mono"));
  const pre=el("pre","Loading immutable seed…");d.append(pre);let loaded=false,approve=null,check=null;
  api('/api/documents/'+q.seedHash).then(doc=>{pre.textContent=JSON.stringify(doc,null,2);loaded=true;if(approve)approve.disabled=!check.checked;}).catch(e=>{pre.textContent=e.message;});
  if(canLegacyApprove(q)){
   const label=el("label");check=el("input");check.type="checkbox";label.append(check,el("span","I authorize creation of one Codex implementation task for this exact packet, inheritance seed and scope. This does not authorize additional work or policy changes."));
   approve=button("Approve this exact scope",()=>command("approve",{queueId:q.id,seedHash:q.seedHash,packetDigest:q.packetDigest}),"primary");approve.disabled=true;
   check.onchange=()=>{approve.disabled=!check.checked||!loaded;};d.append(label,approve);
  }
  d.append(button("Close review",()=>{selected=null;render();}));root.append(d);
 }
}
function canArchiveWorker(w) {return !('dispatchAdmission' in w)&&w.status==='complete'&&w.preserved&&!w.archived;}
function workers(root) {
 if(!state.workers.length){root.append(empty("No implementation workers yet", "The designated brain is separate from implementation workers. It may be planning or reconciling while this list is empty. After approval and preflight, new workers appear here."),button("View brain activity",()=>navigateView("overview")));return;}
 state.workers.forEach(w=>{const d=el("section",null,"detail");d.append(el("h3",w.packetId+" · "+w.repository),badge(w.status),el("p",w.note||"Dispatch "+w.id,"subline"));const actions=el("div",null,"inline-actions");if(w.threadId){actions.append(button("Copy Codex task ID",()=>navigator.clipboard.writeText(w.threadId).then(()=>showNotice("Task ID copied. Open the task in the native Codex sidebar."))),button("Request checkpoint",()=>command("checkpoint",{workerId:w.id})));}else d.append(el("p","Native creation pending or uncertain. Ownership remains reserved; no replacement will be launched.","muted"));if(canArchiveWorker(w))actions.append(button("Request archive",()=>{selected=w.id;render();}));if(w.pr){try{const u=new URL(w.pr);if(u.protocol==='https:'&&u.hostname==='github.com'){const a=el("a","Review pull request","button");a.href=u.href;a.target="_blank";a.rel="noopener noreferrer";actions.append(a);}}catch{}}
 d.append(actions,section("Evidence axes"));const axes=el("div",null,"axes");Object.entries(w.evidence).forEach(([axis,v])=>{const e=el("span",axis+": "+v.status);e.dataset.verified=String(v.status==='verified');e.title=v.reference||"No verified evidence";axes.append(e);});d.append(axes);if(selected===w.id&&canArchiveWorker(w)){d.append(callout("Archive this completed task?", "Archiving can trigger cleanup of a Codex-managed worktree. Only proceed after commits are pushed and evidence is preserved. This is not a stop or delete operation."),button("Confirm archive request",()=>command("archive",{workerId:w.id})));}root.append(d);});
}
function knowledge(root) {
 brainActivity(root,true);
 root.append(section("Current checkpoint",when(state.meta.lastReconciled)),el("p",state.meta.checkpoint,"checkpoint"));
 root.append(section("Immutable inheritance & results"));
 if(!state.queue.length)root.append(el("p","No seeds prepared. Each prepared seed is content-addressed; revisions invalidate prior approval.","muted"));
 state.queue.forEach(q=>{const details=el("details",null,"detail"),summary=el("summary",q.packetId+" · seed "+q.seedHash.slice(0,12)),pre=el("pre","Open to load seed");details.append(summary,pre);details.addEventListener("toggle",async()=>{if(details.open){try{pre.textContent=JSON.stringify(await api('/api/documents/'+q.seedHash),null,2);}catch(e){pre.textContent=e.message;}}});root.append(details);});
 state.workers.filter(w=>w.completionHash).forEach(w=>{const details=el("details",null,"detail"),summary=el("summary",w.packetId+" · completion "+w.completionHash.slice(0,12)),pre=el("pre","Open to load completion evidence");details.append(summary,pre);details.addEventListener("toggle",async()=>{if(details.open){try{pre.textContent=JSON.stringify(await api('/api/documents/'+w.completionHash),null,2);}catch(e){pre.textContent=e.message;}}});root.append(details);});
 root.append(section("Recent decision & state history","Latest 100 events; the durable ledger retains all events."));const list=el("ol",null,"event-list");state.events.forEach(e=>{const li=el("li");li.append(el("time",when(e.at)),el("span",e.kind.replaceAll('_',' ')),el("span",JSON.stringify(e.data),"subline"));list.append(li);});root.append(list);
}
function metrics(root) {
 const summary=state.summary.aggregate;root.append(callout("Measured text, not a productivity score", "Counts include blank and comment lines in tracked UTF-8 files. Vendor/build/generated folders, lockfiles, binaries, symlinks and files over 2 MiB are excluded. Clones and worktrees at the same identified commit count once; different commits remain separate snapshots."));
 const strip=el("div",null,"summary-strip");[[num(summary.lines),"counted physical lines"],[num(summary.characters),"Unicode characters"],[num(summary.files),"text files"],[num(summary.measuredRepositories),"counted code snapshots"]].forEach(([v,l])=>{const s=el("div");s.append(el("strong",v),el("span",l));strip.append(s);});root.append(strip);
 codeCountingCoverage(root,state.summary.coverage);
 const refreshCode=button("Refresh local observations",()=>observe(false));refreshCode.disabled=state.observationJob?.status==='running';root.append(refreshCode,el('p',state.observationJob?.status==='running'?'Reading local observations for this workspace…':state.observationJob?.status==='failed'?'Observation refresh failed. Open Git & delivery for details.':'Runs the existing local observation scan for this workspace only. No GitHub query, task dispatch or automatic refresh.','metric-note'));
 root.append(section("Repository distribution","Alias rows overlap. Do not add them together. Refresh observations explicitly to update these records."));root.append(table(["Repository / commit","Source lines","Test lines","Docs lines","All text lines","Characters","Observation / counting"],state.summary.repositories.map(m=>[textCell(m.repository,m.commit?.slice(0,12)||m.reason),num(m.groups.source?.lines),num(m.groups.tests?.lines),num(m.groups.docs?.lines),m.status==='measured'?num(m.lines):"—",m.status==='measured'?num(m.characters):"—",textCell(m.status,codeCountingLabel(m.counting))])));
 root.append(section("Managed delivery"));root.append(table(["Measurement","Value"],[["Managed tasks",num(summary.managedTasks)],["Completed packets",num(summary.completedPackets)],["Mean cycle time",summary.meanCycleSeconds===null?"Unavailable until completion":Math.round(summary.meanCycleSeconds/60)+" minutes"]]));
 if(state.delivery){root.append(table(["Repository","Tasks","Done / 7 days","Blocked minutes","Runner wait minutes","No-progress cycles"],state.delivery.repositories.map(r=>[r.repository,num(r.tasks),num(r.completedLast7Days),num(Math.round(r.blockedSeconds/60)),num(Math.round(r.runnerWaitSeconds/60)),num(r.noProgressCycles)])));}
 root.append(section("Usage & cost coverage"),el("p",state.summary.usage.reason,"muted"),el("p","Subscription charges are not inferred from API token prices. Model/effort comparisons remain observational.","subline"));
 if(state.metrics.length>state.summary.repositories.length){root.append(section("Snapshot history"));root.append(table(["Repository","Captured","Commit","Lines"],[...state.metrics].sort((a,b)=>b.at-a.at).slice(0,50).map(m=>[m.repository,when(m.at),m.commit?.slice(0,12)||"—",m.status==='measured'?num(m.lines):"—"])));}
}
function render() {
 if(!state)return;
 document.querySelector(".page-actions").hidden=['workspaces','mission','runReadiness'].includes(view);
 const m=state.meta,dispatch=dispatchPresentation(m,state.commands),primary=state.workspace?workspacePausePresentation(state):dispatch;
 $('mode').textContent=dispatch.label+" · Brain: "+activityLabel(state.brainActivity)+" · Checkpoint: "+age(m.lastReconciled)+" · Heartbeat (recorded): "+m.heartbeat.status;
 $('pause').textContent=primary.button;$('pause').disabled=!connected||busy||primary.disabled;
 $('pause').title=state.workspace?primary.detail:"Change new worker dispatch only";
 $('pause').classList.toggle('primary',!!state.workspace);$('reconcile').classList.toggle('primary',!state.workspace);
 $('reconcile').disabled=!connected||busy;$('title').textContent=titles[view][0];$('subtitle').textContent=titles[view][1];
 const root=$('content');root.replaceChildren();
 ({overview,decisions,queue,workers,knowledge,metrics,usage,gitStatus,artifacts,roadmap,readiness,mission:missionView,runReadiness:runReadinessView,workspaces:allWorkspaces})[view](root);
 if(!['workspaces','mission','runReadiness'].includes(view)&&state.commands.length){root.append(section("Control requests","Delivery, brain receipt and completion are separate."));root.append(table(["Request","Status","Result"],[...state.commands].reverse().slice(0,8).map(c=>{const delivery=commandPresentation(c);return [textCell(c.kind,when(c.createdAt)),badge(delivery.label),delivery.detail];})));}
}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>navigateView(b.dataset.view)));
$('pause').onclick=()=>command(state.workspace?workspacePausePresentation(state).kind:state.meta.paused?'resume':'pause');$('reconcile').onclick=()=>command('reconcile');$('refresh').onclick=refresh;
const initialTheme=localStorage.getItem('orchestrator-theme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');document.documentElement.dataset.theme=initialTheme;$('theme').onclick=()=>{const next=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=next;localStorage.setItem('orchestrator-theme',next);};
async function start(){try{const token=new URLSearchParams(location.hash.slice(1)).get('token');if(token){history.replaceState(null,'',location.pathname);csrf=(await api('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})})).csrf;}else csrf=(await api('/api/session',{global:true})).csrf;await initializeWorkspaces();await refresh();applyDashboardRoute(false);setInterval(()=>{const editing=document.activeElement?.matches('input,select,textarea');if(!busy&&!selected&&!editing&&document.visibilityState==='visible')refresh();},5000);}catch(e){showNotice(e.message,true);$('connection').textContent='Authentication required';$('pause').disabled=true;$('reconcile').disabled=true;}}
// All deferred view modules must be ready before the first authenticated render.
document.addEventListener('DOMContentLoaded',start,{once:true});
