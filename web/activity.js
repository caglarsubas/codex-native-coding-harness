"use strict";
let activityDetailsOpen = false;
function activityLabel(activity) {
  if (!activity?.fresh) return "Activity unknown";
  return ({running:"Active recently",idle:"Idle observed",interrupted:"Turn interrupted",failed:"Turn failed"})[activity.status] || "Activity unknown";
}
function navigateView(next, identity=null) {
  view=next; selected=identity; observationPage=0;
  document.querySelectorAll('[data-view]').forEach(b => b.removeAttribute('aria-current'));
  document.querySelector('[data-view="'+next+'"]').setAttribute('aria-current','page');
  render(); window.scrollTo(0,0);
}
function brainActivity(root, history=false) {
  const a=state.brainActivity || {}, m=state.meta;
  const panel=el("section",null,"brain-activity"); panel.setAttribute("aria-label","Brain activity");
  const heading=el("div",null,"brain-heading"), identity=el("div");
  identity.append(el("p","DESIGNATED BRAIN · READ-ONLY ACTIVITY","eyebrow"),el("h2",a.title || "Brain activity"));
  heading.append(identity,badge(activityLabel(a))); panel.append(heading);
  panel.append(el("p",a.fresh ? a.phase : "No fresh status. Last recorded step: "+(a.phase || "Not observed"),"brain-step"));
  const facts=el("dl",null,"brain-facts");
  [["Activity observed",when(a.observedAt)], ["Checkpoint saved",when(m.lastReconciled)], ["New worker dispatch",m.paused?"Paused":"Enabled"]].forEach(([label,value])=>{const row=el("div");row.append(el("dt",label),el("dd",value));facts.append(row);});
  panel.append(facts,el("p",m.paused?"Dispatch is paused. The brain can still plan, reconcile and save results; no new implementation tasks will start.":"Dispatch is enabled for approved packets only. Brain activity does not authorize new work.","brain-note"));
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
