"use strict";
const rereviewWorkers=new Map(),rereviewReports=new Map(),rereviewDrafts=new Map(),rereviewPreviews=new Map(),rereviewPending=new Map(),rereviewDetails=new Map();
function rereviewKey(){return workspaceId+':'+(rereviewWorkers.get(workspaceId)||'');}
function rereviewStale(r){return r.workspaceRevision!==state.meta.revision||!(Date.now()/1000-r.inspectedAt>=0&&Date.now()/1000-r.inspectedAt<=60);}
function rereviewDisclosure(name,label){const key=rereviewKey()+':'+name,d=el('details');d.open=rereviewDetails.get(key)===true;d.append(el('summary',label));d.ontoggle=()=>rereviewDetails.set(key,d.open);return d;}
function rereviewPanel(root){
  if(!state.workspace)return;
  const wrap=el('section',null,'mission-status rereview-panel');wrap.append(el('p','OWNER CONTROL · SETTLED RESULTS','eyebrow'),section('Review an earlier result','Permit a fresh review of unchanged bytes in a later phase. This does not accept the result or restart implementation.'));
  const label=el('label','Task to inspect'),picker=el('select'),blank=el('option','Choose a task');blank.value='';picker.append(blank);
  for(const w of state.workers.filter(w=>w.dispatchAdmission)){const option=el('option',`${w.packetId} · ${w.repository} · ${w.status}`);option.value=w.id;picker.append(option);}
  picker.value=rereviewWorkers.get(workspaceId)||'';picker.disabled=busy;
  picker.onchange=()=>{rereviewPreviews.delete(rereviewKey());rereviewWorkers.set(workspaceId,picker.value);selected=null;render();};label.append(picker);
  const key=rereviewKey(),workerId=rereviewWorkers.get(workspaceId),report=rereviewReports.get(key),pending=rereviewPending.has(workspaceId);
  const inspect=button(pending?'Inspecting saved result…':report?'Inspect result again':'Inspect result & permission',inspectRereview,'primary');inspect.disabled=!workerId||pending||busy||!connected;
  const controls=el('div',null,'mission-form');controls.append(label,inspect);wrap.append(controls);root.append(wrap);
  if(!workerId){wrap.append(el('p','Choose an admission-managed task. No result proofs are inspected when this page opens.','muted'));return;}
  if(!report){wrap.append(el('p','Inspect this task to see retained review versions, permission and current blockers.','muted'));return;}
  wrap.append(el('p',`${rereviewStale(report)?'Earlier inspection · inspect again':'Recorded inspection · not acceptance'} · ${when(report.inspectedAt)}`,'muted'));
  if(report.status==='unavailable'){wrap.append(callout('Result evidence unavailable',report.blocker));return;}
  const task=report.task;
  if(task){wrap.append(table(['Result boundary','Recorded value'],[['Task',task.packetId+' · '+task.repository],['Settlement',when(task.settledAt)],['Last review',report.reviews[0]?.outcome||'Not reviewed'],['Result commit',task.commit||'Not yet recorded · supply the exact commit below']]));
    const scope=rereviewDisclosure('scope','Original scope & acceptance criteria');scope.append(el('pre',JSON.stringify({allowedPaths:task.allowedPaths,acceptance:task.acceptance,baseSHA:task.baseSHA,intentHash:task.intentHash,settlementHash:task.settlementHash},null,2)));wrap.append(scope);
  }
  if(report.authority){const a=report.authority;wrap.append(el('h3',a.status==='revoked'?'Review permission revoked':a.consumed?'Review permission already used':a.expired?'Recorded permission expired':'Recorded review permission'),el('p',`Recorded ${when(a.at)} · expires ${when(a.expiresAt)}. A saved permission is not proof of current eligibility.`,'muted'));}
  if(!report.canAuthorize)wrap.append(callout('New review permission unavailable',report.blocker));
  let entry=rereviewPreviews.get(key);
  if(entry&&entry.generation!==workspaceGeneration){rereviewPreviews.delete(key);entry=null;}
  if(entry){selected='rereview-confirm';rereviewConfirmation(wrap,entry);}
  else {if(report.canAuthorize)rereviewEditor(wrap,report,'authorize');if(report.canRevoke)rereviewEditor(wrap,report,'revoke');}
  const history=rereviewDisclosure('history','Review versions & permission history');history.append(el('p','Newest first. Previous outcomes and original timestamps remain unchanged. Permission is not acceptance.','muted'));
  for(const r of report.reviews){const row=el('section');row.append(el('h3',r.outcome+' · '+when(r.at)),el('p','Commit: '+r.commit,'mono mission-hash'),el('p','Review SHA-256: '+r.reviewHash,'mono mission-hash'),el('p',Object.entries(r.axes).map(([axis,status])=>axis+': '+status).join(' · ')));
    const read=button('Read saved independent review',()=>readRereviewProof(r.reviewArtifactId,row));read.disabled=busy||!connected;row.append(read);history.append(row);}
  if(!report.reviews.length)history.append(el('p','No result review has been recorded.'));
  for(const a of report.permissions)history.append(el('h3',a.status+' · '+when(a.at)),el('p',a.reason),el('p','Permission SHA-256: '+a.authorityHash,'mono mission-hash'));
  wrap.append(history);
}
function rereviewEditor(root,report,operation){
  const key=rereviewKey()+':'+operation;
  if(!rereviewDrafts.has(key))rereviewDrafts.set(key,{commit:'',reason:''});
  const draft=rereviewDrafts.get(key),form=el('form',null,'mission-form');
  form.append(section(operation==='authorize'?'Allow one fresh review':'Revoke further review permission',operation==='authorize'?`Current phase ${report.candidate.phaseId} · generation ${report.candidate.generation}. Permission expires with the run at ${when(report.candidate.expiresAt)}.`:'Revocation blocks new review work. It does not undo a result already recorded or stop native tasks.'));
  if(operation==='authorize'){
    form.append(el('p',report.candidate.goal));
    const scope=rereviewDisclosure('current-scope','Current phase scope');scope.append(el('pre',JSON.stringify(report.candidate.scope,null,2)));form.append(scope);
    const label=el('label','Exact result commit'),input=el('input');input.type='text';input.required=true;input.maxLength=64;input.pattern='[0-9a-f]{40}|[0-9a-f]{64}';input.value=report.task.commit||draft.commit;input.readOnly=!!report.task.commit;
    input.oninput=()=>{draft.commit=input.value;selected='rereview-edit';};label.append(input);form.append(label,el('p',report.task.commit?'The previously reviewed commit is fixed. Changed code needs a separately authorized task.':'Use the full commit hash of the existing settled result. This page does not inspect Git or verify the commit.','muted'));
  }
  const label=el('label','Reason · no secrets'),reason=el('textarea');reason.rows=2;reason.maxLength=2000;reason.required=true;reason.value=draft.reason;reason.oninput=()=>{draft.reason=reason.value;selected='rereview-edit';};label.append(reason);form.append(label);
  const submit=el('button',operation==='authorize'?'Preview review permission':'Preview permission revocation');submit.type='submit';submit.disabled=busy||!connected||rereviewStale(report);form.append(submit);
  form.onsubmit=event=>{event.preventDefault();if(!form.reportValidity())return;previewRereview({operation,workerId:report.workerId,expectedRevision:report.workspaceRevision,contextHash:report.contextHash,reason:draft.reason,
    ...(operation==='authorize'?{commit:report.task.commit||draft.commit}:{authorityHash:report.authority.authorityHash})});};root.append(form);
}
function rereviewConfirmation(root,entry){
  const doc=entry.proposal.document,r=doc.request,approve=doc.operation==='authorize',wrap=el('section',null,'mission-review retention-preview');wrap.id='rereview-confirmation';wrap.tabIndex=-1;
  wrap.append(section(approve?'Confirm this review permission':'Confirm permission revocation',`Preview expires ${when(doc.expiresAt)}. Nothing has changed yet.`),table(['Exact scope','To be confirmed'],[['Project',doc.workspaceId],['Task',doc.scope.task?.packetId||r.workerId],...(approve?[
    ['Commit',r.commit],['Current phase',doc.scope.run.phaseId],['Current run generation',doc.scope.run.generation],['Previous review',r.previousReviewHash||'None'],['Permission expires',when(doc.scope.run.expiresAt)]
  ]:[['Permission SHA-256',r.authorityHash]]),['Reason',r.reason]]),callout('Review permission is not acceptance',approve?'The brain must still collect fresh evidence and independently review the unchanged result. No implementation task is opened or resumed; budget and prior outcomes are unchanged.':'New review work is blocked. Any review already committed remains valid; revocation cannot undo acceptance. Use Pause separately to stop development safely.'));
  const label=el('label'),check=el('input');check.type='checkbox';check.checked=false;label.append(check,el('span',approve?'I authorize one review of this exact settled result in the stated phase.':'I revoke this exact review permission without undoing a recorded result.'));wrap.append(label);
  const submit=button(entry.uncertain?'Retry the same confirmation':approve?'Authorize this review':'Revoke review permission',()=>{if(check.checked)confirmRereview(entry);},'primary');submit.disabled=true;
  check.onchange=()=>{submit.disabled=busy||!connected||!check.checked;};wrap.append(submit,button('Back to result',()=>{if(busy)return;rereviewPreviews.delete(rereviewKey());selected=null;render();}));
  if(entry.uncertain)wrap.append(el('p','Response not confirmed. Retry uses the identical signed request; inspect saved permission before preparing another.','muted'));
  const detail=el('details');detail.append(el('summary','Exact signed scope'),el('pre',JSON.stringify(doc,null,2)));wrap.append(detail);root.append(wrap);
}
async function inspectRereview(){
  const wid=workspaceId,generation=workspaceGeneration,key=rereviewKey(),workerId=rereviewWorkers.get(wid);
  if(!wid||!workerId||busy||rereviewPending.has(wid)||!connected)return;
  const token={};rereviewPending.set(wid,token);rereviewPreviews.delete(key);selected=null;render();
  try{const report=await api('/api/result-review-controls?workerId='+encodeURIComponent(workerId));
    if(workspaceId===wid&&workspaceGeneration===generation&&rereviewKey()===key&&report.workspaceId===wid&&report.workerId===workerId)rereviewReports.set(key,report);
  }catch(error){if(workspaceId===wid&&workspaceGeneration===generation&&rereviewKey()===key&&!error.workspaceChanged){rereviewReports.delete(key);showNotice('Result inspection failed. No permission changed. '+error.message,true);}}
  finally{if(rereviewPending.get(wid)===token)rereviewPending.delete(wid);if(workspaceId===wid&&workspaceGeneration===generation&&view==='workers')render();}
}
async function rereviewPost(path,payload,done){
  if(busy||!connected)return false;
  const wid=workspaceId,generation=workspaceGeneration,key=rereviewKey();busy=true;updateWorkspaceSelector();if(view==='workers')render();
  try{const result=await api(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(payload)});
    if(workspaceId===wid&&workspaceGeneration===generation&&rereviewKey()===key){done(result);return true;}
  }catch(error){if(!error.workspaceChanged&&workspaceId===wid&&workspaceGeneration===generation&&rereviewKey()===key){
    if(path.endsWith('/confirm')&&rereviewPreviews.has(key))rereviewPreviews.get(key).uncertain=true;
    showNotice(error.message+' No automatic retry was sent. Your inputs are retained.',true);
  }}finally{busy=false;updateWorkspaceSelector();if(workspaceId===wid&&workspaceGeneration===generation&&view==='workers')render();}
  return false;
}
async function previewRereview(payload){
  const generation=workspaceGeneration,key=rereviewKey();
  const saved=await rereviewPost('/api/result-review-controls/preview',payload,proposal=>{
    if(proposal.document.workspaceId!==workspaceId||proposal.document.request.workerId!==rereviewWorkers.get(workspaceId))throw new Error('Preview belongs to another project or task');
    rereviewPreviews.set(key,{proposal,generation,uncertain:false});selected='rereview-confirm';
  });
  if(saved&&generation===workspaceGeneration&&view==='workers'&&typeof document!=='undefined')document.getElementById('rereview-confirmation')?.focus();return saved;
}
async function confirmRereview(entry){
  const wid=workspaceId,generation=workspaceGeneration,key=rereviewKey();
  if(entry.generation!==generation||entry!==rereviewPreviews.get(key))return false;
  const saved=await rereviewPost('/api/result-review-controls/confirm',{proposal:entry.proposal,confirmed:true},result=>{
    rereviewPreviews.delete(key);rereviewReports.delete(key);selected=null;
    showNotice(result.replayed?'Original receipt recovered; permission was not reapplied.':entry.proposal.document.operation==='authorize'?'Review permission recorded. The brain must still review the result; no task was resumed.':'Review permission revoked. Recorded outcomes are unchanged.');
  });
  if(saved&&workspaceId===wid&&workspaceGeneration===generation&&rereviewKey()===key){await refresh();await inspectRereview();}return saved;
}
async function readRereviewProof(id,root){
  const wid=workspaceId,generation=workspaceGeneration,key=rereviewKey();
  try{const result=await api('/api/artifacts/'+encodeURIComponent(id));
    if(workspaceId===wid&&workspaceGeneration===generation&&rereviewKey()===key&&view==='workers'){
      const pre=el('pre',result.text||'No readable text available');pre.tabIndex=-1;root.append(pre);pre.focus?.();selected='rereview-proof';
    }
  }catch(error){if(!error.workspaceChanged&&workspaceId===wid&&workspaceGeneration===generation&&rereviewKey()===key)showNotice('Saved proof could not be read: '+error.message,true);}
}
