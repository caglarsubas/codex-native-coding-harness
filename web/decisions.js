"use strict";
Object.assign(titles, {decisions:["Decision inbox", "Choose a direction here. The brain continues within the recorded scope."]});
const decisionDrafts = new Map();
const decisionDetailsOpen = new Set();
const decisionLabels = {open:"Needs your decision", answered:"Answer recorded", received:"Received by brain", applied:"Applied to design", blocked:"Needs follow-up", superseded:"Superseded"};

function workflowSummary(root, controls=false) {
  const w=state.workflow;
  if(!w) {root.append(callout("Workflow upgrade needs a server restart", "No listener or decision state is available from this running server.")); return;}
  const panel=el("section",null,"workflow-summary");
  const label={off:"Idle listening is off",needs_activation:"Native listener needs activation",unconfirmed:"Listener schedule recorded · check-in overdue or missing",listening:"Listener checked in recently"}[w.status];
  panel.append(el("p","DECISIONS & CONTINUATION","eyebrow"),el("h2",label));
  panel.append(el("p",`${w.openDecisions} awaiting your decision · ${w.pendingRequests} requests awaiting completion · Worker dispatch ${w.dispatchPaused?'paused':'enabled'}`));
  panel.append(el("p",`Every 15 minutes while enabled · Inbox checked ${when(w.lastCheckedAt)}`,"muted"));
  const info=el("details",null,"coverage-details"),infoKey='listener:'+controls;
  info.open=decisionDetailsOpen.has(infoKey);
  info.addEventListener('toggle',()=>{if(info.open)decisionDetailsOpen.add(infoKey);else decisionDetailsOpen.delete(infoKey);});
  info.append(el("summary","Schedule, usage & availability"));
  info.append(el("p",`Native heartbeat: ${w.nativeStatus} (observed ${when(w.nativeObservedAt)}).`));
  info.append(el("p","Keep this computer and Codex running. Scheduled checks consume model usage, including idle checks; this is not an instant browser-to-Codex connection."));
  const actions=el("div",null,"inline-actions");
  if(!controls) actions.append(button(w.openDecisions?`Review ${w.openDecisions} decision${w.openDecisions===1?'':'s'}`:"Open decision inbox",()=>navigateView("decisions"),w.openDecisions?"primary":""));
  else {
    actions.append(button(w.listenerEnabled?"Turn off idle listening":"Keep listening between jobs",()=>command("listening",{enabled:!w.listenerEnabled})));
    info.append(el("p","Listening and worker dispatch are separate. Turning off idle listening takes effect on the next brain cycle; active workers still need supervision. Turning it back on cannot wake an already-paused native schedule."));
  }
  if(w.status==='needs_activation'||w.status==='unconfirmed') {
    panel.append(el("p",w.status==='needs_activation'?"Open the brain once to activate its native decision listener. A saved request cannot wake a paused schedule.":"No fresh inbox check or native status confirmation. Check the brain and app availability; the saved schedule alone does not prove it is running.","muted"));
    if(/^[a-zA-Z0-9_-]{1,100}$/.test(state.meta.brainId||"")) {
      const link=el("a","Open brain in Codex","button");link.href="codex://threads/"+encodeURIComponent(state.meta.brainId);actions.append(link);
    }
  }
  panel.append(actions,info);root.append(panel);
}

function decisionArtifacts(root, ids) {
  const links=el("div",null,"inline-actions");
  for(const id of ids) {
    const artifact=state.observations.artifacts.find(a=>a.id===id);
    if(artifact) links.append(button(`Read ${artifact.name} · v${artifact.version}`,()=>{
      observationRepo="all";artifactQuery="";navigateView("artifacts",id);
      document.querySelector('.artifact-reader')?.scrollIntoView();
    }));
  }
  root.append(links);
}

async function submitDecision(d, draft, submit) {
  if(busy||!connected) {showNotice("Wait for the current request or refresh the connection.",true);return;}
  const payload={decisionId:d.id,decisionHash:d.decisionHash,optionId:draft.optionId,note:draft.note,confirmed:draft.confirmed};
  // Retain the exact envelope after an uncertain network response; retry is not a second answer.
  if(!draft.request||JSON.stringify(draft.request.payload)!==JSON.stringify(payload))
    draft.request={id:crypto.randomUUID(),kind:"decision_response",expectedRevision:state.meta.revision,payload};
  busy=true;submit.disabled=true;
  try {
    await api('/api/commands',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(draft.request)});
    decisionDrafts.delete(d.id);
    showNotice("Answer recorded for this exact version. The brain will receive it on its next active cycle; no implementation was authorized.");
    await refresh();
  } catch(error) {
    if(error.message.includes("State changed")) draft.request=null;
    showNotice(error.message+" Your draft is retained. Refresh and review before retrying.",true);
  } finally {busy=false;submit.disabled=false;}
}

