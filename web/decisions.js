"use strict";
Object.assign(titles, {decisions:["Decision inbox", "Choose a suggestion or write your own answer. The brain continues within the recorded scope."]});
const decisionDrafts = new Map();
const decisionDetailsOpen = new Set();
const decisionLabels = {open:"Needs your decision", answered:"Answer recorded", received:"Received by brain", applied:"Applied to design", blocked:"Needs follow-up", superseded:"Superseded"};

function commandPresentation(c, activity=state?.brainActivity, now=Date.now()/1000) {
  if(c.status!=="queued"&&!c.needsBrainReceipt)return {label:c.status==='processing'?(c.kind==='brain_stop'?"Preparing safe checkpoint":"Received by brain"):c.status,detail:c.result||"The brain has received this request."};
  if(state?.meta?.brainControl?.desired==='stopped'&&!['brain_stop','brain_resume'].includes(c.kind))
    return {label:"Saved until brain resumes",detail:"The brain is stopping or stopped at your request. This input is preserved; use Resume brain to continue."};
  const subject=c.kind==='decision_response'?"Answer":c.kind==='approve'?"Approval":c.needsBrainReceipt?"Policy change":"Request";
  const n=c.notification;
  if(!n)return {label:subject+" saved",detail:"No immediate notification is recorded for this request. Use Wake brain now to process saved controls; an active turn finishes first."};
  if(n.status==='sending')return now-n.attemptedAt<=12
    ?{label:"Notifying brain",detail:subject+" saved. Waiting for Codex to acknowledge the notification."}
    :{label:"Delivery unconfirmed",detail:"The send was interrupted or its result is missing. Check the brain; your answer is saved and will not be resent automatically."};
  if(n.status==='accepted') {
    if(now-n.finishedAt>90)return {label:"Receipt overdue",detail:"Codex accepted the notification, but the brain has not recorded a receipt yet. Open the brain to check progress, approval prompts or availability. A paused heartbeat cannot recover this request."};
    return {label:activity?.fresh&&activity.status==='running'?"Brain active · awaiting receipt":"Sent to Codex",
      detail:"Codex accepted the notification. An idle brain can start now; an active turn finishes first. Waiting for brain receipt, not a worker slot."
        +(c.kind==='resume'?" Worker dispatch resume is not yet applied.":c.kind==='brain_stop'?" A safe checkpoint has not yet been reached.":c.kind==='brain_resume'?" Worker dispatch stays unchanged.":"")};
  }
  return {label:n.status==='unavailable'?"Notification unavailable":"Delivery unconfirmed",detail:n.detail};
}

