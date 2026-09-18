"use strict";
Object.assign(titles, {decisions:["Decision inbox", "Choose a suggestion or write your own answer. The brain continues within the recorded scope."]});
const decisionDrafts = new Map();
const decisionDetailsOpen = new Set();
const decisionLabels = {open:"Needs your decision", answered:"Answer recorded", received:"Received by brain", applied:"Applied to design", blocked:"Needs follow-up", superseded:"Superseded"};

function commandPresentation(c, activity=state?.brainActivity, now=Date.now()/1000) {
  if(c.status!=="queued")return {label:c.status==='processing'?(c.kind==='brain_stop'?"Preparing safe checkpoint":"Received by brain"):c.status,detail:c.result||"The brain has received this request."};
  if(state?.meta?.brainControl?.desired==='stopped'&&!['brain_stop','brain_resume'].includes(c.kind))
    return {label:"Saved until brain resumes",detail:"The brain is stopping or stopped at your request. This input is preserved; use Resume brain to continue."};
  const subject=c.kind==='decision_response'?"Answer":"Request";
  const n=c.notification;
  if(!n)return {label:subject+" saved",detail:"No immediate notification is recorded for this request. Use Wake brain now to process saved controls; an active turn finishes first."};
  if(n.status==='sending')return now-n.attemptedAt<=12
    ?{label:"Notifying brain",detail:subject+" saved. Waiting for Codex to acknowledge the notification."}
    :{label:"Delivery unconfirmed",detail:"The send was interrupted or its result is missing. Check the brain; your answer is saved and will not be resent automatically."};
  if(n.status==='accepted') {
    if(now-n.finishedAt>90)return {label:"Receipt overdue",detail:"Codex accepted the notification, but the brain has not recorded a receipt yet. Open the brain to check progress, approval prompts or availability. The heartbeat remains a fallback."};
    return {label:activity?.fresh&&activity.status==='running'?"Brain active · awaiting receipt":"Sent to Codex",
      detail:"Codex accepted the notification. An idle brain can start immediately; an active turn finishes first. Waiting for this request’s receipt, not an implementation-worker slot. A resume request is not yet applied; a stop request is not yet a safe checkpoint."};
  }
  return {label:n.status==='unavailable'?"Notification unavailable":"Delivery unconfirmed",detail:n.detail};
}

