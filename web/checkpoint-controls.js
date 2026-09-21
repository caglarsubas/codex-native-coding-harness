"use strict";
const checkpointDecisions=new Map(),checkpointDrafts=new Map(),checkpointPreviews=new Map(),checkpointDecisionPending=new Map(),checkpointDecisionDetails=new Map();
function checkpointDecisionDisclosure(key,label){
  const details=el('details'),id=workspaceId+':'+key;details.open=checkpointDecisionDetails.get(id)||false;
  details.append(el('summary',label));details.addEventListener('toggle',()=>checkpointDecisionDetails.set(id,details.open));return details;
}
function checkpointDecisionCurrent(entry){return entry&&entry.generation===workspaceGeneration;}
function checkpointDecisionStale(report){return report.workspaceRevision!==state.meta.revision||!(Date.now()/1000-report.inspectedAt>=0&&Date.now()/1000-report.inspectedAt<=60);}
function checkpointDecisionView(root){
  const report=checkpointDecisions.get(workspaceId),pending=checkpointDecisionPending.has(workspaceId),panel=el('section',null,'mission-status');
  panel.append(el('p',state.workspace.name+' · OWNER DECISION','eyebrow'),el('h2','Decide what may come next'),
    el('p','Review the saved checkpoint and exact next mission before a future run can be authorized. This decision does not accept a phase, start work, resume the brain or enable Play.'));
  const inspect=button(pending?'Inspecting saved decisions…':report?'Inspect decisions again':'Inspect checkpoint decisions',inspectCheckpointDecisions,'primary');inspect.disabled=pending||busy||!connected;panel.append(inspect);root.append(panel);
  if(!report){root.append(el('p','No decision inspection in this tab. Opening this page does not inspect proofs or change authority.','muted'));return;}
  root.append(el('p',`${checkpointDecisionStale(report)?'Earlier inspection · inspect again':'Saved local evidence · not live status'} · ${when(report.inspectedAt)}`,'muted'));
  if(report.status==='unavailable'){root.append(callout('Decision evidence unavailable','Retained review or withdrawal evidence is missing, changed or exceeds inspection limits. Ask the brain/operator to reconcile it. No fallback authority is offered.'));return;}
  if(!report.canReview)root.append(callout('Next-phase review unavailable',report.reviewBlocker));
  let entry=checkpointPreviews.get(workspaceId);
  if(entry&&!checkpointDecisionCurrent(entry)){checkpointPreviews.delete(workspaceId);entry=null;}
  if(entry){selected='checkpoint-confirm';checkpointDecisionConfirmation(root,entry);}
  else if(report.canReview)checkpointReviewEditor(root,report);
  const history=checkpointDecisionDisclosure('reviews',`Recorded owner reviews · ${report.reviews.length}`);history.append(
    el('p','Newest first. A new review does not cancel earlier reviews. Withdraw each unwanted review explicitly. Withdrawal blocks a future run grant; it does not stop a run already authorized. Use Pause for that.','muted'));
  for(const row of report.reviews){
    const item=el('section');item.append(el('h3',row.withdrawn?'Withdrawn review':'Recorded review · not running authority'),el('p',`Reviewed ${when(row.at)} · next-intent expiry ${when(row.expiresAt)}`),el('p','Review SHA-256: '+row.checkpointReviewHash,'mono mission-hash'),el('p','Report SHA-256: '+row.reportHash,'mono mission-hash'));
    if(row.withdrawn)item.append(el('p','Withdrawal recorded '+when(row.withdrawnAt)));
    else if(!entry)checkpointWithdrawalEditor(item,report,row);
    history.append(item);
  }
  if(!report.reviews.length)history.append(el('p','No owner checkpoint review has been recorded.'));
  root.append(history);
}
function checkpointReviewEditor(root,report){
  const c=report.candidate,key=workspaceId+':review';
  if(!checkpointDrafts.has(key))checkpointDrafts.set(key,{settings:'',minutes:''});
  const draft=checkpointDrafts.get(key),form=el('form',null,'mission-form');
  form.append(section('Review the next mission',`Saved report v${c.reportVersion} · generation ${c.generation} · ${when(c.reportAt)}`),el('p','Inspect the full saved report and next mission below before confirming. Counts are recorded claims, not phase acceptance.'));
  const spec=c.mission.spec;
  form.append(el('h3',spec.phase.title),el('p',spec.phase.objective),el('p','Required checkpoint: '+spec.phase.checkpoint),
    table(['Next mission limit','Reviewed value'],[['Approval mode',spec.authority.approvalMode],['Parallel tasks',num(spec.authority.maxParallelTasks)],['Total phase tasks',num(spec.authority.maxTasks)],['Phase token limit',num(spec.authority.tokenBudget)],['Included checkpoint reserve',num(spec.authority.checkpointReserveTokens)]]));
  const read=button('Inspect the bound report',()=>loadPhaseCheckpoints({reportHash:c.reportHash,artifactId:c.artifactId}));read.disabled=busy||!connected;form.append(read);
  const detail=checkpointDecisionDisclosure('mission:'+c.missionHash,'Next mission, scope and authority limits');detail.append(el('pre',JSON.stringify(c.mission,null,2)));form.append(detail);
  const label=el('label','Settings for the next intent'),select=el('select');select.required=true;
  const blank=el('option','Choose settings explicitly');blank.value='';select.append(blank);
  for(const [i,option] of c.settings.entries()){const node=el('option',option.label);node.value=String(i);select.append(node);}
  // A changed inspection must not reinterpret an old option index as a different policy.
  const selectedIndex=c.settings.findIndex(s=>JSON.stringify(s.value)===draft.settings);
  select.value=selectedIndex<0?'':String(selectedIndex);
  select.onchange=()=>{draft.settings=select.value===''?'':JSON.stringify(c.settings[Number(select.value)].value);selected='checkpoint-edit';};label.append(select);form.append(label);
  const duration=el('label','Next-intent validity (minutes)'),input=el('input');input.type='number';input.min=1;input.max=1440;input.step=1;input.required=true;input.value=draft.minutes;
  input.oninput=()=>{draft.minutes=input.value;selected='checkpoint-edit';};duration.append(input);form.append(duration,el('p','1–1,440 minutes from preview creation. This limits a future authorization; it is not a schedule or permission to run.','muted'));
  const submit=el('button','Preview checkpoint review');submit.type='submit';submit.disabled=busy||!connected||checkpointDecisionStale(report);form.append(submit);
  form.onsubmit=event=>{event.preventDefault();if(!form.reportValidity()||select.value==='')return;
    previewCheckpointDecision({operation:'review',expectedRevision:report.workspaceRevision,contextHash:report.contextHash,
      reportHash:c.reportHash,artifactId:c.artifactId,missionHash:c.missionHash,reviewReceiptHash:c.reviewReceiptHash,
      settingsPolicy:c.settings[Number(select.value)].value,expiresInSeconds:Number(input.value)*60});
  };root.append(form);
}
function checkpointWithdrawalEditor(root,report,row){
  const key=workspaceId+':'+row.checkpointReviewHash;
  if(!checkpointDrafts.has(key))checkpointDrafts.set(key,{reason:''});
  const draft=checkpointDrafts.get(key),form=el('form',null,'mission-form'),label=el('label','Reason to withdraw this review · no secrets'),input=el('textarea');
  input.rows=2;input.maxLength=2000;input.required=true;input.value=draft.reason;input.oninput=()=>{draft.reason=input.value;selected='checkpoint-edit';};label.append(input);form.append(label);
  const submit=el('button','Preview withdrawal');submit.type='submit';submit.disabled=busy||!connected||checkpointDecisionStale(report);form.append(submit);
  form.onsubmit=event=>{event.preventDefault();if(form.reportValidity())previewCheckpointDecision({operation:'withdraw',expectedRevision:report.workspaceRevision,contextHash:report.contextHash,checkpointReviewHash:row.checkpointReviewHash,reason:input.value});};root.append(form);
}
function checkpointDecisionConfirmation(root,entry){
  const d=entry.proposal.document,r=d.request,review=d.operation==='review',wrap=el('section',null,'mission-review retention-preview');
  wrap.id='checkpoint-decision-confirmation';wrap.tabIndex=-1;
  wrap.append(section(review?'Confirm checkpoint review':'Confirm withdrawal',`Preview expires ${when(d.expiresAt)}. Nothing has changed yet.`),
    table(['Exact scope','To be confirmed'],[['Workspace',d.workspaceId],['Report SHA-256',d.scope.reportHash],['Next mission SHA-256',d.scope.missionHash],...(review?[
      ['Settings',JSON.stringify(r.settingsPolicy)],['Next-intent expiry',when(r.expiresAt)]
    ]:[['Review SHA-256',r.checkpointReviewHash],['Reason',r.reason]])]),
    callout(review?'Review is not Play':'Already-authorized runs are unchanged',review?'This records your review of the exact checkpoint, next mission and settings. It does not authorize a run or clear admission, maintenance, native evidence or phase-acceptance gates.':'This withdraws only the selected review for future run grants. It does not stop or revoke a run already authorized; use safe Pause separately. Other reviews remain unchanged.'));
  const label=el('label'),check=el('input');check.type='checkbox';check.checked=false;label.append(check,el('span',review?'I reviewed this saved report, next mission and settings for the stated expiry.':'I want to withdraw this exact review, without stopping an already-authorized run.'));wrap.append(label);
  const submit=button(entry.uncertain?'Retry the same confirmation':review?'Record checkpoint review':'Withdraw this review',()=>{if(check.checked)confirmCheckpointDecision(entry);},'primary');submit.disabled=true;
  check.onchange=()=>{submit.disabled=busy||!connected||!check.checked;};
  wrap.append(submit,button('Back to decisions',()=>{if(busy)return;checkpointPreviews.delete(workspaceId);selected=null;render();}));
  if(entry.uncertain)wrap.append(el('p','The response was not confirmed. Retry uses the identical signed request; inspect saved decisions before preparing a different one.','muted'));
  const detail=el('details');detail.append(el('summary','Exact signed decision and mission'),el('pre',JSON.stringify(d,null,2)));wrap.append(detail);root.append(wrap);
}
async function inspectCheckpointDecisions(){
  const wid=workspaceId,generation=workspaceGeneration;
  if(!wid||busy||checkpointDecisionPending.has(wid)||!connected)return;
  const token={};checkpointDecisionPending.set(wid,token);checkpointPreviews.delete(wid);selected=null;render();
  try{const report=await api('/api/checkpoint-decisions');if(workspaceId===wid&&workspaceGeneration===generation&&report.workspaceId===wid)checkpointDecisions.set(wid,report);}
  catch(error){if(workspaceId===wid&&workspaceGeneration===generation&&!error.workspaceChanged){checkpointDecisions.delete(wid);showNotice('Decision inspection failed. No authority changed. '+error.message,true);}}
  finally{if(checkpointDecisionPending.get(wid)===token)checkpointDecisionPending.delete(wid);if(workspaceId===wid&&workspaceGeneration===generation&&view==='phaseCheckpoints')render();}
}
async function checkpointDecisionPost(path,payload,done){
  if(busy||!connected)return false;
  const wid=workspaceId,generation=workspaceGeneration;busy=true;updateWorkspaceSelector();if(view==='phaseCheckpoints')render();
  try{const result=await api(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(payload)});
    if(workspaceId===wid&&workspaceGeneration===generation){done(result);return true;}
  }catch(error){if(!error.workspaceChanged&&workspaceId===wid&&workspaceGeneration===generation){
    if(path.endsWith('/confirm')&&checkpointPreviews.has(wid))checkpointPreviews.get(wid).uncertain=true;
    showNotice(error.message+' No automatic retry was sent. Your inputs are retained.',true);
  }}finally{busy=false;updateWorkspaceSelector();if(workspaceId===wid&&workspaceGeneration===generation&&view==='phaseCheckpoints')render();}
  return false;
}
async function previewCheckpointDecision(payload){
  const generation=workspaceGeneration;
  const saved=await checkpointDecisionPost('/api/checkpoint-decisions/preview',payload,proposal=>{
    if(proposal.document.workspaceId!==workspaceId)throw new Error('Preview belongs to another workspace');
    checkpointPreviews.set(workspaceId,{proposal,generation,uncertain:false});selected='checkpoint-confirm';
  });
  if(saved&&generation===workspaceGeneration&&view==='phaseCheckpoints'&&typeof document!=='undefined')document.getElementById('checkpoint-decision-confirmation')?.focus();
  return saved;
}
async function confirmCheckpointDecision(entry){
  if(!checkpointDecisionCurrent(entry)||entry!==checkpointPreviews.get(workspaceId))return false;
  const wid=workspaceId,generation=workspaceGeneration,review=entry.proposal.document.operation==='review';
  const saved=await checkpointDecisionPost('/api/checkpoint-decisions/confirm',{proposal:entry.proposal,confirmed:true},result=>{
    checkpointPreviews.delete(wid);checkpointDecisions.delete(wid);selected=null;
    showNotice(result.replayed?'Original decision receipt recovered; no authority was reapplied.':review?'Checkpoint review recorded. No run was authorized or started.':'Review withdrawn for future run grants. Already-authorized runs are unchanged.');
  });
  if(saved&&workspaceId===wid&&workspaceGeneration===generation){await refresh();await inspectCheckpointDecisions();}
  return saved;
}