function workflowSummary(root, controls=false) {
  const w=state.workflow;
  if(!w) {root.append(callout("Workflow upgrade needs a server restart", "No listener or decision state is available from this running server.")); return;}
  const panel=el("section",null,"workflow-summary");
  const label={brain_stopped:"Paused at brain checkpoint",event_waiting:"Waiting for an event · no idle checks requested",idle_pause_pending:"Idle checks no longer needed · native pause pending",needs_activation:"Supervision schedule needs activation",unconfirmed:"Schedule recorded · check-in overdue or missing",listening:"Supervision checked in recently"}[w.status]||"Not observed";
  const notifier=state.brainNotification,immediate=notifier?.status==='configured';
  const stopped=state.meta.brainControl?.desired==='stopped';
  panel.append(el("p","DECISIONS & CONTINUATION","eyebrow"),el("h2",stopped?"Inputs are saved until you resume the brain":immediate?"Answers and controls notify the brain immediately":"Immediate notification unavailable"));
  panel.append(el("p",notifier?.detail||"Restart with native notification enabled. Answers remain saved until the brain receives them.","muted"));
  panel.append(el("p",`${w.openDecisions} awaiting your decision · ${w.pendingRequests} request${w.pendingRequests===1?'':'s'} awaiting completion · Worker dispatch ${w.dispatchPaused?'paused':'enabled'}`));
  if(w.followUpsNeedingProposal)panel.append(callout("Blocked work needs a next step",`${w.followUpsNeedingProposal} blocked outcome${w.followUpsNeedingProposal===1?' needs':'s need'} a concrete proposal or an explicit external dependency. No implementation is authorized by this status.`));
  else if(w.followUps)panel.append(el("p",`${w.followUps} retained follow-up${w.followUps===1?'':'s'} · Read the proposals and their next decisions in the inbox.`));
  panel.append(el("p",`${label} · Inbox checked ${when(w.lastCheckedAt)}`,"muted"));
  const info=el("details",null,"coverage-details"),infoKey='listener:'+controls;
  info.open=decisionDetailsOpen.has(infoKey);
  info.addEventListener('toggle',()=>{if(info.open)decisionDetailsOpen.add(infoKey);else decisionDetailsOpen.delete(infoKey);});
  info.append(el("summary","Schedule, usage & availability"));
  info.append(el("p",`Native heartbeat: ${w.nativeStatus} (observed ${when(w.nativeObservedAt)}).`));
  info.append(el("p","Keep this computer and Codex running. Immediate notification uses the existing native task queue; it never interrupts an active turn. Acknowledged delivery is not a brain receipt or permission to execute."));
  info.append(el("p","Event-driven waiting pauses the native heartbeat when only owner input or an external dependency remains. New answers, approvals and controls notify the brain directly. Active work still needs supervision. Periodic idle checks are optional and consume model usage even when nothing changes."));
  const actions=el("div",null,"inline-actions");
  if(!controls) actions.append(button(w.openDecisions?`Review ${w.openDecisions} decision${w.openDecisions===1?'':'s'}`:"Open decision inbox",()=>navigateView("decisions"),w.openDecisions?"primary":""));
  else {
    actions.append(button(w.listenerEnabled?"Use event-driven waiting":"Enable periodic idle checks",()=>command("listening",{enabled:!w.listenerEnabled})));
    info.append(el("p","This preference does not change worker dispatch or stop the brain. The brain applies the native schedule and records its actual status after receiving the request. If notification fails, use Open brain in Codex; do not assume a paused heartbeat will recover it."));
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
  card.id='decision-'+d.id;
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
  continuationCards(root);
  const rows=state.decisions||[],active=rows.filter(d=>['open','answered','received'].includes(d.status));
  if(!active.length)root.append(empty("No unanswered questions", "Check any follow-ups above for the next step. Earlier answers remain in history. Packet execution still needs a separate approval in Approved queue."));
  active.sort((a,b)=>a.createdAt-b.createdAt).forEach(d=>decisionCard(d,root));
  const history=rows.filter(d=>!['open','answered','received'].includes(d.status));
  if(history.length){root.append(section("Decision history","Earlier versions and outcomes remain preserved."));history.forEach(d=>{const details=el("details",null,"decision-history");details.open=decisionDetailsOpen.has(d.id);details.addEventListener('toggle',()=>{if(details.open)decisionDetailsOpen.add(d.id);else decisionDetailsOpen.delete(d.id);});details.append(el("summary",`${d.spec.title} · v${d.version} · ${decisionLabels[d.status]}`));decisionCard(d,details);root.append(details);});}
}

function continuationCards(root) {
  const rows=state.continuations||[];
  if(!rows.length)return;
  root.append(section("Next steps for blocked work","Your original answer stays preserved. A proposal is not permission to execute."));
  const labels={needs_proposal:"Proposal needed",needs_revision:"Proposal links changed · review needed",waiting_external:"Waiting for an external event",proposal_published:"Next step published"};
  for(const c of rows) {
    const card=el("article",null,"decision-card");
    card.append(el("p",c.repository,"eyebrow"),el("h2",c.title),badge(labels[c.status]),el("p",c.outcome.summary));
    if(c.response?.note)card.append(el("p","Your retained answer","eyebrow"),el("p",c.response.note,"decision-note"));
    if(c.proposal) {
      const p=c.proposal.spec;
      card.append(el("h3",`Proposal · v${c.proposal.version}`),el("p",p.summary));
      decisionArtifacts(card,p.artifactIds);
      if(p.externalBlocker)card.append(el("p",p.externalBlocker.reason),el("p","Resume when: "+p.externalBlocker.resumeWhen));
      for(const d of c.decisions)card.append(button(`${d.title} · ${decisionLabels[d.status]||d.status}`,()=>{
        const target=document.getElementById('decision-'+d.id);
        if(target){const details=target.closest('details');if(details)details.open=true;target.scrollIntoView({block:'start'});}
      }));
      if(c.queue.length)card.append(button("Review proposed packets",()=>navigateView("queue")));
    }
    if(['needs_proposal','needs_revision','waiting_external'].includes(c.status)) {
      card.append(el("p",c.status==='waiting_external'?"No repeated checks are needed while this dependency is unchanged.":"The brain should prepare one bounded next step, without repeating the answered question or starting implementation.","muted"));
      const pending=state.commands.some(cmd=>cmd.kind==='reconcile'&&['queued','processing'].includes(cmd.status));
      const review=button(pending?"Review requested":"Ask brain to review next step",()=>command("reconcile"),"primary");
      review.disabled=pending||state.meta.brainControl?.desired==='stopped';card.append(review);
    }
    const evidence=el("details");evidence.append(el("summary","Original outcome evidence"));decisionArtifacts(evidence,c.outcome.artifactIds);card.append(evidence);
    root.append(card);
  }
}
