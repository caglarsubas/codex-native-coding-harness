"use strict";
const standardPreviews=new Map();
const standardCatalogRequests=new Map(),standardCatalogTimers=new Map(),standardCatalogInFlight=new Set();
function catalogMissing(s){return (!s.run||['completed','blocked'].includes(s.run.status))&&!s.available&&s.catalogRequired===true;}
function catalogStatus(refresh){
  if(!refresh)return {title:'Codex readiness has not been checked',detail:'Choose Check Codex readiness to ask the designated brain for available models and efforts. This does not start development.'};
  if(refresh.status==='completed')return {title:'Native capabilities recorded',detail:refresh.result};
  if(refresh.status==='failed')return {title:'Capability refresh failed',detail:refresh.result||'The brain retained an observation error. Review the details before retrying.'};
  const notification=refresh.notification||{};
  if(notification.status==='accepted')return Date.now()/1000-refresh.createdAt>90
    ?{title:'Brain receipt overdue',detail:'Native delivery was acknowledged, but the catalog receipt is overdue. A legacy desktop queue may not start an unloaded brain; inspect the bound host and retained request before further action.'}
    :{title:'Capability request sent',detail:notification.nativeDelivery==='owned_turn_start'
      ?'The bound Codex host started a turn. Waiting for the designated brain’s separate ledger receipt.'
      :'Native delivery was acknowledged, not received by the brain. Waiting for the designated brain’s separate ledger receipt; a legacy desktop queue may not start an unloaded task.'};
  if(notification.status==='uncertain'||notification.status==='sending')return {title:'Delivery unconfirmed',detail:'The request is retained and will not be resent automatically. Waiting for the brain or heartbeat to reconcile the exact request.'};
  if(notification.status==='unavailable')return {title:'Automatic delivery unavailable',detail:`${notification.detail} Safe delivery attempt ${refresh.deliveryAttempts} of ${refresh.maxDeliveryAttempts}.`};
  return {title:'Capability request saved',detail:'The request is retained but has not been sent. A stopped or parked brain must be explicitly resumed; this request never resumes it.'};
}
function scheduleCatalogFollowup(s){
  const key=workspaceId,refresh=s.catalogRefresh;if(!refresh||refresh.status!=='queued'||standardCatalogTimers.has(key))return;
  const notification=refresh.notification||{},safeRetry=notification.status==='unavailable'&&refresh.deliveryAttempts<refresh.maxDeliveryAttempts;
  const recent=Date.now()/1000-refresh.createdAt<90;
  if(!safeRetry&&!recent)return;
  const delay=safeRetry?(refresh.deliveryAttempts===1?2000:5000):2500;
  standardCatalogTimers.set(key,setTimeout(async()=>{
    standardCatalogTimers.delete(key);if(workspaceId!==key||standardCatalogInFlight.has(key))return;
    standardCatalogInFlight.add(key);
    try{
      if(safeRetry)await api('/api/standard/catalog-refresh',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({id:refresh.id,contextHash:s.contextHash})});
      await refreshStateForCatalog(key);
    }catch(error){if(!error.workspaceChanged)showNotice(error.message,true);}
    finally{standardCatalogInFlight.delete(key);}
  },delay));
}
async function refreshStateForCatalog(key){if(workspaceId===key)await refresh();}
async function requestCatalogForPlay(s){
  const key=workspaceId;
  let request=standardCatalogRequests.get(key);
  const retained=s.catalogRefresh;
  if(retained&&retained.status==='queued')request={id:retained.id,contextHash:s.contextHash};
  else request={id:crypto.randomUUID(),contextHash:s.contextHash};
  standardCatalogRequests.set(key,request);
  if(standardCatalogInFlight.has(key))return;
  standardCatalogInFlight.add(key);
  render();
  try{
    const result=await api('/api/standard/catalog-refresh',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(request)});
    const status=catalogStatus({...result,deliveryAttempts:(result.notificationHistory||[]).length+(result.notification?1:0),maxDeliveryAttempts:3});
    showNotice(status.title+'. '+status.detail);await refresh();
  }catch(error){if(!error.workspaceChanged)showNotice(error.message,true);}
  finally{standardCatalogInFlight.delete(key);if(workspaceId===key)render();}
}
async function reviewStandardControl(s,operation,run){
  if(busy||!connected)return;busy=true;
  const key=workspaceId;
  try{
    const budget=state.mission?.document?.spec.authority.tokenBudget||1;
    const preview=await api('/api/standard/preview',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
      body:JSON.stringify({operation,contextHash:s.contextHash,brainAllowance:run?.brainAllowance||Math.max(1,Math.floor(budget*.2)),durationHours:8,measureUsage:operation==='play'})});
    if(workspaceId!==key)return;
    standardPreviews.set(key,preview);selected='standard-confirm';
  }catch(error){if(!error.workspaceChanged)showNotice(error.message,true);}finally{busy=false;render();updateWorkspaceSelector();}
  const review=document.getElementById('phase-control-review');if(review){review.scrollIntoView({block:'start'});review.focus({preventScroll:true});}
}
function standardPanel(root,mode='all'){
  const s=state.standard;if(!s)return;
  const panel=el('section',null,'mission-status'),run=s.run;
  panel.append(el('p','STANDARD PROJECT','eyebrow'),el('h2',run?`Phase ${run.phaseId} · ${run.status}`:'No phase has started'));
  if(mode==='all'){
    panel.append(el('p',s.boundary,'muted'),button('Review mission & next phase',()=>navigateView('mission')));
    if(state.meta?.brainId){const a=el('a','Open brain in Codex','button');a.href='codex://threads/'+encodeURIComponent(state.meta.brainId);panel.append(a);}
  }
  const needsCatalog=catalogMissing(s);
  if(mode==='all'&&needsCatalog){const status=catalogStatus(s.catalogRefresh);panel.append(callout(status.title,status.detail));scheduleCatalogFollowup(s);}
  else if(mode==='all'&&s.blocker)panel.append(el('p',s.blocker,'checkpoint'));
  if(run){
    panel.append(el('p',`Phase ${run.phaseId} · ${run.tasks.length} / ${run.limits.maxTasks} tasks · expires ${when(run.expiresAt)}`));
    if(['all','usage'].includes(mode)){
    panel.append(table(['Budget observation','Value'],[
      ['Observed tokens (partial)',s.observedTokens===null?'Not observed':num(s.observedTokens)],['Tasks without token observations',num(s.unmeasuredTasks)],
      ['Reserved/spent conservative allowance',num(s.chargedAllowance)],['Remaining worker allowance',num(s.remainingAllowance)],
      ['Brain usage coverage',run.brainUsageCoverage],['Checkpoint reserve',num(run.limits.checkpointReserveTokens)]]));
    if(run.usageGuardVersion){
      const usage=s.measuredUsage;
      panel.append(section('Phase token measurement','Local Codex session counters; cached input is included. This is a cooperative checkpoint, not a provider billing cap.'));
      panel.append(table(['Measure','Observed'],[
        ['Input',usage?num(usage.tokens.input_tokens):'Unknown'],
        ['Cached input',usage?num(usage.tokens.cached_input_tokens):'Unknown'],
        ['Uncached input',usage?num(usage.tokens.input_tokens-usage.tokens.cached_input_tokens):'Unknown'],
        ['Output',usage?num(usage.tokens.output_tokens):'Unknown'],
        ['Reasoning within output',usage?num(usage.tokens.reasoning_output_tokens):'Unknown'],
        ['Total observed',usage?num(usage.tokens.total_tokens):'Unknown'],
        ['Observation',usage?when(usage.collectedAt):'Not measured'],
        ['Coverage',usage?usage.coverage:'Unknown'],
        ['Gaps',usage?(usage.gaps.join(', ')||'None observed'):'Unmeasured'],
        ['Measured remaining',usage?.remainingMeasured===null||!usage?'Unknown':num(usage.remainingMeasured)]]));
      if(s.closeoutUsage){
        const closeout=s.closeoutUsage;
        panel.append(el('p',`Post-checkpoint closeout: ${num(closeout.tokens.total_tokens)} observed tokens · ${closeout.coverage} · ${closeout.gaps.join(', ')||'no recorded gap'} · observed ${when(closeout.collectedAt)}. Not included in phase total.`, 'subline'));
      }
      panel.append(button('Measure registered task usage',async()=>{
        try{await api('/api/standard/usage-refresh',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({runId:run.id})});await refresh();}
        catch(error){showNotice(error.message,true);}
      }));
    }
    }
    if(['all','operations'].includes(mode)&&s.blockers?.length)panel.append(callout('Checkpoint required',s.blockers.join(' ')));
    if(['all','tasks'].includes(mode)){
    panel.append(el('p',run.limits.mergeMode==='brain_exact_pr_v1'?'Merge capability: one exact PR; requires independent checks by the designated brain.':'Merge capability: manual (default).'));
    if(run.merges?.length){
      panel.append(section('Exact PR merge history','Prepared, issued, uncertain, merged and not-merged are merge states only. They do not establish semantic correctness, CI, deployment, runtime, archival or phase acceptance. Unknown delivery is reconciled, never resent.'));
      panel.append(table(['PR / exact head','Merge state','Retained evidence'],run.merges.map(m=>{
        const evidence=el('div');missionDocument(evidence,m.bindingHash,'Immutable merge binding');
        if(m.observationHash)missionDocument(evidence,m.observationHash,'Merge verification / reconciliation');
        if(m.receiptHash)missionDocument(evidence,m.receiptHash,'Delivery receipt');
        return [textCell(m.prUrl,m.headSHA),m.status,evidence];
      })));
    }
    if(run.checkpoint)panel.append(phaseNarrative(run.checkpoint.summary,run.tasks));
    if(run.tasks.length)panel.append(table(['Task / settings requested','Progress','Evidence'],run.tasks.map(t=>{
      const links=el('div');missionDocument(links,t.seedHash,'Inheritance seed');
      if(t.result)missionDocument(links,t.result,'Result & preservation');
      if(t.threadId){const a=el('a','Open Codex task','button');a.href='codex://threads/'+encodeURIComponent(t.threadId);links.append(a);}
      return [textCell(t.title,`${t.model} · ${t.effort}`),textCell(t.status,t.nativeStatus),links];
    })));
    if(!run.tasks.length)panel.append(el('p','No tasks have been registered for this phase yet. Follow the brain conversation for its next update.','muted'));
    }
    if(['all','operations'].includes(mode)){
    const history=el('details');history.append(el('summary','Run history · latest 30 retained versions'));
    for(const item of s.history||[])missionDocument(history,item.documentHash,`${when(item.at)} · ${item.operation} · v${item.revision} · ${item.status}`);
    panel.append(history);
    if(['paused','completed','blocked'].includes(run.status)){
      if(mode==='all')standardBrainHandoff(panel);
      else {const handoff=journeyDisclosure('brain-handoff','Brain replacement & recovery',body=>standardBrainHandoff(body));handoff.id='brain-handoff-section';panel.append(handoff);}
    }
    }
  }
  if(mode!=='all'){root.append(panel);return;}
  const operation=!run||['completed','blocked'].includes(run.status)?'play':run.status==='paused'?'resume':'pause';
  const label={play:'Review Play',resume:'Review Resume',pause:'Pause at safe checkpoint'}[operation];
  const requestButton=button(label,async()=>{
    if(needsCatalog){await requestCatalogForPlay(s);return;}
    await reviewStandardControl(s,operation,run);
  },'primary');
  requestButton.disabled=busy||!connected||(operation==='play'&&!s.available&&!needsCatalog)||run?.status==='stopping';panel.append(requestButton);
  if(needsCatalog&&s.catalogRefresh?.status==='queued'){requestButton.textContent='Waiting for native capabilities';requestButton.disabled=true;}
  if(needsCatalog&&s.catalogRefresh?.status==='failed')requestButton.textContent='Retry capability refresh';
  standardConfirmation(panel,s,run);
  root.append(panel);
}
function standardConfirmation(parent,s,run){
  const pending=standardPreviews.get(workspaceId);
  if(pending){
    const key=workspaceId;
    const panel=el('section',null,'standard-confirmation');panel.id='phase-control-review';panel.tabIndex=-1;
    const operation=pending.preview.operation;
    const invalid=()=>!connected||workspaceId!==key||state.standard?.contextHash!==pending.preview.contextHash||pending.preview.expiresAt<=Date.now()/1000;
    if(invalid()){
      panel.append(section('Review needs refreshing','The connection, phase state or review deadline changed. No new approval has been recorded.'),button('Discard outdated review',()=>{standardPreviews.delete(key);selected=null;render();}));parent.append(panel);return;
    }
    panel.append(section(operation==='pause'?'Pause at a safe checkpoint':operation==='resume'?'Resume this phase':'Review this phase before Play',`Review expires ${when(pending.preview.expiresAt)}`));
    panel.append(el('p',operation==='pause'?'The brain will stop new work and settle registered tasks at a safe checkpoint. Follow the sessions until the phase reports paused.':operation==='resume'?'Continue this saved phase with its existing limits and consumed budget.':`Reserve ${num(pending.preview.brainAllowance)} tokens for the brain within the phase budget. Play lasts at most ${pending.preview.durationHours} hours. ${pending.preview.measureUsage?'Missing usage coverage stops new effects. ':''}The brain stops at the reviewed checkpoint.`));
    if(operation!=='pause'&&state.mission?.document){
      const spec=state.mission.document.spec;
      panel.append(el('h3',spec.goal),el('p','Owner checkpoint: '+spec.phase.checkpoint),
        table(['Authorized scope','Paths / operations'],spec.phase.scope.map(row=>[row.repository,row.allowedPaths.join(', ')+' · '+row.operations.join(', ')])),
        table(['Limit','Value'],[['Token budget',num(spec.authority.tokenBudget)],['Checkpoint reserve',num(spec.authority.checkpointReserveTokens)],['Parallel tasks',num(spec.authority.maxParallelTasks)],['Total tasks',num(spec.authority.maxTasks)]]),
        el('p',spec.authority.mergeMode==='brain_exact_pr_v1'?'The brain may cross-check and merge an exact PR within this reviewed phase and repository policy.':'You review and merge pull requests manually.'));
      for(const [title,items] of [['Success criteria',spec.successCriteria],['Stop sooner if…',spec.phase.stopConditions],['Excluded from this phase',spec.exclusions]]){
        const list=el('ul');for(const item of items)list.append(el('li',item));panel.append(el('h3',title),list);
      }
      const exact=el('details');exact.append(el('summary','Exact plan & available Codex settings'),el('p','Models and efforts: '+(s.catalog?.models||[]).map(m=>m.model+' ('+m.efforts.join(', ')+')').join('; ')),el('p','Exact mission: '+state.mission.documentHash,'mono mission-hash'));panel.append(exact);
    }
    const label=el('label'),check=el('input');check.type='checkbox';label.append(check,el('span',operation==='pause'?'Pause this phase at its next safe checkpoint.':'I approve this exact phase/control and its cooperative usage limits, including any observation gaps.'));
    const confirm=button('Confirm '+pending.preview.operation,async()=>{
      if(busy||!check.checked)return;
      if(invalid()){showNotice('This review is no longer current. Discard it and review the latest phase state.',true);render();return;}
      busy=true;confirm.disabled=true;check.disabled=true;cancel.disabled=true;confirm.textContent='Saving request…';help.textContent='Saving this exact control. Wait for the retained result before sending another request.';updateWorkspaceSelector();
      try{const result=await api('/api/standard/confirm',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({...pending,confirmed:true})});
        standardPreviews.delete(key);selected=null;showNotice(result.notification?.detail||result.result);await refresh();
      }catch(error){showNotice(error.message+' Inspect the retained run before retrying.',true);}finally{busy=false;render();updateWorkspaceSelector();}
    },'primary');confirm.disabled=true;check.onchange=()=>{confirm.disabled=!check.checked||busy||invalid();};
    const help=el('p','Select the confirmation above to enable this action.','muted');help.id='phase-confirmation-help';confirm.setAttribute('aria-describedby',help.id);
    const cancel=button('Cancel review',()=>{if(busy)return;standardPreviews.delete(key);selected=null;render();});
    panel.append(label,help,confirm,cancel);
    parent.append(panel);
  }
}

