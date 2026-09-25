"use strict";
// A navigation projection of existing records. Only the existing signed controls
// can authorize Play, Resume or Pause; this module never submits them directly.
const journeyDetailsOpen=new Set();
function journeyDisclosure(key,title,build){
  const details=el('details',null,'journey-disclosure'),identity=(workspaceId||'legacy')+':'+key;
  details.open=journeyDetailsOpen.has(identity);details.append(el('summary',title));
  const body=el('div');build(body);details.append(body);
  details.addEventListener('toggle',()=>{if(!details.isConnected)return;if(details.open)journeyDetailsOpen.add(identity);else journeyDetailsOpen.delete(identity);});
  return details;
}
function roadmapJourneyState(snapshot,isConnected=true,now=Date.now()/1000){
  const s=snapshot.standard,run=s?.run,m=snapshot.mission,spec=m?.document?.spec;
  const result=(stage,title,detail,label,action,extra={})=>({stage,title,detail,label,action,...extra});
  if(!isConnected)return result(0,'Reconnect to see your next step','The last saved state may be out of date. Refresh the connection before reviewing or starting work.','Reconnect','refresh');
  const repos=snapshot.repositories;
  if(!snapshot.workspace||!Array.isArray(repos)||!repos.length||repos.some(r=>r.policyProfile!=='standard'))
    return result(0,'This project uses packet approvals','Review the approved queue and project readiness to continue this roadmap. Phase Play is available for configured standard projects.','Review approved queue','queue',{strict:true});
  const handoff=snapshot.brainHandoff?.handoff;
  if(handoff&&['prepared','candidate','received'].includes(handoff.status))return result(3,'Finish the brain handoff',
    handoff.status==='received'?'The replacement received its checkpoint. Project identity and final owner review still need to be resolved before continuing.':'A replacement brain is being prepared. Follow its recorded progress before continuing the phase.',
    'Review handoff progress','handoff',{canPause:run?.status==='running'});
  const pending=[...(snapshot.commands||[])].reverse().find(c=>run&&c.payload?.runId===run.id&&['standard_play','standard_pause','standard_resume'].includes(c.kind)&&['queued','processing'].includes(c.status));
  if(run?.status==='stopping')return result(2,'Pause requested','New work is fenced. The brain still needs to settle registered tasks and save a safe checkpoint.',pending?'Inspect request delivery':'Follow sessions',pending?'request':'overview',{request:pending});
  if(pending)return result(2,'Waiting for the brain’s receipt','Your '+pending.kind.replace('standard_','')+' request is saved. Inspect its delivery status before sending another request.','Inspect request delivery','request',{request:pending,canPause:run.status==='running'});
  const blockers=[...(s?.blockers||[])];
  if(run&&['running','paused'].includes(run.status)&&run.expiresAt<=now&&!blockers.some(x=>/expir/i.test(x)))blockers.push('The phase time limit has expired.');
  if(run?.status==='running'){
    if(blockers.length)return result(2,'This phase needs a checkpoint','New work is blocked. Pause at the next safe point, then review the reason below.','Pause at safe checkpoint','pause',{reasons:blockers});
    const count=snapshot.workflow?.openDecisions||0;
    if(count)return result(2,'Your decision is needed',`${count} open ${count===1?'decision needs':'decisions need'} your input. The phase keeps its reviewed scope.`, 'Review decisions','decisions',{canPause:true});
    return result(2,'Phase is active','Play is active up to the reviewed stopping checkpoint. Follow the sessions for observed task activity, or pause safely at any time.','Follow sessions','overview',{canPause:true});
  }
  if(run?.status==='paused'){
    if(blockers.length)return result(3,'Resolve the checkpoint before resuming','The saved phase cannot resume with its current limits or evidence. Ask the brain to explain the blocker and prepare the next review.','Prepare checkpoint follow-up','prepare',{reasons:blockers});
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
    return result(1,'Check Codex before Play','The brain needs to refresh the available models and efforts for this phase. When it responds, return here to review Play.',request?.status==='failed'?'Retry Codex readiness':'Check Codex readiness','catalog',{catalog:true});
  }
  if(!s?.available)return result(1,'A prerequisite needs attention',s?.blocker||'Inspect project readiness to find the missing setup for this phase.','Inspect readiness','runReadiness');
  return result(1,'Ready to review Play','Review the exact phase and confirm when ready. The brain will stop at the checkpoint shown below.','Review Play','play');
}
function prepareRoadmapPhase(){
  if(busy||!connected){showNotice('Wait for the current request or reconnect before preparing a phase message.',true);return;}
  if(state?.recovery?.phaseStatus==='blocked'){
    focusAssistantConversation();assistantRequestStep('phase_prepare');return;
  }
  const key=workspaceId||'legacy',existing=brainDrafts.get(key);
  if(existing?.text||existing?.request){navigateView('conversation');showNotice('Your existing message is preserved. Finish or discard it before preparing another phase request.');return;}
  const phase=state.standard?.run?.phaseId;
  const message='Review this project’s configured roadmap sources and latest retained results'+(phase?' for phase '+phase:'')+'. Prepare the next unfinished, bounded phase as a mission draft. Include the goal, measurable success criteria, repository and path scope, token budget, parallel-task limit, merge policy, exclusions and stopping checkpoint. Explain any prerequisite or unresolved checkpoint first. Preserve consumed usage and previous results. Save the draft for my review and reply in the project conversation with the result. Do not start Play or approve the phase.';
  brainDrafts.set(key,{text:message,confirmed:false,request:null});
  navigateView('conversation');showNotice('Phase request prepared. Review the message below, then select the confirmation and Send to brain.');
  document.getElementById('brain-message')?.focus();
}
function journeyAction(action){
  if(action==='refresh')return refresh();
  if(action==='prepare')return prepareRoadmapPhase();
  if(action==='catalog')return requestCatalogForPlay(state.standard);
  if(action==='request'){journeyDetailsOpen.add((workspaceId||'legacy')+':control-requests');navigateView('operations');document.getElementById('control-request-history')?.scrollIntoView({block:'start'});return;}
  if(['play','resume','pause'].includes(action))return reviewStandardControl(state.standard,action,state.standard?.run);
  if(action==='handoff'){navigateView('operations');const target=document.getElementById('brain-handoff-section');if(target){target.open=true;target.scrollIntoView({block:'start'});target.querySelector('summary')?.focus();}return;}
  navigateView(action);
}
function roadmapJourney(root){
  const snapshot=state,s=snapshot.standard,run=s?.run,m=snapshot.mission,spec=m?.document?.spec;
  let model=roadmapJourneyState(snapshot,connected);
  if(connected&&!model.strict&&model.action!=='handoff'&&!['running','stopping','paused'].includes(run?.status)&&missionDrafts.has(workspaceId))model={stage:0,title:'Your phase draft is open',detail:'Continue editing the unsaved phase plan, then review it before Play. Previous phase results remain available below.',label:'Continue phase draft',action:'mission'};
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
  else if(model.action!=='conversation')actions.append(button('Talk to project brain',()=>navigateView('conversation')));
  lead.append(copy,actions);panel.append(lead);
  if(snapshot.recovery)recoverySummary(panel,snapshot.recovery);
  if(model.reasons?.length){const reasons=el('ul',null,'journey-reasons');model.reasons.forEach(reason=>reasons.append(el('li',reason)));panel.append(reasons);}
  if(model.request){const delivery=commandPresentation(model.request);panel.append(el('p',delivery.label+'. '+delivery.detail,'journey-receipt'));}
  if(model.catalog){const status=catalogStatus(s.catalogRefresh);panel.append(el('p',status.title+'. '+status.detail,'journey-receipt'));scheduleCatalogFollowup(s);}
  if(model.checkpoint)panel.append(phaseNarrative(model.checkpoint,run?.tasks||[]));
  if(!model.strict&&(spec||run)){
    const samePhase=!run||spec?.phase.id===run.phaseId,active=run&&['running','paused','stopping'].includes(run.status);
    const limits=(active?run.limits:spec?.authority)||run?.limits||{};
    panel.append(el('h3',active?(samePhase?spec?.phase.title||run.phaseId:run.phaseId):spec?.phase.title||run.phaseId,'journey-phase-title'));
    const facts=el('dl',null,'journey-facts');
    const rows=[['Phase token budget',num(limits.tokenBudget)],['Parallel tasks',num(limits.maxParallelTasks)],
      ['Stopping checkpoint',samePhase&&spec?spec.phase.checkpoint:'See the retained phase result']];
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
