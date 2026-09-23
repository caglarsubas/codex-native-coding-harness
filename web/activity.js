"use strict";
let activityDetailsOpen = false;
function activityLabel(activity) {
  if (!activity?.fresh) return ({idle:"Last observed idle",running:"Last observed working"})[activity?.lastKnownStatus] || "Activity not observed";
  return ({running:"Active recently",idle:"Idle observed",interrupted:"Turn interrupted",failed:"Turn failed"})[activity.status] || "Activity unknown";
}
function brainControlPresentation(meta, activity) {
  const c=meta.brainControl || {desired:"running",phase:"ready"};
  const labels={stop_requested:"Stop requested",checkpointing:"Preparing safe checkpoint",parked:"Safe checkpoint saved",resume_requested:"Brain resume requested",ready:"Brain available"};
  const idleAfterCheckpoint=c.phase==='parked' && activity?.fresh && activity.status==='idle' && activity.observedAt>=c.checkpoint?.at;
  return {phase:c.phase,stopped:c.desired==='stopped',label:idleAfterCheckpoint?"Brain stopped at checkpoint":labels[c.phase]||"Brain control not observed",
    detail:c.phase==='parked'?"Automatic brain work is stopped. "+(idleAfterCheckpoint?"A later native idle observation confirms the turn finished.":"Native turn completion has not yet been observed after this checkpoint.")+" Saved answers wait for Resume brain."
      :c.desired==='stopped'?"New worker dispatch is paused now. The brain must finish its current bounded step, reconcile workers and acceptance, save a checkpoint and pause its heartbeat. Running tools are not interrupted."
      :c.phase==='resume_requested'?"Resume saved and awaiting brain receipt. The brain will recover its retained checkpoint; worker dispatch stays unchanged."
      :"Resume brain wakes this existing task from retained state. Stop is cooperative: it takes effect at a verified safe checkpoint, not in the middle of a running tool."};
}
function dispatchPresentation(meta, commands=[]) {
  const pending=commands.some(c=>c.kind==='resume' && ['queued','processing'].includes(c.status));
  return {label:pending?"Worker dispatch resume requested":meta.paused?"New worker dispatch paused":"Approved worker dispatch enabled",
    button:pending?"Worker resume requested":meta.paused?"Resume worker dispatch":"Pause new workers",
    disabled:meta.paused && (pending || meta.brainControl?.desired==='stopped')};
}
function navigateView(next, identity=null, updateAddress=true, activateWorkspace=true) {
  if(!titles[next])return;
  if(updateAddress&&!recordDashboardVisit(workspaceHref(next,identity&&['decisions','artifacts'].includes(next)?identity:null)))return;
  view=next; selected=next==='decisions'?null:identity; observationPage=0;
  if(identity&&next==='artifacts'){observationRepo='all';artifactQuery='';}
  document.querySelectorAll('[data-view]').forEach(b => b.removeAttribute('aria-current'));
  const nav=document.querySelector('[data-view="'+next+'"]');
  nav.setAttribute('aria-current','page');
  if(nav.closest?.('details'))nav.closest('details').open=true;
  if(activateWorkspace&&typeof revealPane==='function')revealPane('workspace');
  render();
  if(activateWorkspace){
    if(typeof focusRouteTarget==='function')focusRouteTarget({view:next,id:identity});
    else window.scrollTo(0,0);
  }
}
function brainActivity(root, history=false) {
  const a=state.brainActivity || {}, m=state.meta;
  const panel=el("section",null,"brain-activity"); panel.setAttribute("aria-label","Brain activity");
  const heading=el("div",null,"brain-heading"), identity=el("div");
  identity.append(el("p","DESIGNATED BRAIN · CONTROL & OBSERVED ACTIVITY","eyebrow"),el("h2",a.title || "Brain activity"));
  heading.append(identity,badge(activityLabel(a))); panel.append(heading);
  panel.append(el("p",a.fresh ? a.phase : "No fresh status. Last recorded step: "+(a.phase || "Not observed"),"brain-step"));
  const facts=el("dl",null,"brain-facts");
  [["Activity observed",when(a.observedAt)], ["Checkpoint saved",when(m.lastReconciled)], ["New worker dispatch",m.paused?"Paused":"Enabled"]].forEach(([label,value])=>{const row=el("div");row.append(el("dt",label),el("dd",value));facts.append(row);});
  panel.append(facts,el("p",m.brainControl?.desired==='stopped'?"Brain stop and worker dispatch are separate. No new implementation tasks will start; existing ownership and unfinished work are preserved.":m.paused?"Dispatch is paused. The brain can still plan, reconcile and save results; no new implementation tasks will start.":"Dispatch is enabled for approved packets only. Brain activity does not authorize new work.","brain-note"));
  const control=brainControlPresentation(m,a),controls=el("div",null,"inline-actions");
  panel.append(callout(control.label,control.detail));
  const resume=button(control.phase==='resume_requested'?"Brain resume requested":control.stopped?"Resume brain":"Wake brain now",()=>command("brain_resume"),"primary");
  resume.disabled=!connected||busy||control.phase==='resume_requested'||(state.workspacePause?.status==='pausing');
  const stop=button("Stop brain at safe checkpoint",()=>command("brain_stop"));
  stop.disabled=!connected||busy||control.stopped;
  controls.append(resume,stop);if(!state.workspace)panel.append(controls);
  if(m.brainControl?.checkpoint) {
    const cp=m.brainControl.checkpoint;
    panel.append(el("p","Retained safe checkpoint · "+when(cp.at)+" · "+cp.summary,"brain-note"));
    decisionArtifacts(panel,cp.artifactIds);
  }
  if(m.checkpoint) panel.append(el("p","Saved checkpoint: "+m.checkpoint.slice(0,280)+(m.checkpoint.length>280?"…":""),"brain-note"));
  const actions=el("div",null,"inline-actions");
  if (/^[a-zA-Z0-9_-]{1,100}$/.test(m.brainId || "")) {
    const link=el("a","Open brain in Codex","button"); link.href="codex://threads/"+encodeURIComponent(m.brainId); actions.append(link);
    actions.append(button("Copy brain task ID",()=>navigator.clipboard.writeText(m.brainId).then(()=>showNotice("Brain task ID copied. Use the Codex sidebar if your browser does not open the task link.")).catch(()=>showNotice("Task ID: "+m.brainId))));
  }
  actions.append(button(history?"Back to Overview":"Activity & checkpoint history",()=>navigateView(history?"overview":"knowledge")));
  panel.append(actions);
  const artifacts=(state.observations?.artifacts || []).filter(a=>a.references?.some(r=>r.session===m.brainId)).sort((a,b)=>b.orderAt-a.orderAt);
  if(artifacts.length) {
    const latest=artifacts[0], result=el("div",null,"brain-result");
    result.append(el("p","Latest retained brain artifact","eyebrow"),el("p",latest.name+" · v"+latest.version));
    result.append(button("Read latest brain artifact",()=>{observationRepo="all"; artifactQuery=m.brainId; navigateView("artifacts",latest.id); const reader=document.querySelector('.artifact-reader'); reader?.scrollIntoView(); reader?.focus({preventScroll:true});}));
    panel.append(result);
  }
  const details=el("details",null,"coverage-details");
  details.open=activityDetailsOpen;
  details.addEventListener("toggle",()=>{activityDetailsOpen=details.open;});
  details.append(el("summary","Activity source & freshness"),el("p",a.reason || "This server has not loaded the activity reader. Restart the dashboard server to enable it."));
  details.append(el("p","Visible-page refresh: every 5 seconds. Activity expires after 2 minutes without new evidence; this does not prove the task stopped. Checkpoint age and heartbeat are separate. No prompts, reasoning, messages or tool arguments are shown."));
  details.append(el("p","Activity source: "+(a.source || "unavailable")+" · Last check: "+when(a.checkedAt)));
  panel.append(details);
  if(history) {
    panel.append(section("Recent brain activity","Metadata only · newest first"));
    const list=el("ol",null,"event-list");
    [...(a.events || [])].reverse().forEach(e=>{const item=el("li");item.append(el("time",when(e.at)),el("span",e.label));list.append(item);});
    panel.append(list);
    if(!a.events?.length) panel.append(el("p","No supported events available in the bounded local log tail.","muted"));
  }
  root.append(panel);
}