function workflowSummary(root, controls=false) {
  const w=state.workflow;
  if(!w) {root.append(callout("Workflow upgrade needs a server restart", "No listener or decision state is available from this running server.")); return;}
  const panel=el("section",null,"workflow-summary");
  const label={brain_stopped:"Paused at brain checkpoint",off:"Idle listening is off",needs_activation:"Native listener needs activation",unconfirmed:"Listener schedule recorded · check-in overdue or missing",listening:"Listener checked in recently"}[w.status]||"Not observed";
  const notifier=state.brainNotification,immediate=notifier?.status==='configured';
  const stopped=state.meta.brainControl?.desired==='stopped';
  panel.append(el("p","DECISIONS & CONTINUATION","eyebrow"),el("h2",stopped?"Inputs are saved until you resume the brain":immediate?"Answers and controls notify the brain immediately":"Immediate notification unavailable"));
  panel.append(el("p",notifier?.detail||"Restart with native notification enabled. Answers remain saved until the brain receives them.","muted"));
  panel.append(el("p",`${w.openDecisions} awaiting your decision · ${w.pendingRequests} requests awaiting completion · Worker dispatch ${w.dispatchPaused?'paused':'enabled'}`));
  panel.append(el("p",`Heartbeat fallback: ${label.toLowerCase()} · Inbox checked ${when(w.lastCheckedAt)}`,"muted"));
  const info=el("details",null,"coverage-details"),infoKey='listener:'+controls;
  info.open=decisionDetailsOpen.has(infoKey);
  info.addEventListener('toggle',()=>{if(info.open)decisionDetailsOpen.add(infoKey);else decisionDetailsOpen.delete(infoKey);});
  info.append(el("summary","Schedule, usage & availability"));
  info.append(el("p",`Native heartbeat: ${w.nativeStatus} (observed ${when(w.nativeObservedAt)}).`));
  info.append(el("p","Keep this computer and Codex running. Immediate notification uses the existing native task queue; it never interrupts an active turn. Acknowledged delivery is not a brain receipt or permission to execute."));
  info.append(el("p","The 15-minute heartbeat is a recovery fallback while enabled, not a required delay after answering. Both answer processing and scheduled checks consume model usage, including idle checks."));
  const actions=el("div",null,"inline-actions");
  if(!controls) actions.append(button(w.openDecisions?`Review ${w.openDecisions} decision${w.openDecisions===1?'':'s'}`:"Open decision inbox",()=>navigateView("decisions"),w.openDecisions?"primary":""));
  else {
    actions.append(button(w.listenerEnabled?"Turn off idle listening":"Keep listening between jobs",()=>command("listening",{enabled:!w.listenerEnabled})));
    info.append(el("p","Listening and worker dispatch are separate. Turning off idle listening takes effect on the next brain cycle; active workers still need supervision. Turning it back on cannot wake an already-paused native schedule."));
  }
  if(w.status==='needs_activation'||w.status==='unconfirmed') {
    panel.append(el("p",w.status==='needs_activation'?"The fallback schedule needs native activation. Immediate answer notification is separate and does not enable the schedule.":"No fresh fallback check or native schedule confirmation. The saved schedule alone does not prove it is running.","muted"));
  }
  if(/^[a-zA-Z0-9_-]{1,100}$/.test(state.meta.brainId||"")) {
    const link=el("a","Open brain in Codex","button");link.href="codex://threads/"+encodeURIComponent(state.meta.brainId);actions.append(link);
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
  const payload={decisionId:d.id,decisionHash:d.decisionHash,optionId:draft.optionId||null,note:draft.note,confirmed:draft.confirmed};
  // Retain the exact envelope after an uncertain network response; retry is not a second answer.
  if(!draft.request||JSON.stringify(draft.request.payload)!==JSON.stringify(payload))
    draft.request={id:crypto.randomUUID(),kind:"decision_response",expectedRevision:state.meta.revision,payload};
  busy=true;submit.disabled=true;
  try {
    const result=await api('/api/commands',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(draft.request)});
    decisionDrafts.delete(d.id);
    const delivery=commandPresentation(result);
    showNotice("Answer saved. "+delivery.label+". "+delivery.detail+" No implementation was authorized.");
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
    const form=el("form",null,"decision-form"),choices=el("fieldset");choices.append(el("legend","Suggested options · optional"));
    const intro=el("p","You can answer in your own words below without selecting an option.","muted");
    s.options.forEach(option=>{
      const label=el("label",null,"decision-option"),radio=el("input"),copy=el("span");
      radio.type="radio";radio.name="decision-"+d.id;radio.value=option.id;radio.checked=draft.optionId===option.id;
      copy.append(el("strong",option.label+(option.id===s.recommendedOptionId?" · Recommended":"")),el("span",option.implications,"subline"));
      label.append(radio,copy);choices.append(label);
      radio.onchange=()=>{draft.optionId=option.id;draft.confirmed=false;check.checked=false;updateAnswerMode();};
    });
    const ownAnswer=button("Use my own answer instead",()=>{
      draft.optionId="";draft.confirmed=false;check.checked=false;
      choices.querySelectorAll('input[type=radio]').forEach(radio=>{radio.checked=false;});
      updateAnswerMode();note.focus();
    });
    const noteLabel=el("label"),noteTitle=el("span"),note=el("textarea");note.rows=5;note.maxLength=4000;note.value=draft.note;
    const hint=el("p","Up to 4,000 characters. No credentials or secrets. Your answer is input for review, not permission to execute work.","muted");
    hint.id="decision-answer-hint-"+d.id;note.setAttribute("aria-describedby",hint.id);
    function updateAnswerMode() {
      const option=s.options.find(o=>o.id===draft.optionId);
      noteTitle.textContent=option?"Your note or requested information":"Your answer · in your own words";
      note.placeholder=option?"Add context or the information requested by this option.":"Write your answer here. You do not need to select an option above.";
      note.required=!option||option.requiresNote;
      note.setCustomValidity(note.required&&!note.value.trim()?"Write your answer or provide the information requested by your selected option.":"");
      ownAnswer.hidden=!option;
    }
    note.oninput=()=>{draft.note=note.value;draft.confirmed=false;check.checked=false;updateAnswerMode();};noteLabel.append(noteTitle,note);
    const confirmation=el("label",null,"decision-confirmation"),check=el("input");check.type="checkbox";check.required=true;check.checked=draft.confirmed;
    check.onchange=()=>{draft.confirmed=check.checked;};confirmation.append(check,el("span","I confirm this answer for this version. This is not approval to implement, access targets or merge."));
    const submit=button(state.meta.brainControl?.desired==='stopped'?"Save answer for later":state.brainNotification?.status==='configured'?"Send answer to brain":"Record answer",()=>{},"primary");submit.type="submit";
    form.onsubmit=e=>{e.preventDefault();if(form.reportValidity())submitDecision(d,draft,submit);};
    updateAnswerMode();
    form.append(intro,choices,ownAnswer,noteLabel,hint,confirmation,submit);card.append(form);
  } else if(d.response) {
    const option=s.options.find(o=>o.id===d.response.optionId);
    card.append(el("p",d.response.optionId===null?"Your answer · in your own words":"Your answer: "+(option?.label||d.response.optionId)),el("p",d.response.note||"No additional note.","decision-note"),el("p","Recorded "+when(d.response.at),"muted"));
    const command=state.commands.find(c=>c.id===d.response.commandId);
    if(command&&d.status==='answered') {
      const delivery=commandPresentation(command);
      card.append(callout(delivery.label,delivery.detail));
    }
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