function decisionCard(d, root) {
  const card=el("article",null,"decision-card"),s=d.spec;
  card.append(el("p",`${s.repository} / ${s.key} · version ${d.version}`,"eyebrow"),el("h2",s.title),badge(decisionLabels[d.status]||d.status));
  card.append(el("h3",s.question),el("p",s.context));
  card.append(el("p","Scope: "+s.scope,"decision-scope"),el("p","Next step: "+s.nextStep),el("p",d.boundary,"muted"));
  decisionArtifacts(card,s.artifactIds);
  const detail=el("details",null,"coverage-details");
  detail.open=decisionDetailsOpen.has('binding:'+d.id);
  detail.addEventListener('toggle',()=>{if(detail.open)decisionDetailsOpen.add('binding:'+d.id);else decisionDetailsOpen.delete('binding:'+d.id);});
  detail.append(el("summary","Version binding & creation time"),el("p",d.decisionHash,"mono"),el("p",when(d.createdAt)));card.append(detail);
  if(d.status==='open') {
    let draft=decisionDrafts.get(d.id);
    if(!draft){draft={optionId:"",note:"",confirmed:false,request:null};decisionDrafts.set(d.id,draft);}
    const form=el("form",null,"decision-form"),choices=el("fieldset");choices.append(el("legend","Choose a direction"));
    s.options.forEach(option=>{
      const label=el("label",null,"decision-option"),radio=el("input"),copy=el("span");
      radio.type="radio";radio.name="decision-"+d.id;radio.value=option.id;radio.checked=draft.optionId===option.id;radio.required=true;
      copy.append(el("strong",option.label+(option.id===s.recommendedOptionId?" · Recommended":"")),el("span",option.implications,"subline"));
      label.append(radio,copy);choices.append(label);
      radio.onchange=()=>{draft.optionId=option.id;draft.confirmed=false;check.checked=false;note.required=option.requiresNote;};
    });
    const noteLabel=el("label", "Your note or requested information"),note=el("textarea");note.rows=4;note.maxLength=4000;note.value=draft.note;
    note.placeholder="No credentials or secrets. This note is input for review, not permission to execute commands.";
    note.required=s.options.find(o=>o.id===draft.optionId)?.requiresNote||false;
    note.oninput=()=>{draft.note=note.value;draft.confirmed=false;check.checked=false;};noteLabel.append(note);
    const confirmation=el("label",null,"decision-confirmation"),check=el("input");check.type="checkbox";check.required=true;check.checked=draft.confirmed;
    check.onchange=()=>{draft.confirmed=check.checked;};confirmation.append(check,el("span","I confirm this direction and note for this version. This is not approval to implement, access targets or merge."));
    const submit=button("Record decision",()=>{},"primary");submit.type="submit";
    form.onsubmit=e=>{e.preventDefault();if(form.reportValidity())submitDecision(d,draft,submit);};
    form.append(choices,noteLabel,confirmation,submit);card.append(form);
  } else if(d.response) {
    const option=s.options.find(o=>o.id===d.response.optionId);
    card.append(el("p","Your answer: "+option.label),el("p",d.response.note||"No additional note.","decision-note"),el("p","Recorded "+when(d.response.at),"muted"));
    if(d.receivedAt)card.append(el("p","Received by brain "+when(d.receivedAt),"muted"));
  }
  if(d.resolution){card.append(el("h3","Brain outcome"),el("p",d.resolution.summary),el("p",when(d.resolution.at),"muted"));decisionArtifacts(card,d.resolution.artifactIds);}
  root.append(card);
}

function decisions(root) {
  workflowSummary(root,true);
  const rows=state.decisions||[],active=rows.filter(d=>['open','answered','received'].includes(d.status));
  if(!active.length)root.append(empty("No decisions waiting", "The brain publishes specific questions here with their scope and supporting artifacts. Already answered decisions stay in history. Packet execution still needs a separate approval in Approved queue."));
  active.sort((a,b)=>a.createdAt-b.createdAt).forEach(d=>decisionCard(d,root));
  const history=rows.filter(d=>!['open','answered','received'].includes(d.status));
  if(history.length){root.append(section("Decision history","Earlier versions and outcomes remain preserved."));history.forEach(d=>{const details=el("details",null,"decision-history");details.open=decisionDetailsOpen.has(d.id);details.addEventListener('toggle',()=>{if(details.open)decisionDetailsOpen.add(d.id);else decisionDetailsOpen.delete(d.id);});details.append(el("summary",`${d.spec.title} · v${d.version} · ${decisionLabels[d.status]}`));decisionCard(d,details);root.append(details);});}
}
