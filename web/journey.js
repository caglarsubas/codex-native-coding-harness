"use strict";
// A navigation projection of existing records. Only the existing signed controls
// can authorize Play, Resume or Pause; this module never submits them directly.
const journeyDetailsOpen=new Set();
function catalogReadinessIssue(refresh){
  if(refresh?.status!=='failed')return null;
  const error=refresh.catalogError;
  // Retryability may mean "after setup changes", not "send the same check
  // again now". Use structured retained codes, never diagnose from prose.
  if(error?.code==='native_task_schema_unavailable')return {
    title:'Codex task tools are unavailable',
    detail:'The brain received the check, but this host does not expose the native task tools needed to verify models and efforts. Repair the host’s tool setup before another check. Your phase review is unchanged; Play has not started.',
    requiresSetupChange:true};
  if(error?.code==='schema_unavailable')return {
    title:'Codex task capabilities are unverified',
    detail:'The brain could not observe the native task schemas needed to verify models and efforts. Inspect the host’s tool setup before another check. Your phase review is unchanged; Play has not started.',
    requiresSetupChange:true};
  if(error?.retryable===false)return {
    title:'Codex readiness needs operator attention',
    detail:'The brain recorded a readiness error that cannot be retried. Inspect the saved diagnostic and resolve its prerequisite before another check. Play has not started.',
    requiresSetupChange:true};
  return null;
}
function catalogReadinessDetails(root,refresh){
  if(refresh?.status!=='failed')return;
  const key=workspaceId,requestId=refresh.id,contextHash=state.standard?.contextHash;
  const details=journeyDisclosure('catalog-error:'+refresh.id,'Details · Codex readiness diagnostic',body=>{
    body.append(el('p',refresh.result||'No diagnostic text was retained.'),
      el('p','Request: '+refresh.id+' · recorded '+when(refresh.completedAt),'subline'));
    if(refresh.catalogError)body.append(el('p','Error: '+refresh.catalogError.code+' · retryable after prerequisites are resolved: '+(refresh.catalogError.retryable?'yes':'no'),'subline'));
    if(catalogReadinessIssue(refresh)){
      body.append(el('p','A new check is not a host repair. It sends a new bounded request to the same brain; it does not reconfigure the host, grant authority or start Play.','muted'));
      if(refresh.catalogError?.retryable!==false){
        const recheck=button('Check again after host repair',()=>{
          const current=state.standard?.catalogRefresh;
          if(workspaceId!==key||current?.id!==requestId||current.status!=='failed'||!catalogReadinessIssue(current)||
            current.catalogError?.retryable===false||state.standard?.contextHash!==contextHash||busy||!connected)return;
          return requestCatalogForPlay(state.standard);
        });
        recheck.disabled=busy||!connected||standardCatalogInFlight.has(workspaceId);
        body.append(recheck);
      }
    }
  });
  details.id='catalog-readiness-diagnostic';root.append(details);
}
function projectPhaseStatus(snapshot){
  const run=snapshot.standard.run,m=snapshot.mission;
  const next=['completed','blocked'].includes(run.status)&&m?.document?.spec.phase.id!==run.phaseId&&m?.document;
  const attention=snapshot.recovery&&(snapshot.recovery.reconciliationRequired||['running','stopping'].includes(run.status));
  const latestControl=[...(snapshot.commands||[])].reverse().find(c=>c.payload?.runId===run.id&&['standard_play','standard_pause','standard_resume'].includes(c.kind));
  const lost=['connection_lost','unconfirmed'].includes(latestControl?.notification?.nativeTurnStatus);
  const status=next?`Plan v${m.document.version} ${m.effectiveStatus==='reviewed'?'reviewed · Play not started':'awaits review'} · Previous phase ${run.status}`:lost?`CONNECTION UNRESOLVED · phase recorded ${run.status}`:attention?'RECOVERY REQUIRED':run.status.toUpperCase();
  const unsettled=run.tasks.filter(t=>!['completed','failed','not_created'].includes(t.status)).length;
  return 'STANDARD · '+status+' · '+unsettled+' registered '+(unsettled===1?'task':'tasks')+' unsettled';
}
function journeyDisclosure(key,title,build){
  const details=el('details',null,'journey-disclosure'),identity=(workspaceId||'legacy')+':'+key;
  details.open=journeyDetailsOpen.has(identity);details.append(el('summary',title));
  const body=el('div');build(body);details.append(body);
  details.addEventListener('toggle',()=>{if(!details.isConnected)return;if(details.open)journeyDetailsOpen.add(identity);else journeyDetailsOpen.delete(identity);});
  return details;
}
function controlRequestHistory(root){
  const commands=[...(state.commands||[])].reverse();
  const details=journeyDisclosure('control-requests','Details · Control request history',body=>{
    body.append(el('p','Saved request, native delivery and brain receipt are separate. Inspect the existing request before sending more work. This history submits nothing.','muted'));
    if(!commands.length){body.append(el('p','No saved control requests.'));return;}
    for(const command of commands){
      const info=commandPresentation(command);
      const record=el('article',null,'brain-exchange');
      record.append(el('h3',command.kind.replaceAll('_',' ')),el('p',info.label),el('p',info.detail,'muted'),
        el('p','Request: '+command.id+' · saved '+when(command.createdAt),'brain-message-text subline'),
        el('p','Recorded result: '+(command.result||'No result retained'),'muted'));
      if(typeof wakeFailureDetails==='function')wakeFailureDetails(record,command.notification,command.id);
      body.append(record);
    }
  });
  details.id='control-request-history';root.append(details);
}
function journeyPendingConversation(snapshot){
  return [...(snapshot.commands||[])].reverse().find(c=>c.kind==='reconcile'&&c.payload?.message&&!c.conversationReply);
}
function journeyConversationProgress(command){
  const n=command.notification;
  if(n?.nativeTurnStatus==='connection_lost')return {
    title:'Connection lost; this request is unresolved',
    detail:'The owned Codex connection stopped responding. Your request is preserved, but its result is unknown. Repair the host and reconcile this existing request; do not send another message or repeat Play.'};
  if(n?.nativeTurnStatus==='unconfirmed')return {
    title:'The native connection ended without a confirmed result',
    detail:'Inspect this existing request and host. An ended observer is not a brain receipt, finished turn or permission to retry.'};
  const ended=['completed','failed','interrupted'].includes(n?.nativeTurnStatus);
  if(n?.nativeTurnStatus==='native_attention_required')return {
    title:'Check the native permission or input request',
    detail:'Codex reported a permission or input request. Inspect it in brain chat; only a current prompt can be answered. No permission is granted automatically.'};
  if(command.conversationReceivedAt)return ended?{
    title:'The brain turn ended without a saved reply',
    detail:'The brain received this request, but its reply is missing. Inspect the existing turn and host before reconciling it; do not send another request.'}:{
    title:'Waiting for the brain’s saved reply',
    detail:'The brain received your request. Its reply has not been saved yet. Follow this request in brain chat; do not send a duplicate.'};
  if(['uncertain','sending'].includes(n?.status))return {
    title:'Request delivery needs reconciliation',
    detail:'Your request is saved, but its native delivery is unconfirmed. Inspect this attempt before any new wake; do not resend it.'};
  if(n?.status==='unavailable')return {
    title:'The saved request could not reach Codex',
    detail:'Inspect its delivery record and the configured host. A new message will not repair the connection; no retry has been sent.'};
  if(n?.status==='accepted')return ended?{
    title:'Codex ended the turn without a brain receipt',
    detail:'Native delivery and the brain’s ledger receipt are separate. Inspect the existing turn and host; do not repeat this request.'}:{
    title:'Waiting for the brain’s receipt',
    detail:'Codex accepted the saved request. Follow its separate brain receipt and reply in brain chat before sending another request.'};
  return {title:'A saved request is waiting for delivery',
    detail:'This request has no recorded native delivery. Inspect the saved request and brain controls before preparing more work.'};
}
function roadmapJourneyState(snapshot,isConnected=true,now=Date.now()/1000){
  const s=snapshot.standard,run=s?.run,m=snapshot.mission,spec=m?.document?.spec;
  const result=(stage,title,detail,label,action,extra={})=>({stage,title,detail,label,action,...extra});
  if(!isConnected)return result(0,'Reconnect to see your next step','The last saved state may be out of date. Refresh the connection before reviewing or starting work.','Reconnect','refresh');
  const repos=snapshot.repositories;
  if(!snapshot.workspace||!Array.isArray(repos)||!repos.length||repos.some(r=>r.policyProfile!=='standard'))
    return result(0,'This project uses packet approvals','Review the approved queue and project readiness to continue this roadmap. Phase Play is available for configured standard projects.','Review approved queue','queue',{strict:true});
  const pause=snapshot.workspacePause||{},control=snapshot.meta?.brainControl||{};
  if(control.desired==='stopped'&&pause.status==='pausing'&&control.phase==='checkpointing'){
    const missing=(pause.blockers||[]).some(item=>['inventory_missing','inventory_incomplete'].includes(item.code));
    return result(3,missing?'Native checkpoint evidence is missing':'The saved Pause is still checkpointing',
      missing?'The brain needs complete native task and descendant evidence. If its observation tools are unavailable, this is an operator capability gap; another Help, Play or message cannot clear it.':'Follow the recorded stop blockers. Do not repeat Pause or start new work.',
      'Inspect checkpoint blockers','operations');
  }
  const handoff=snapshot.brainHandoff?.handoff;
  if(handoff&&['prepared','candidate','received'].includes(handoff.status))return result(3,'Finish the brain handoff',
    handoff.status==='received'?'The replacement received its checkpoint. Project identity and final owner review still need to be resolved before continuing.':'A replacement brain is being prepared. Follow its recorded progress before continuing the phase.',
    'Review handoff progress','handoff',{canPause:run?.status==='running'});
  const pending=[...(snapshot.commands||[])].reverse().find(c=>run&&c.payload?.runId===run.id&&['standard_play','standard_pause','standard_resume'].includes(c.kind)&&['queued','processing'].includes(c.status));
  if(run?.status==='stopping'&&s.pauseRecovery?.available&&snapshot.brainNotification?.transport==='owned_app_server')return result(2,s.pauseRecovery.replacementOf?'Review replacement checkpoint recovery':'Recover the saved Pause',
    s.pauseRecovery.replacementOf?'The first recovery failed before turn start. Review one replacement; its failed record is preserved and no third attempt is allowed.':'Its delivery failed before starting a brain turn. Review one checkpoint-only recovery; development stays stopped.',
    s.pauseRecovery.replacementOf?'Review replacement recovery':'Recover saved Pause','pause-recover');
  if(run?.status==='stopping'&&['queued','processing'].includes(run.pauseRecovery?.status)){
    const request=(snapshot.commands||[]).find(c=>c.id===run.pauseRecovery.id);
    return result(2,'Following Pause recovery','Native delivery, the saved Pause receipt and the paused checkpoint are separate. No second wake will be sent.',
      'Inspect recovery progress','request',{request});
  }
  const turnRecovery=[...(snapshot.commands||[])].reverse().find(c=>c.notification?.hostRunId===run?.id&&c.notification?.turnRecovery)?.notification?.turnRecovery;
  if(run?.status==='stopping'&&!pending&&turnRecovery?.status==='controller_recovered'&&!snapshot.meta?.controller)
    return result(2,'The stranded turn was recovered','Development stays stopped. Review the existing safe-checkpoint control so the brain can retain the phase result. No permission or Play was replayed.',
      'Review safe phase checkpoint','pause');
  if(run?.status==='stopping'&&!pending&&turnRecovery?.status==='awaiting_end')
    return result(2,'Following turn recovery','Cancellation was claimed once. Ownership remains retained until the same turn and tracked terminals can be confirmed inactive.',
      'Check existing turn recovery','conversation');
  if(run?.status==='stopping')return result(2,'Pause requested','New work is fenced. The brain still needs to settle registered tasks and save a safe checkpoint.',pending?'Inspect request delivery':'Follow sessions',pending?'request':'overview',{request:pending});
  const latestControl=[...(snapshot.commands||[])].reverse().find(c=>run&&c.payload?.runId===run.id&&['standard_play','standard_pause','standard_resume'].includes(c.kind));
  if(run?.status==='running'&&latestControl?.notification?.nativeTurnStatus==='native_attention_required')
    return result(2,'The native brain turn needs recovery','Its permission observer ended without a confirmed native result. Inspect the exact existing turn in Brain chat; do not repeat Play or send its instruction again.',
      'Inspect existing turn recovery','conversation',{canPause:true});
  if(run?.status==='running'&&['connection_lost','unconfirmed'].includes(latestControl?.notification?.nativeTurnStatus))return result(2,latestControl.notification.nativeTurnStatus==='connection_lost'?'Connection lost; this request is unresolved':'Native outcome is unconfirmed; inspect this request',
    'The phase is recorded as running, not verified active. Repair the host, then reconcile this existing request and any effects. Its receipt, usage and ownership are preserved; do not repeat Play.',
    'Inspect saved request','request',{request:latestControl,canPause:true});
  if(pending){
    const status=pending.notification?.nativeTurnStatus;
    const lost=['connection_lost','unconfirmed'].includes(status);
    const ended=['completed','failed','interrupted'].includes(status);
    return result(2,lost?'Connection lost; this request is unresolved':ended?'Brain turn ended; receipt is missing':'Waiting for the brain’s receipt',
      lost?'Repair the host connection, then reconcile this saved request. Its effect is unknown; do not repeat Review or Play.':ended?'The native turn ended without recording this control’s receipt. Inspect the existing request and host; do not repeat Play.':'Your '+pending.kind.replace('standard_','')+' request is saved. Inspect its delivery status before sending another request.',
      'Inspect saved request','request',{request:pending,canPause:run.status==='running'});
  }
  const blockers=[...(s?.blockers||[])];
  if(run&&['running','paused'].includes(run.status)&&run.expiresAt<=now&&!blockers.some(x=>/expir/i.test(x)))blockers.push('The phase time limit has expired.');
  const conversation=journeyPendingConversation(snapshot);
  // A phase draft or absent run is not proof that an earlier conversation is
  // finished. Paused recovery keeps its separately signed preparation path.
  if(conversation&&run?.status!=='paused'&&!(run?.status==='running'&&blockers.length&&!snapshot.recovery)){
    const progress=journeyConversationProgress(conversation);
    return result(run?.status==='running'?2:0,progress.title,progress.detail,
      'Inspect saved request','conversation',{request:conversation,canPause:run?.status==='running'});
  }
  if(run?.status==='running'){
    if(snapshot.recovery&&!snapshot.meta?.controller){
      if(snapshot.meta?.brainControl?.desired==='stopped')return result(2,'Brain is stopped; recovery is still needed',
        'A normal message cannot wake a stopped brain. Inspect its safe checkpoint and explicit brain Resume control before requesting reconciliation.',
        'Review brain recovery','operations',{canPause:true});
      if((snapshot.commands||[]).some(c=>c.kind==='reconcile'&&c.payload?.message&&!c.conversationReply))return result(2,'Recovery request is awaiting a reply',
        'Follow the saved request and its receipt. The recorded blockers remain until reconciled; do not send a duplicate.',
        'Follow brain reply','conversation',{canPause:true});
      return result(2,'Recovery required before continuing',
        'The phase is still open, but its recorded conditions need attention. Reconcile existing work before deciding how to continue.',
        'Reconcile this phase','reconcile',{canPause:true});
    }
    if(blockers.length)return result(2,'This phase needs a checkpoint','New work is blocked. Pause at the next safe point, then review the reason below.','Pause at safe checkpoint','pause',{reasons:blockers});
    const count=snapshot.workflow?.openDecisions||0;
    if(count)return result(2,'Your decision is needed',`${count} open ${count===1?'decision needs':'decisions need'} your input. The phase keeps its reviewed scope.`, 'Review decisions','decisions',{canPause:true});
    return result(2,'Phase is active','Play is active up to the reviewed stopping checkpoint. Follow the sessions for observed task activity, or pause safely at any time.','Follow sessions','overview',{canPause:true});
  }
  if(run?.status==='paused'){
    const recovery=run.recovery;
    const budgetAdjusted=(run.budgetReviews||[]).some(r=>r.at>=run.checkpoint?.at);
    if(s.brainBudget?.available&&!budgetAdjusted&&run.checkpoint?.reasonCodes?.includes('token_budget'))return result(3,'Review the brain allowance',
      'The phase is paused at its budget checkpoint. Reallocate within the approved phase total; preserve usage and gaps. Host evidence and fresh usage are still required before a separate Resume.',
      'Review brain allowance','budget',{reasons:blockers});
    if(budgetAdjusted&&blockers.some(b=>/measure exact run usage|usage observation expired/i.test(b)))return result(3,'Allowance adjusted; refresh usage',
      'The local correction is saved and the phase remains paused. Review a fresh registered usage check; unknown coverage and other prerequisites still block Resume.',
      'Review usage check','usage-check',{reasons:blockers});
    if(snapshot.phaseCloseout?.available)return result(3,'Recovery finished; close the stopped phase',
      'Close this empty phase as blocked and unqualified. Its usage and evidence stay intact. Then Help prepares the next proposal; no prompt writing or Resume.',
      'Review stopped-phase closeout','close',{reasons:blockers});
    if(recovery&&recovery.status!=='replied')return result(3,'Recovery preparation is underway',
      'One owner-reviewed preparation wake is saved. Follow native delivery, brain receipt and reply here; no second request is sent.',
      'Follow recovery progress','recover_follow',{reasons:blockers});
    if(blockers.length){
      if(recovery)return result(3,'Review the recovery result',
        'The brain saved its preparation reply. Review the remaining evidence or exact owner decision; this phase is still paused.',
        'Review recovery result','recover_follow',{reasons:blockers});
      const held=(snapshot.commands||[]).find(c=>c.kind==='reconcile'&&c.payload?.message&&!c.conversationReply);
      if(held?.notification)return result(3,'Check the existing brain delivery',
        'An earlier message has an attempted native send but no reply. Its outcome must be reconciled before another wake.',
        'Inspect saved request','conversation',{reasons:blockers});
      return result(3,'Prepare safely from this checkpoint',
        'The phase stays paused. Review one bounded recovery-only brain turn. It will '+
        (held?'reuse your saved message':'create one focused instruction')+' and propose the next exact decision without starting development work.',
        'Review recovery preparation','recover',{reasons:blockers});
    }
    return result(2,'Paused at a checkpoint','Review Resume to continue the same phase with its existing scope and consumed budget.','Review Resume','resume');
  }
  if(run&&!['completed','blocked'].includes(run.status))return result(2,'Phase status needs reconciliation','The recorded phase is not in a recognized control state. Ask the brain to reconcile it before starting or resuming work.','Talk to project brain','conversation');
  const ended=run&&['completed','blocked'].includes(run.status);
  if(ended&&(!spec||run.phaseId===spec.phase.id))return result(3,run.status==='completed'?'Phase checkpoint reached':'Phase stopped with a blocker',
    run.status==='blocked'?'The safety stop needs an evidence check and an exact new phase proposal before another Play.':'Review the recorded result, then ask the brain to prepare the next unfinished roadmap phase. The next phase has its own review and Play.',
    run.status==='blocked'?'Prepare recovery proposal':'Prepare next phase','prepare',{checkpoint:run.checkpoint?.summary,reasons:run.status==='blocked'?blockers:[]});
  if(!spec)return result(0,'Choose what to build next','Ask the project brain to propose a bounded phase from your roadmap. You will review the scope, budget and stopping point before Play.','Prepare next phase','prepare');
  if(m.effectiveStatus!=='reviewed'||m.bindingIssues?.length)return result(1,'Review the proposed phase','Check the outcome, repository scope, budget and stopping point. Save and review the phase plan before Play.','Review phase plan','mission',{reasons:m.bindingIssues||[]});
  if(spec.authority.approvalMode!=='phase_delegated')return result(1,'Set phase approval authority','To use phase Play, review a plan that allows the brain to approve tasks inside this phase.','Edit phase plan','mission');
  if(s?.catalogRequired){
    const request=s.catalogRefresh;
    if(request?.status==='queued')return result(1,request.notification?.status==='unavailable'?'Codex check needs delivery':'Waiting for Codex readiness',
      'A request to check available models and efforts is saved. Inspect delivery below before sending another request. Play still needs your confirmation.','Inspect request delivery','request',{catalog:true});
    const issue=catalogReadinessIssue(request);
    if(issue)return result(1,issue.title,issue.detail,'Inspect Codex readiness','request',{catalog:true,requiresSetupChange:true});
    return result(1,'Check Codex before Play','The brain needs to refresh the available models and efforts for this phase. When it responds, return here to review Play.',request?.status==='failed'?'Retry Codex readiness':'Check Codex readiness','catalog',{catalog:true});
  }
  if(!s?.available)return result(1,'A prerequisite needs attention',s?.blocker||'Inspect project readiness to find the missing setup for this phase.','Inspect readiness','runReadiness');
  return result(1,'Ready to review Play','Review the exact phase and confirm when ready. The brain will stop at the checkpoint shown below.','Review Play','play');
}
function prepareRoadmapPhase(){
  if(busy||!connected){showNotice('Wait for the current request or reconnect before preparing a phase message.',true);return;}
  if(journeyPendingConversation(state)){
    navigateView('conversation');showNotice('Your saved request is still awaiting a reply. Inspect it before preparing another request.');return;
  }
  if(state?.recovery?.phaseStatus==='blocked'){
    focusAssistantConversation();assistantRequestStep('phase_prepare');return;
  }
  const key=workspaceId||'legacy',existing=brainDrafts.get(key)||(typeof loadBrainDraft==='function'?loadBrainDraft(key):null);
  if(existing?.text||existing?.request){navigateView('conversation');showNotice('Your existing message is preserved. Finish or discard it before preparing another phase request.');return;}
  const phase=state.standard?.run?.phaseId;
  const message='Review this project’s configured roadmap sources and latest retained results'+(phase?' for phase '+phase:'')+'. Prepare the next unfinished, bounded phase as a mission draft. Include the goal, measurable success criteria, repository and path scope, token budget, parallel-task limit, merge policy, exclusions and stopping checkpoint. Explain any prerequisite or unresolved checkpoint first. Preserve consumed usage and previous results. Save the draft for my review and reply in the project conversation with the result. Do not start Play or approve the phase.';
  brainDrafts.set(key,{text:message,confirmed:false,request:null});if(typeof saveBrainDraft==='function')saveBrainDraft(key,brainDrafts.get(key));
  navigateView('conversation');showNotice('Phase request prepared. Review the message below, then select the confirmation and Send to brain.');
  document.getElementById('brain-message')?.focus();
}
function journeyAction(action){
  if(action==='usage-check'){focusAssistantConversation();return assistantRequestStep('usage_check');}
  if(action==='budget'){navigateView('usage');const panel=document.getElementById('brain-budget-review');panel?.scrollIntoView({block:'start'});panel?.focus();return;}
  if(action==='close'){focusAssistantConversation();return assistantRequestStep('phase_close');}
  if(action==='pause-recover'){focusAssistantConversation();return assistantRequestStep('phase_pause_recovery');}
  if(action==='recover'||action==='recover_follow'){
    focusAssistantConversation();
    if(typeof developmentHelpUpdate==='function')developmentHelpUpdate();
    const next=document.getElementById('assistant-next-step');
    next?.scrollIntoView({block:'start'});
    const first=next?.querySelector('button:not([hidden]):not(:disabled)');
    if(first)first.focus({preventScroll:true});
    else if(next){next.setAttribute('tabindex','-1');next.focus({preventScroll:true});}
    return;
  }
  if(action==='reconcile'){focusAssistantConversation();return assistantRequestStep('phase_reconcile');}
  if(action==='refresh')return refresh();
  if(action==='prepare')return prepareRoadmapPhase();
  if(action==='catalog')return requestCatalogForPlay(state.standard);
  if(action==='request'){
    const issue=catalogReadinessIssue(state.standard?.catalogRefresh);
    journeyDetailsOpen.add((workspaceId||'legacy')+':'+(issue?'catalog-error:'+state.standard.catalogRefresh.id:'control-requests'));
    navigateView('operations');
    const record=document.getElementById(issue?'catalog-readiness-diagnostic':'control-request-history');
    record?.scrollIntoView({block:'start'});record?.querySelector('summary')?.focus();return;
  }
  if(['play','resume','pause'].includes(action))return reviewStandardControl(state.standard,action,state.standard?.run);
  if(action==='handoff'){navigateView('operations');const target=document.getElementById('brain-handoff-section');if(target){target.open=true;target.scrollIntoView({block:'start'});target.querySelector('summary')?.focus();}return;}
  if(action==='conversation'){
    const request=journeyPendingConversation(state),key=workspaceId||'legacy';
    if(request){
      // Match the durable conversation's createdAt/ID order, not whichever
      // history page or scroll position the owner happened to inspect last.
      const messages=(state.commands||[]).filter(c=>c.kind==='reconcile'&&c.payload?.message)
        .sort((a,b)=>{
          const time=(b.createdAt||0)-(a.createdAt||0);if(time)return time;
          const left=Array.from(b.id||''),right=Array.from(a.id||'');
          for(let i=0;i<Math.min(left.length,right.length);i++){
            const point=left[i].codePointAt(0)-right[i].codePointAt(0);if(point)return point;
          }
          return left.length-right.length;
        });
      if(typeof brainPages!=='undefined')brainPages.set(key,Math.floor(messages.findIndex(c=>c.id===request.id)/30));
      if(typeof brainRequestFocus!=='undefined')brainRequestFocus.set(key,request.id);
    }
  }
  navigateView(action);
}
function roadmapJourney(root){
  const snapshot=state,s=snapshot.standard,run=s?.run,m=snapshot.mission,spec=m?.document?.spec;
  let model=roadmapJourneyState(snapshot,connected);
  if(connected&&!model.strict&&!model.request&&model.action!=='handoff'&&!['running','stopping','paused'].includes(run?.status)&&missionDrafts.has(workspaceId))model={stage:0,title:'Your phase draft is open',detail:'Continue editing the unsaved phase plan, then review it before Play. Previous phase results remain available below.',label:'Continue phase draft',action:'mission'};
  const panel=el('section',null,'roadmap-journey');panel.setAttribute('aria-label','Roadmap development cycle');
  const steps=el('ol',null,'journey-steps');
  [['Plan','mission'],['Review & Play','roadmap'],['Develop','overview'],['Checkpoint','workers']].forEach(([name,target],index)=>{
    const li=el('li'),link=button(name,()=>navigateView(target));
    if(index===model.stage)link.setAttribute('aria-current','step');
    const number=el('span',String(index+1),'journey-step-number');link.prepend(number);li.append(link);steps.append(li);
  });panel.append(steps);
  const lead=el('div',null,'journey-lead'),copy=el('div');
  copy.append(el('p',(snapshot.workspace?.name||'Current project')+' · '+['PLAN','REVIEW','DEVELOP','CHECKPOINT'][model.stage],'eyebrow'),el('h2',model.title),el('p',model.detail,'journey-description'));
  const waiting=busy||standardCatalogInFlight.has(workspaceId);
  const actions=el('div',null,'journey-actions'),primary=button(model.label,()=>journeyAction(model.action),'primary');primary.disabled=waiting;
  if(waiting){primary.setAttribute('aria-describedby','journey-busy');actions.append(el('p','Finishing your current request…','muted'));actions.lastChild.id='journey-busy';}
  actions.append(primary);
  if(model.canPause){const pause=button('Pause at safe checkpoint',()=>journeyAction('pause'));pause.disabled=busy;actions.append(pause);}
  else if(model.stage===3&&model.action==='prepare')actions.append(button('Review phase results',()=>navigateView('workers')));
  else if(model.requiresSetupChange)actions.append(button('View reviewed phase plan',()=>navigateView('mission')));
  else if(model.action!=='conversation')actions.append(button('Talk to project brain',()=>navigateView('conversation')));
  lead.append(copy,actions);panel.append(lead);
  if(snapshot.recovery)recoverySummary(panel,snapshot.recovery,model.title!==snapshot.recovery.title);
  const latest=latestBrainReply(snapshot);
  if(latest){const reply=latest.conversationReply;panel.append(el('p','Brain replied · '+when(reply.at),'eyebrow'),narrative(reply.message,'Project brain reply'));}
  const usageWarning=priorPhaseUsageWarning(snapshot);
  if(usageWarning)panel.append(el('p',usageWarning,'journey-receipt'));
  if(model.reasons?.length){const reasons=el('ul',null,'journey-reasons');model.reasons.forEach(reason=>reasons.append(el('li',reason)));panel.append(reasons);}
  if(model.request){const delivery=commandPresentation(model.request);panel.append(el('p',delivery.label+'. '+delivery.detail,'journey-receipt'));}
  if(model.catalog){const status=catalogStatus(s.catalogRefresh);if(!model.requiresSetupChange)panel.append(el('p',status.title+'. '+status.detail,'journey-receipt'));catalogReadinessDetails(panel,s.catalogRefresh);scheduleCatalogFollowup(s);}
  if(model.checkpoint)panel.append(phaseNarrative(model.checkpoint,run?.tasks||[]));
  if(!model.strict&&(spec||run)){
    const samePhase=!run||spec?.phase.id===run.phaseId,active=run&&['running','paused','stopping'].includes(run.status);
    const limits=(active?run.limits:spec?.authority)||run?.limits||{};
    panel.append(el('h3',active?(samePhase?spec?.phase.title||run.phaseId:run.phaseId):spec?.phase.title||run.phaseId,'journey-phase-title'));
    const facts=el('dl',null,'journey-facts');
    const rows=[['Phase token budget',num(limits.tokenBudget)],['Parallel tasks',num(limits.maxParallelTasks)],
      ['Stopping checkpoint',spec&&(!active||samePhase)?spec.phase.checkpoint:'See the retained phase result']];
    for(const [label,value] of rows){const row=el('div'),dd=el('dd');dd.append(label==='Stopping checkpoint'?narrative(value,label):el('span',value));row.append(el('dt',label),dd);facts.append(row);}panel.append(facts);
    if(run){const tasks=run.tasks||[],settled=tasks.filter(t=>['completed','failed','not_created'].includes(t.status)).length;
      panel.append(el('p',`${!samePhase?'Previous phase '+run.phaseId+' · ':''}${settled} / ${tasks.length} tasks settled · Measured remaining tokens: ${s.measuredUsage?.remainingMeasured==null?'unknown':num(s.measuredUsage.remainingMeasured)} · `+(s.measuredUsage?'observed '+when(s.measuredUsage.collectedAt):'usage has not been measured'),'journey-receipt'));
    }
    const links=el('div',null,'journey-links');links.append(button('Phase plan & limits',()=>navigateView('mission')),button('Tasks & results',()=>navigateView('workers')),button('Token details',()=>navigateView('usage')));panel.append(links);
  }
  if(!model.strict&&standardPreviews.has(workspaceId))standardConfirmation(panel,s,run);
  root.append(panel);
}
function journeyReturn(root,label){
  const strip=el('nav',null,'journey-return');strip.setAttribute('aria-label','Development navigation');
  strip.append(button('← Roadmap & Play',()=>navigateView('roadmap')),el('span',label));root.append(strip);
}
