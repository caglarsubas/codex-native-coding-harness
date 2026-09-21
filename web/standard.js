"use strict";
const standardPreviews=new Map();
function standardPanel(root){
  const s=state.standard;if(!s)return;
  const panel=el('section',null,'mission-status'),run=s.run;
  panel.append(el('p','STANDARD PROJECT · COOPERATIVE NATIVE RUN','eyebrow'),el('h2',run?`Development ${run.status}`:'Play one reviewed phase'));
  panel.append(el('p',s.boundary,'muted'));
  panel.append(button('Review mission & next phase',()=>navigateView('mission')));
  if(state.meta?.brainId){const a=el('a','Open brain in Codex','button');a.href='codex://threads/'+encodeURIComponent(state.meta.brainId);panel.append(a);}
  if(s.blocker)panel.append(el('p',s.blocker,'checkpoint'));
  if(run){
    panel.append(el('p',`Phase ${run.phaseId} · ${run.tasks.length} / ${run.limits.maxTasks} tasks · expires ${when(run.expiresAt)}`));
    panel.append(table(['Budget observation','Value'],[
      ['Observed tokens (partial)',s.observedTokens===null?'Not observed':num(s.observedTokens)],['Tasks without token observations',num(s.unmeasuredTasks)],
      ['Reserved/spent conservative allowance',num(s.chargedAllowance)],['Remaining worker allowance',num(s.remainingAllowance)],
      ['Brain usage coverage',run.brainUsageCoverage],['Checkpoint reserve',num(run.limits.checkpointReserveTokens)]]));
    if(s.blockers?.length)panel.append(callout('Checkpoint required',s.blockers.join(' ')));
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
  }
  const operation=!run||['completed','blocked'].includes(run.status)?'play':run.status==='paused'?'resume':'pause';
  const label={play:'Review Play',resume:'Review Resume',pause:'Pause at safe checkpoint'}[operation];
  const requestButton=button(label,async()=>{
    if(busy)return;busy=true;
    try{
      const budget=state.mission?.document?.spec.authority.tokenBudget||1;
      const preview=await api('/api/standard/preview',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
        body:JSON.stringify({operation,contextHash:s.contextHash,brainAllowance:run?.brainAllowance||Math.max(1,Math.floor(budget*.2)),durationHours:8})});
      standardPreviews.set(workspaceId,preview);selected='standard-confirm';
    }catch(error){showNotice(error.message,true);}finally{busy=false;render();updateWorkspaceSelector();}
  },'primary');
  requestButton.disabled=busy||!connected||(operation==='play'&&!s.available)||run?.status==='stopping';panel.append(requestButton);
  const pending=standardPreviews.get(workspaceId);
  if(pending){
    panel.append(section('Confirm this exact phase',`Preview expires ${when(pending.preview.expiresAt)}`));
    panel.append(el('p',`Reserve ${num(pending.preview.brainAllowance)} tokens for the brain. Play lasts at most ${pending.preview.durationHours} hours. Phase limits and the available native model/effort catalog are bound to this review. Tasks remain retained; merge and archive are manual.`));
    if(state.mission?.document){
      const spec=state.mission.document.spec;
      panel.append(el('h3',spec.goal),el('p','Owner checkpoint: '+spec.phase.checkpoint),
        table(['Authorized scope','Paths / operations'],spec.phase.scope.map(row=>[row.repository,row.allowedPaths.join(', ')+' · '+row.operations.join(', ')])),
        table(['Limit','Value'],Object.entries(spec.authority).map(([key,value])=>[key,String(value)])),
        el('p','Models and efforts: '+(s.catalog?.models||[]).map(m=>m.model+' ('+m.efforts.join(', ')+')').join('; ')),
        el('p','Exact mission: '+state.mission.documentHash,'mono mission-hash'));
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
