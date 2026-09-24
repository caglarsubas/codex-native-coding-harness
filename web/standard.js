"use strict";
const standardPreviews=new Map();
const standardCatalogRequests=new Map(),standardCatalogTimers=new Map(),standardCatalogInFlight=new Set(),standardPlayIntents=new Set();
function catalogMissing(s){return (!s.run||['completed','blocked'].includes(s.run.status))&&!s.available&&s.catalogRequired===true;}
function catalogStatus(refresh){
  if(!refresh)return {title:'Native capabilities required',detail:'The dashboard will ask the designated brain to record the current model/effort catalog when you choose Review Play.'};
  if(refresh.status==='completed')return {title:'Native capabilities recorded',detail:refresh.result};
  if(refresh.status==='failed')return {title:'Capability refresh failed',detail:refresh.result||'The brain retained an observation error. Review the details before retrying.'};
  const notification=refresh.notification||{};
  if(notification.status==='accepted')return Date.now()/1000-refresh.createdAt>90
    ?{title:'Brain receipt overdue',detail:'Codex accepted the fixed request, but the catalog receipt is overdue. The request remains retained; the active heartbeat may reconcile it, otherwise open the brain to inspect the blocker.'}
    :{title:'Capability request sent',detail:'Codex accepted the fixed request. Waiting for the designated brain to record its ledger receipt.'};
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
  const key=workspaceId;standardPlayIntents.add(key);
  let request=standardCatalogRequests.get(key);
  const retained=s.catalogRefresh;
  if(retained&&retained.status==='queued')request={id:retained.id,contextHash:s.contextHash};
  else request={id:crypto.randomUUID(),contextHash:s.contextHash};
  standardCatalogRequests.set(key,request);
  if(standardCatalogInFlight.has(key))return;
  standardCatalogInFlight.add(key);
  try{
    const result=await api('/api/standard/catalog-refresh',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(request)});
    const status=catalogStatus({...result,deliveryAttempts:(result.notificationHistory||[]).length+(result.notification?1:0),maxDeliveryAttempts:3});
    showNotice(status.title+'. '+status.detail);await refresh();
  }catch(error){if(!error.workspaceChanged)showNotice(error.message,true);}
  finally{standardCatalogInFlight.delete(key);}
}
async function reviewStandardControl(s,operation,run){
  if(busy)return;busy=true;
  try{
    const budget=state.mission?.document?.spec.authority.tokenBudget||1;
    const preview=await api('/api/standard/preview',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
      body:JSON.stringify({operation,contextHash:s.contextHash,brainAllowance:run?.brainAllowance||Math.max(1,Math.floor(budget*.2)),durationHours:8,measureUsage:operation==='play'})});
    standardPreviews.set(workspaceId,preview);standardPlayIntents.delete(workspaceId);selected='standard-confirm';
  }catch(error){showNotice(error.message,true);}finally{busy=false;render();updateWorkspaceSelector();}
}
function standardPanel(root){
  const s=state.standard;if(!s)return;
  const panel=el('section',null,'mission-status'),run=s.run;
  panel.append(el('p','STANDARD PROJECT · COOPERATIVE NATIVE RUN','eyebrow'),el('h2',run?`Development ${run.status}`:'Play one reviewed phase'));
  panel.append(el('p',s.boundary,'muted'));
  panel.append(button('Review mission & next phase',()=>navigateView('mission')));
  if(state.meta?.brainId){const a=el('a','Open brain in Codex','button');a.href='codex://threads/'+encodeURIComponent(state.meta.brainId);panel.append(a);}
  const needsCatalog=catalogMissing(s);
  if(needsCatalog){const status=catalogStatus(s.catalogRefresh);panel.append(callout(status.title,status.detail));scheduleCatalogFollowup(s);}
  else if(s.blocker)panel.append(el('p',s.blocker,'checkpoint'));
  if(run){
    panel.append(el('p',`Phase ${run.phaseId} · ${run.tasks.length} / ${run.limits.maxTasks} tasks · expires ${when(run.expiresAt)}`));
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
    if(s.blockers?.length)panel.append(callout('Checkpoint required',s.blockers.join(' ')));
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
    if(run.checkpoint)panel.append(el('p',run.checkpoint.summary,'checkpoint'));
    if(run.tasks.length)panel.append(table(['Task / settings requested','Progress','Evidence'],run.tasks.map(t=>{
      const links=el('div');missionDocument(links,t.seedHash,'Inheritance seed');
      if(t.result)missionDocument(links,t.result,'Result & preservation');
      if(t.threadId){const a=el('a','Open Codex task','button');a.href='codex://threads/'+encodeURIComponent(t.threadId);links.append(a);}
      return [textCell(t.title,`${t.model} · ${t.effort}`),textCell(t.status,t.nativeStatus),links];
    })));
    const history=el('details');history.append(el('summary','Run history · latest 30 retained versions'));
    for(const item of s.history||[])missionDocument(history,item.documentHash,`${when(item.at)} · ${item.operation} · v${item.revision} · ${item.status}`);
    panel.append(history);
    if(['paused','completed','blocked'].includes(run.status))standardBrainHandoff(panel);
  }
  const operation=!run||['completed','blocked'].includes(run.status)?'play':run.status==='paused'?'resume':'pause';
  const label={play:'Review Play',resume:'Review Resume',pause:'Pause at safe checkpoint'}[operation];
  const requestButton=button(label,async()=>{
    if(needsCatalog){await requestCatalogForPlay(s);return;}
    await reviewStandardControl(s,operation,run);
  },'primary');
  requestButton.disabled=busy||!connected||(operation==='play'&&!s.available&&!needsCatalog)||run?.status==='stopping';panel.append(requestButton);
  if(needsCatalog&&s.catalogRefresh?.status==='queued'){requestButton.textContent='Waiting for native capabilities';requestButton.disabled=true;}
  if(needsCatalog&&s.catalogRefresh?.status==='failed')requestButton.textContent='Retry capability refresh';
  if(operation==='play'&&s.available&&standardPlayIntents.has(workspaceId)&&!standardPreviews.has(workspaceId)&&!busy)setTimeout(()=>reviewStandardControl(s,operation,run),0);
  const pending=standardPreviews.get(workspaceId);
  if(pending){
    panel.append(section('Confirm this exact phase',`Preview expires ${when(pending.preview.expiresAt)}`));
    panel.append(el('p',`Reserve ${num(pending.preview.brainAllowance)} tokens for the brain. Play lasts at most ${pending.preview.durationHours} hours. ${pending.preview.measureUsage?'Registered local task usage must be refreshed before new effects; missing coverage stops new effects. ':''}Phase limits and the available native model/effort catalog are bound to this review. Tasks remain retained; archive is manual. Merge is manual unless the exact reviewed phase explicitly opts in and repository policy permits it.`));
    if(state.mission?.document){
      const spec=state.mission.document.spec;
      panel.append(el('h3',spec.goal),el('p','Owner checkpoint: '+spec.phase.checkpoint),
        table(['Authorized scope','Paths / operations'],spec.phase.scope.map(row=>[row.repository,row.allowedPaths.join(', ')+' · '+row.operations.join(', ')])),
        table(['Limit','Value'],Object.entries(spec.authority).map(([key,value])=>[key,String(value)])),
        el('p','Models and efforts: '+(s.catalog?.models||[]).map(m=>m.model+' ('+m.efforts.join(', ')+')').join('; ')),
        el('p','Exact mission: '+state.mission.documentHash,'mono mission-hash'),
        el('p',spec.authority.mergeMode==='brain_exact_pr_v1'?'This phase opts in to one exact PR merge. The installed launcher must first be updated to the exact compatible merged source; a stale schema-1-only launcher is refused.':'This phase keeps manual merge.'));
    }
    const label=el('label'),check=el('input');check.type='checkbox';label.append(check,el('span','I approve the separate cooperative contract and this exact phase/control, including its observed-usage gaps.'));
    const confirm=button('Confirm '+pending.preview.operation,async()=>{
      if(busy||!check.checked)return;busy=true;
      try{const result=await api('/api/standard/confirm',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({...pending,confirmed:true})});
        standardPreviews.delete(workspaceId);selected=null;showNotice(result.notification?.detail||result.result);await refresh();
      }catch(error){showNotice(error.message+' Inspect the retained run before retrying.',true);}finally{busy=false;render();updateWorkspaceSelector();}
    },'primary');confirm.disabled=true;check.onchange=()=>{confirm.disabled=!check.checked||busy;};
    panel.append(label,confirm,button('Cancel review',()=>{standardPreviews.delete(workspaceId);selected=null;render();}));
  }
  root.append(panel);
}

