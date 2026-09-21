"use strict";
Object.assign(titles,{retention:['Task retention','Decide when the brain may request archival. Preservation and native safety checks still come first.']});
const retentionReports=new Map(),retentionDrafts=new Map(),retentionPreviews=new Map(),retentionPending=new Map();
function retentionCurrent(entry){return entry&&entry.generation===workspaceGeneration;}
function retentionStale(report){return report.workspaceRevision!==state.meta.revision||!(Date.now()/1000-report.inspectedAt>=0&&Date.now()/1000-report.inspectedAt<=60);}
function retentionView(root){
  if(!state.workspace){root.append(empty('Select a registered workspace','Retention belongs to one workspace and one exact run.'));return;}
  const report=retentionReports.get(workspaceId),pending=retentionPending.has(workspaceId);
  const intro=el('section',null,'mission-status');intro.append(el('p',state.workspace.name+' · OWNER CONTROL','eyebrow'),el('h2','Keep completed work recoverable'),
    el('p','Delegation is off unless you review a policy for an already-authorized run. This page does not archive a task, enable Play or release a checkpoint.'));
  const inspect=button(pending?'Inspecting saved policy…':report?'Inspect policy again':'Inspect retention policy',inspectRetention,'primary');inspect.disabled=pending||busy||!connected;intro.append(inspect);root.append(intro);
  if(!report){root.append(empty('No policy inspection in this tab','Inspect saved limits, attempts and review availability. Opening this page does not inspect proofs or native activity.'));return;}
  root.append(el('p',`${retentionStale(report)?'Earlier inspection · inspect again':'Recorded inspection · not archive clearance'} · ${when(report.inspectedAt)}`,'muted'));
  if(report.status==='unavailable'){root.append(callout('Policy evidence unavailable','Retained policy or run evidence is missing, changed or exceeds inspection limits. The brain/operator must reconcile it; no fallback authority is offered.'));return;}
  const p=report.policy;
  if(p){
    root.append(section(p.revoked?'Delegation revoked':p.matchesCurrentRun?'Reviewed policy for this run':'Earlier-run policy · not current authority',`Policy v${p.version} · recorded ${when(p.at)}`),
      table(['Policy boundary','Recorded value'],[['Run',`${p.phaseId} · generation ${p.generation}`],['Archive request limit',num(p.maxArchives)],['Requests already recorded',num(p.recordedAttempts)],['Minimum retention',`${num(p.minimumRetentionSeconds)} seconds after acceptance`],['Run expiry',when(p.expiresAt)]]));
  }else root.append(section('No delegated retention','A phase task-approval grant alone does not permit archival.'));
  root.append(el('p','Requests count even if cancelled, rejected or uncertain. Policy revisions do not reset the run’s count. Only accepted, preserved local root tasks can proceed; descendants and incomplete preservation block archival.','checkpoint'));
  if(report.currentRun)root.append(el('p',`Current authorized intent: ${report.currentRun.phaseId} · generation ${report.currentRun.generation}. Expires ${when(report.currentRun.expiresAt)}. This is not running-state evidence.`,'muted'));
  if(!report.canReview)root.append(callout('Review unavailable',report.reviewBlocker));
  let entry=retentionPreviews.get(workspaceId);
  if(entry&&!retentionCurrent(entry)){retentionPreviews.delete(workspaceId);entry=null;}
  if(entry){selected='retention-confirm';retentionConfirmation(root,entry);}
  else {
    if(report.canReview)retentionEditor(root,report,'review');
    if(report.canRevoke)retentionEditor(root,report,'revoke');
  }
  const history=el('details');history.append(el('summary','Policy versions & exact bindings'));
  for(const item of report.history){
    const row=el('section');row.append(el('h3',`Version ${item.version} · ${when(item.at)}`),el('p',`${item.phaseId} · run generation ${item.generation} · limit ${num(item.maxArchives)} requests · minimum ${num(item.minimumRetentionSeconds)} seconds`),
      el('p','Policy SHA-256: '+item.policyHash,'mono mission-hash'),el('p','Run SHA-256: '+item.runHash,'mono mission-hash'));history.append(row);
  }
  if(!report.history.length)history.append(el('p','No policy has been recorded.'));
  if(report.omittedHistory)history.append(el('p',`${num(report.omittedHistory)} earlier versions omitted from this bounded view. The retained ledger remains the record.`,'muted'));
  root.append(history);
}
function retentionEditor(root,report,operation){
  const key=workspaceId+':'+operation;
  if(!retentionDrafts.has(key))retentionDrafts.set(key,{maxArchives:'',minimumRetentionSeconds:'',reason:''});
  const draft=retentionDrafts.get(key),form=el('form',null,'mission-form retention-form');
  form.append(section(operation==='review'?'Review delegation for this run':'Withdraw further delegation',operation==='review'?'Choose explicit limits. Nothing is selected or approved automatically.':'Revocation blocks new sends. It cannot cancel a native call whose send check was already consumed.'));
  function field(label,key,type,max){
    const wrap=el('label',label),input=el(type==='number'?'input':'textarea');
    if(type==='number'){input.type='number';input.min=key==='maxArchives'?1:0;input.max=max;input.step=1;}else{input.rows=2;input.maxLength=max;}
    input.required=true;input.value=draft[key];input.oninput=()=>{draft[key]=input.value;selected='retention-edit';};wrap.append(input);form.append(wrap);
  }
  if(operation==='review'){
    field('Archive request limit for this run','maxArchives','number',report.currentRun.maxArchives);
    field('Keep accepted tasks for at least (seconds)','minimumRetentionSeconds','number',86400);
    form.append(el('p',`Limit: 1–${report.currentRun.maxArchives} requests. Retention: 0–86,400 seconds; 3,600 seconds is one hour. Existing attempts remain charged.`,'muted'));
  }else field('Reason for revocation · no secrets','reason','text',2000);
  const submit=el('button',operation==='review'?'Preview retention policy':'Preview revocation');submit.type='submit';submit.disabled=busy||!connected||retentionStale(report);form.append(submit);
  form.onsubmit=event=>{event.preventDefault();if(!form.reportValidity())return;
    const payload={operation,expectedRevision:report.workspaceRevision,contextHash:report.contextHash,...(operation==='review'?{
      runHash:report.currentRun.runHash,expectedPolicyHash:report.policy?.policyHash||null,maxArchives:Number(draft.maxArchives),minimumRetentionSeconds:Number(draft.minimumRetentionSeconds)
    }:{policyHash:report.policy.policyHash,reason:draft.reason})};previewRetention(payload);
  };root.append(form);
}
function retentionConfirmation(root,entry){
  const doc=entry.proposal.document,review=doc.operation==='review',r=doc.request,wrap=el('section',null,'mission-review retention-preview');
  wrap.append(section(review?'Confirm this retention policy':'Confirm revocation',`Preview expires ${when(doc.expiresAt)}. Nothing has been changed by preparing it.`),
    table(['Exact scope','To be confirmed'],[['Workspace',doc.workspaceId],['Run',`${doc.run.phaseId} · generation ${doc.run.generation}`],...(review?[
      ['Archive request limit',num(r.maxArchives)],['Minimum retention',`${num(r.minimumRetentionSeconds)} seconds after acceptance`]
    ]:[['Policy',r.policyHash],['Reason',r.reason]])]));
  if(review)wrap.append(callout('Archival can remove a managed worktree','You are delegating archive requests for accepted, preserved root tasks in this exact run. Git bundles alone do not preserve untracked files, external payloads or native transcripts. The brain must independently verify preservation and fresh inactivity before a one-shot archive check.'));
  else wrap.append(callout('In-flight calls are not undone','Revocation stops new delegated requests and unsent archive checks. It does not interrupt tasks or reverse archival already sent.'));
  const checks=[];
  function acknowledgment(text){const label=el('label'),check=el('input');check.type='checkbox';check.checked=false;label.append(check,el('span',text));wrap.append(label);checks.push(check);return check;}
  acknowledgment(review?'I reviewed this exact run and these limits; future requests may be approved within them.':'I want to revoke this exact policy. Other workspace authority is unchanged.');
  if(review)acknowledgment('I explicitly acknowledge that native archival can clean up the managed worktree after preservation checks.');
  const submit=button(entry.uncertain?'Retry the same confirmation':review?'Approve retention for this run':'Revoke delegation',()=>{
    if(checks.every(c=>c.checked))confirmRetention(entry,{confirmed:true,cleanupAcknowledged:review});
  },'primary');submit.disabled=true;
  checks.forEach(check=>check.onchange=()=>{submit.disabled=busy||!connected||!checks.every(c=>c.checked);});
  wrap.append(submit,button('Back to policy settings',()=>{if(busy)return;retentionPreviews.delete(workspaceId);selected=null;render();}));
  if(entry.uncertain)wrap.append(el('p','The response was not confirmed. Retrying uses the same signed request; inspect the saved policy before preparing anything different.','muted'));
  const detail=el('details');detail.append(el('summary','Exact signed scope'),el('pre',JSON.stringify(doc,null,2)));wrap.append(detail);root.append(wrap);
}
async function inspectRetention(){
  const wid=workspaceId,generation=workspaceGeneration;
  if(!wid||busy||retentionPending.has(wid)||!connected)return;
  const token={};retentionPending.set(wid,token);retentionPreviews.delete(wid);selected=null;render();
  try{const report=await api('/api/retention');if(workspaceId===wid&&workspaceGeneration===generation&&report.workspaceId===wid)retentionReports.set(wid,report);}
  catch(error){if(workspaceId===wid&&workspaceGeneration===generation&&!error.workspaceChanged){retentionReports.delete(wid);showNotice('Retention inspection failed. No policy changed. '+error.message,true);}}
  finally{if(retentionPending.get(wid)===token)retentionPending.delete(wid);if(workspaceId===wid&&workspaceGeneration===generation&&view==='retention')render();}
}
async function retentionPost(path,payload,done){
  if(busy||!connected)return;
  const wid=workspaceId,generation=workspaceGeneration;busy=true;updateWorkspaceSelector();if(view==='retention')render();
  try{
    const result=await api(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(payload)});
    if(workspaceId===wid&&workspaceGeneration===generation){done(result);return true;}
  }catch(error){if(!error.workspaceChanged&&workspaceId===wid&&workspaceGeneration===generation){
    if(path.endsWith('/confirm')&&retentionPreviews.has(wid))retentionPreviews.get(wid).uncertain=true;
    showNotice(error.message+' No automatic retry was sent. Your inputs are retained.',true);
  }}finally{busy=false;updateWorkspaceSelector();if(workspaceId===wid&&workspaceGeneration===generation&&view==='retention')render();}
  return false;
}
async function previewRetention(payload){
  const generation=workspaceGeneration;
  return retentionPost('/api/retention/preview',payload,proposal=>{
    if(proposal.document.workspaceId!==workspaceId)throw new Error('Preview belongs to another workspace');
    retentionPreviews.set(workspaceId,{proposal,generation,uncertain:false});selected='retention-confirm';
  });
}
async function confirmRetention(entry,confirmation){
  if(!retentionCurrent(entry)||entry!==retentionPreviews.get(workspaceId))return false;
  const review=entry.proposal.document.operation==='review',wid=workspaceId,generation=workspaceGeneration;
  const saved=await retentionPost('/api/retention/confirm',{proposal:entry.proposal,...confirmation},result=>{
    retentionPreviews.delete(wid);retentionReports.delete(wid);selected=null;
    showNotice(result.replayed?'The original confirmation receipt was recovered; no policy was reapplied.':review?'Retention delegation reviewed. No task was archived; Play and dispatch are unchanged.':'Delegation revoked. New sends are blocked; in-flight native calls are not undone.');
  });
  if(saved&&workspaceId===wid&&workspaceGeneration===generation){await refresh();await inspectRetention();}
  return saved;
}