const handoffPreviews=new Map();
function standardBrainHandoff(panel){
  const handoff=state.brainHandoff?.handoff,readiness=state.brainHandoff?.readiness,pending=handoffPreviews.get(workspaceId);
  panel.append(section('Brain handoff','A replacement is reviewed at a saved checkpoint. The project retains its usage and authority history.'));
  if(readiness?.blockers?.length)panel.append(el('p',`Before owner review: ${readiness.blockers.join(' · ')}`,'muted'));
  if(handoff)panel.append(el('p',`${handoff.status} · package ${handoff.packageHash} · old task ${handoff.oldBrainId}`,'subline'));
  if(handoff?.status==='prepared')panel.append(el('p',state.brainNotification?.status==='disabled'
    ?'Preparation was saved, but immediate brain notification is off. Open the designated brain in Codex and ask it to process this exact handoff once; do not confirm preparation again or use Resume.'
    :'Preparation was saved. The existing brain must create one replacement task; notification delivery alone does not prove creation. Do not use Resume for this handoff.','muted'));
  if(handoff?.status==='candidate')panel.append(el('p','One replacement task has been recorded. Wait for its final package receipt; do not create or resend another task.','muted'));
  if(handoff?.candidate)panel.append(el('p',`Candidate ${handoff.candidate.taskId} · ${handoff.candidate.projectId} · ${handoff.candidate.observation}`,'subline'));
  if(handoff?.candidate){const task=el('a','Open replacement task in Codex','button');task.href='codex://threads/'+encodeURIComponent(handoff.candidate.taskId);panel.append(task);}
  if(handoff?.candidate)panel.append(el('p',handoff.nativeMembership
    ?`Codex task list: ${handoff.nativeMembership.projectId} · ${handoff.nativeMembership.hostId} · ${handoff.nativeMembership.status} · observed ${new Date(handoff.nativeMembership.observedAt*1000).toLocaleString()} · brain-imported, not cryptographic attestation`
    :'Codex task-list project membership not yet recorded; final rebinding is blocked.','subline'));
  if(handoff?.receipt){
    panel.append(el('p',`Replacement receipt: ${handoff.receipt.summary}`,'subline'));
    panel.append(el('p',`Native final reply observed ${handoff.receiptEvidence?.observedAt?new Date(handoff.receiptEvidence.observedAt*1000).toLocaleString():'unknown'} · project membership needs a separate Codex task-list observation`,'subline'));
  }
  if(!handoff||['cancelled','complete'].includes(handoff.status)){
    const prepare=button('Review brain handoff',async()=>{
    try{handoffPreviews.set(workspaceId,{stage:'prepare',...(await api('/api/brain-handoff/preview',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:'{}'}))});render();}
    catch(error){showNotice(error.message,true);}
    });prepare.disabled=readiness?.canPrepare===false;panel.append(prepare);
  }
  const membershipFresh=handoff?.nativeMembership?.status==='idle'&&handoff.nativeMembership.observedAt>=handoff?.receiptEvidence?.observedAt&&Date.now()/1000-handoff.nativeMembership.observedAt<=3600;
  if(handoff?.status==='received'&&readiness?.canFinalize&&membershipFresh)panel.append(button('Review replacement receipt',async()=>{
    try{handoffPreviews.set(workspaceId,{stage:'final',...(await api('/api/brain-handoff/final-preview',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:'{}'}))});render();}
    catch(error){showNotice(error.message,true);}
  }));
  if(handoff?.status==='received'&&(!readiness?.canFinalize||!membershipFresh))panel.append(el('p',handoff.nativeMembership
    ?'Final review waits for every server-side checkpoint gate and fresh idle task evidence. A new native observation is required if this one expires; Refresh alone does not renew it.'
    :'The receipt is recorded, but final review needs separately verified native task identity and project evidence. Refresh alone cannot supply missing evidence; Resume is unrelated.','muted'));
  if(!pending)return;
  panel.append(el('p',`Review expires ${when(pending.preview.expiresAt)}. ${pending.stage==='prepare'?'The existing brain will create one native replacement and the new task must acknowledge the package.':'This changes the designated brain binding; the phase remains paused.'}`,'muted'));
  if(pending.stage==='prepare')panel.append(el('pre',JSON.stringify(pending.package,null,2),'detail'));
  else panel.append(el('pre',JSON.stringify(pending.handoff,null,2),'detail'));
  const label=el('label'),box=el('input');box.type='checkbox';
  label.append(box,el('span','I reviewed this exact checkpoint, task identity, tool-reported project membership and handoff boundary.'));
  const confirm=button(pending.stage==='prepare'?'Confirm handoff preparation':'Confirm replacement brain',async()=>{
    if(!box.checked)return;
    const endpoint=pending.stage==='prepare'?'/api/brain-handoff/confirm':'/api/brain-handoff/final-confirm';
    const body=pending.stage==='prepare'?{preview:pending.preview,package:pending.package,signature:pending.signature,confirmed:true}
      :{preview:pending.preview,signature:pending.signature,confirmed:true};
    try{const result=await api(endpoint,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});
      handoffPreviews.delete(workspaceId);showNotice(result.result||'Brain handoff recorded. Inspect the retained status.');await refresh();}
    catch(error){showNotice(error.message,true);}
  },'primary');confirm.disabled=true;box.onchange=()=>{confirm.disabled=!box.checked;};
  panel.append(label,confirm,button('Cancel review',()=>{handoffPreviews.delete(workspaceId);render();}));
}