const handoffPreviews=new Map();
function standardBrainHandoff(panel){
  const handoff=state.brainHandoff?.handoff,pending=handoffPreviews.get(workspaceId);
  panel.append(section('Brain handoff','A replacement is reviewed at a saved checkpoint. The project retains its usage and authority history.'));
  if(handoff)panel.append(el('p',`${handoff.status} · package ${handoff.packageHash} · old task ${handoff.oldBrainId}`,'subline'));
  if(handoff?.candidate)panel.append(el('p',`Candidate ${handoff.candidate.taskId} · ${handoff.candidate.projectId} · ${handoff.candidate.observation}`,'subline'));
  if(handoff?.candidate)panel.append(el('p',handoff.nativeMembership
    ?`Codex task list: ${handoff.nativeMembership.projectId} · ${handoff.nativeMembership.hostId} · ${handoff.nativeMembership.status} · observed ${new Date(handoff.nativeMembership.observedAt*1000).toLocaleString()} · brain-imported, not cryptographic attestation`
    :'Codex task-list project membership not yet recorded; final rebinding is blocked.','subline'));
  if(handoff?.receipt){
    panel.append(el('p',`Replacement receipt: ${handoff.receipt.summary}`,'subline'));
    panel.append(el('p',`Native final reply observed ${handoff.receiptEvidence?.observedAt?new Date(handoff.receiptEvidence.observedAt*1000).toLocaleString():'unknown'} · project membership needs a separate Codex task-list observation`,'subline'));
  }
  if(!handoff||['cancelled','complete'].includes(handoff.status))panel.append(button('Review brain handoff',async()=>{
    try{handoffPreviews.set(workspaceId,{stage:'prepare',...(await api('/api/brain-handoff/preview',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:'{}'}))});render();}
    catch(error){showNotice(error.message,true);}
  }));
  const membershipFresh=handoff?.nativeMembership?.status==='idle'&&handoff.nativeMembership.observedAt>=handoff?.receiptEvidence?.observedAt&&Date.now()/1000-handoff.nativeMembership.observedAt<=3600;
  if(handoff?.status==='received'&&membershipFresh)panel.append(button('Review replacement receipt',async()=>{
    try{handoffPreviews.set(workspaceId,{stage:'final',...(await api('/api/brain-handoff/final-preview',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:'{}'}))});render();}
    catch(error){showNotice(error.message,true);}
  }));
  if(handoff?.status==='received'&&!membershipFresh)panel.append(el('p','A fresh idle Codex task-list observation after the final reply is required before final review.','muted'));
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
