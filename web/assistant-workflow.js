"use strict";
const workflowPhrases={phase_prepare:'confirm prepare',phase_review:'confirm review',phase_play:'confirm play',phase_pause:'confirm pause',phase_resume:'confirm resume',usage_check:'confirm usage',codex_check:'confirm readiness',brain_message:'confirm send'};
function assistantWorkflowState(action,current=state,now=Date.now()/1000){
  const doc=action.proposal.document,recorded=current?.commands?.find(c=>c.id===doc.id)||action.receipt?.result;
  if(action.workspace!==workspaceId)return {locked:true,label:'Different project',detail:'Return to the project where this preview was prepared.'};
  if(recorded?.kind){const info=commandPresentation(recorded,current?.brainActivity,now);return {locked:true,label:info.label,detail:info.detail,recorded};}
  if(action.receipt)return {locked:true,label:doc.workflow==='usage_check'?'Usage refreshed':'Review saved',detail:action.receipt.message,recorded:action.receipt};
  if(action.cancelled)return {locked:true,label:'Dismissed',detail:'Nothing was submitted.'};
  if(action.sending)return {locked:true,label:'Saving…',detail:'Waiting for the receipt.'};
  if(action.rejected)return {locked:true,label:'Review again',detail:action.rejected};
  if(action.uncertain)return {locked:false,label:'Receipt unconfirmed',detail:'Retry this same confirmation to recover its receipt.'};
  if(now>doc.expiresAt)return {locked:true,label:'Preview expired',detail:'Ask again for a current preview.'};
  const request=doc.request;
  const stale=doc.workflow==='phase_review'?(current?.mission?.revision!==request.expectedRevision||current?.mission?.documentHash!==request.documentHash):
    request.preview?(request.preview.operation!=='pause'&&current?.standard?.contextHash!==request.preview.contextHash):
    ['codex_check','usage_check'].includes(doc.workflow)?current?.standard?.contextHash!==request.contextHash:current?.meta?.revision!==request.expectedRevision;
  if(stale||current?.meta?.brainId!==doc.brainId)return {locked:true,label:'Project changed',detail:'Ask again to review its current state.'};
  return {locked:false,label:'Ready for your confirmation',detail:'Type “'+workflowPhrases[doc.workflow]+'” or use the button below.'};
}
function assistantWorkflowPreview(item,proposal){
  const doc=proposal.document,p=doc.preview,section=el('section',null,'chat-action');
  section.setAttribute('aria-label','Review '+p.title);
  section.append(el('p','REVIEW TOGETHER','eyebrow'),el('h3',p.title),el('p',p.impact));
  if(p.mission){
    const {spec,version}=p.mission,a=spec.authority;
    section.append(el('p',spec.phase.title+' · plan v'+version,'chat-phase-title'),narrative(spec.goal,'Proposed outcome'),narrative(spec.phase.objective,'Phase objective'));
    const list=el('ul');
    for(const text of [`${num(a.tokenBudget)} phase tokens · ${num(a.checkpointReserveTokens)} reserved for checkpointing`,
      `${a.maxParallelTasks} parallel · ${a.maxTasks} tasks maximum`,
      a.approvalMode==='phase_delegated'?'The brain may approve tasks only inside this reviewed phase.':'Each packet requires your exact approval.',
      a.mergeMode==='brain_exact_pr_v1'?'Brain may merge the reviewed PR after checks.':'Pull requests wait for your merge.'])list.append(el('li',text));
    for(const row of spec.phase.scope)list.append(el('li',row.repository+': '+row.operations.join(', ')));
    section.append(list,el('p','Stops at'),narrative(spec.phase.checkpoint,'Stopping checkpoint'));
    const details=el('details');details.append(el('summary','Scope, success criteria & exclusions'));
    for(const row of spec.phase.scope)details.append(el('h4',row.repository),el('p',row.operations.join(', ')),el('pre',row.allowedPaths.join('\n')));
    for(const [title,items] of [['Success criteria',spec.successCriteria],['Stop sooner if',spec.phase.stopConditions],['Exclusions',spec.exclusions]]){
      const ul=el('ul');for(const text of items)ul.append(el('li',text));details.append(el('h4',title),ul);
    }
    section.append(details);
  }
  if(p.runSettings)section.append(el('p',`${p.runSettings.durationHours} hours maximum · ${num(p.runSettings.brainAllowance)} tokens allocated to the brain.${p.runSettings.measureUsage?' Missing usage coverage stops new effects.':''}`,'muted'));
  if(p.retainedRun)section.append(el('p',`Existing limits and consumed usage are preserved. Original phase expiry: ${when(p.retainedRun.expiresAt)}.`,'muted'));
  if(p.message)section.append(narrative(p.message,'Exact instruction to the project brain'));
  const exact=el('details');exact.append(el('summary','Receipt binding & expiry'),el('p','Expires '+when(doc.expiresAt)),el('pre',JSON.stringify({project:doc.workspaceId,mission:p.mission?.documentHash,requestId:doc.id},null,2)));section.append(exact);
  const status=el('p',null,'chat-action-status');status.setAttribute('role','status');
  const controls=el('div',null,'assistant-actions'),confirm=el('button','Confirm','primary'),dismiss=el('button','Dismiss');confirm.type=dismiss.type='button';controls.append(dismiss,confirm);section.append(status,controls);
  const action={proposal,workspace:workspaceId,element:section,status,confirm,dismiss,sending:false,receipt:null};
  // A newly requested preview replaces only unsubmitted, certain previews.
  for(const old of assistantActions.values())if(old.proposal.document.workflow&&!old.receipt&&!old.sending&&!old.uncertain)old.cancelled=true;
  assistantActions.set(doc.id,action);
  dismiss.onclick=()=>{action.cancelled=true;refreshAssistantActions();};
  action.submit=async()=>{
    if(!connected||assistantWorkflowState(action).locked)return;
    action.sending=true;action.uncertain=false;assistantConnectionChanged();
    try{
      action.receipt=await api('/api/assistant/confirm',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({proposal,confirmed:true})});
      assistantStatus(action.receipt.message);await refresh();
    }catch(error){if(error.workspaceChanged)return;if([400,401,403,409].includes(error.status))action.rejected=error.message;else action.uncertain=true;assistantStatus(error.message,true);}
    finally{action.sending=false;assistantConnectionChanged();assistantScroll();}
  };
  confirm.onclick=action.submit;item.append(section);refreshAssistantActions();
}
function assistantTypedConfirmation(question){
  const phrase=question.trim().toLowerCase().replace(/[.!]$/,'');
  if(!Object.values(workflowPhrases).includes(phrase))return false;
  const candidates=[...assistantActions.values()].filter(a=>a.proposal.document.workflow&&workflowPhrases[a.proposal.document.workflow]===phrase&&!assistantWorkflowState(a).locked);
  if(candidates.length!==1){assistantStatus('There is no single current preview for that confirmation. Ask for a fresh preview first.',true);return true;}
  chatTurn('user',question);$('assistant-question').value='';candidates[0].submit();return true;
}
async function assistantRequestStep(key){
  if(!connected||assistantPending)return;
  assistantPending=true;assistantConnectionChanged();
  try{const proposal=await api('/api/assistant/preview',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({key})});
    assistantActionPreview(chatTurn('assistant','Review this next step here.'),proposal);assistantScroll();
  }catch(error){if(!error.workspaceChanged)assistantStatus(error.message,true);}
  finally{assistantPending=false;assistantConnectionChanged();}
}
function assistantNextStep(){
  const root=$('assistant-next-step');if(!root)return;root.replaceChildren();
  if(!connected||!state?.workspace)return;
  const messages=[...(state.commands||[])].reverse().filter(c=>c.kind==='reconcile'&&c.payload?.message);
  const pending=messages.find(c=>!c.conversationReply);
  if(pending){const info=commandPresentation(pending,state.brainActivity);root.append(el('p','WITH YOUR PROJECT BRAIN','eyebrow'),el('p',info.label),el('p',info.detail,'muted'));return;}
  const journey=roadmapJourneyState(state,true),map={prepare:'phase_prepare',mission:'phase_review',catalog:'codex_check',play:'phase_play',pause:'phase_pause',resume:'phase_resume'};
  const needsMeasurement=(state.standard?.blockers||[]).some(reason=>/measure exact run usage|usage observation expired/i.test(reason));
  if(needsMeasurement&&!journey.request&&['running','paused'].includes(state.standard?.run?.status)){
    root.append(el('p','USAGE CHECK NEEDED','eyebrow'),el('p','Refresh measured usage before the next effect.'),button('Review usage check',()=>assistantRequestStep('usage_check')));return;
  }
  root.append(el('p','CURRENT PROJECT','eyebrow'),el('p',journey.title));
  const key=map[journey.action];
  const reviewable=journey.action!=='mission'||(state.mission?.effectiveStatus==='draft'&&!state.mission?.bindingIssues?.length);
  const prepareBlocked=key==='phase_prepare'&&['paused','stopping'].includes(state.standard?.run?.status);
  if(key&&reviewable&&!prepareBlocked){const b=button(journey.label,()=>assistantRequestStep(key));b.disabled=assistantPending;root.append(b);}
  else root.append(el('p',journey.detail,'muted'));
  if(journey.request){const info=commandPresentation(journey.request,state.brainActivity);root.append(el('p',info.label+'. '+info.detail,'muted'));}
  if(journey.reasons?.length){const reasons=el('ul');for(const text of journey.reasons)reasons.append(el('li',text));root.append(reasons);}
  if(messages[0]?.conversationReply){const reply=messages[0].conversationReply;root.append(journeyDisclosure('assistant-brain-reply','Latest project brain reply · '+when(reply.at),details=>details.append(narrative(reply.message,'Retained brain reply'))));}
}
function assistantWorkflowReceipt(action,recorded){
  if(action.proposal.document.workflow==='usage_check'&&action.receipt&&!action.usageShown){
    action.usageShown=true;const r=action.receipt.result;
    const item=chatTurn('assistant',assistantUsageSummary(r));
    if(r.gaps.length){const details=el('details');details.append(el('summary','Measurement gaps'),el('pre',r.gaps.join('\n')));item.append(details);}
  }
  const reply=recorded?.conversationReply;
  if(!reply||action.replyHash===reply.hash)return;
  action.replyHash=reply.hash;
  const item=chatTurn('assistant',reply.message);item.dataset.role='brain';item.querySelector('.eyebrow').textContent='PROJECT BRAIN · '+when(reply.at);
  // Retained brain text is shown locally, never appended to inference history.
}
function assistantUsageSummary(report){
  const observed=report.records?.length?`${report.gaps.length?'At least ':''}${num(report.tokens.total_tokens)} observed tokens · ${num(report.tokens.cached_input_tokens)} cached input`:'No usage samples were available';
  return `${observed} · observed ${when(report.collectedAt)}. ${report.gaps.length?'Remaining measured budget is unknown.':'Local registered-session coverage recorded; not a provider billing total.'}`;
}
function focusAssistant(){focusAssistantConversation();}
function focusAssistantConversation(){panePreferences.collapsed.workspace=true;panePreferences.collapsed.assistant=false;panePreferences.focus='assistant';savePanes();applyPanes();$('assistant-question').focus();}
