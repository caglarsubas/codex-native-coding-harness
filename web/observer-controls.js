"use strict";
const observerReports=new Map(),observerDrafts=new Map(),observerPreviews=new Map(),observerPending=new Map(),observerDetails=new Map();
function observerStale(r){return r.workspaceRevision!==state.meta.revision||!(Date.now()/1000-r.inspectedAt>=0&&Date.now()/1000-r.inspectedAt<=60);}
function observerReportStale(p){return p.stale||!(Date.now()/1000-p.startedAt>=0&&Date.now()/1000-p.startedAt<=60);}
function observerDisclosure(key,label){const id=workspaceId+':'+key,d=el('details');d.open=observerDetails.get(id)===true;d.append(el('summary',label));d.ontoggle=()=>observerDetails.set(id,d.open);return d;}
function observerEndpoint(root,p){root.append(el('p','Executable: '+p.executable,'mission-hash'),el('p','Executable SHA-256: '+p.sha256,'mono mission-hash'),el('p','Existing private socket: '+p.socket,'mission-hash'),el('p','Expected server identity SHA-256: '+p.serverIdentityHash,'mono mission-hash'));}
function observerControlPanel(root){
  if(!state.workspace)return;
  const wrap=el('section',null,'mission-status observer-panel'),r=observerReports.get(workspaceId),pending=observerPending.has(workspaceId);
  wrap.append(el('p','OWNER SETUP · READ-ONLY NATIVE OBSERVER','eyebrow'),section('Observation endpoint','Review which existing local endpoint the brain may use for bounded metadata reads. This is not a model provider or the dashboard assistant’s inference endpoint.'));
  const inspect=button(pending?'Inspecting saved observer state…':r?'Inspect observer setup again':'Inspect observer setup',inspectObserverControls,'primary');inspect.disabled=busy||pending||!connected;wrap.append(inspect);root.append(wrap);
  if(!r){wrap.append(el('p','No observer inspection in this tab. This page never starts a server, connects to a socket or collects native observations.','muted'));return;}
  wrap.append(el('p',`${observerStale(r)?'Earlier inspection · inspect again':'Recorded setup · not a connection test'} · ${when(r.inspectedAt)}`,'muted'));
  const gaps=el('ul');for(const message of Object.values(r.gaps))gaps.append(el('li',message));wrap.append(section('What this observer cannot prove','These gaps remain even when metadata reads succeed.'),gaps);
  if(r.status==='unavailable'){wrap.append(callout('Endpoint history unavailable',r.reviewBlocker));return;}
  if(r.endpoint){wrap.append(section(r.endpoint.revoked?'Endpoint access revoked':'Reviewed endpoint · not connected here'),el('p',`Version ${r.endpoint.version} · ${when(r.endpoint.at)}`));const exact=observerDisclosure('endpoint','Read reviewed endpoint fingerprints');observerEndpoint(exact,r.endpoint.endpoint);wrap.append(exact);}
  else wrap.append(el('p','No observation endpoint has been reviewed. Nothing is discovered or selected automatically.','muted'));
  if(!r.canReview)wrap.append(callout('Endpoint review unavailable',r.reviewBlocker));
  let entry=observerPreviews.get(workspaceId);if(entry&&entry.generation!==workspaceGeneration){observerPreviews.delete(workspaceId);entry=null;}
  if(entry){selected='observer-confirm';observerConfirmation(wrap,entry);}
  else{
    if(r.canReview){if(observerDrafts.get(workspaceId)?.editing)observerEditor(wrap,r);else wrap.append(button('Configure observation endpoint',()=>{if(busy)return;if(!observerDrafts.has(workspaceId))observerDrafts.set(workspaceId,{allocationId:'',executable:'',socket:'',serverIdentityHash:''});observerDrafts.get(workspaceId).editing=true;selected='observer-edit';render();}));}
    if(r.canRevoke){const revoke=button('Preview endpoint revocation',()=>previewObserverControls({operation:'revoke',expectedRevision:r.workspaceRevision,contextHash:r.contextHash,endpointHash:r.endpoint.endpointHash}));revoke.disabled=busy||!connected||observerStale(r);wrap.append(revoke,el('p','Revocation prevents later collection. It cannot cancel a read already in flight or stop native work.','muted'));}
  }
  const history=observerDisclosure('history',`Endpoint versions · ${r.history.length+r.omittedHistory}`);history.append(el('p',`Newest first, original review times. ${r.omittedHistory} older versions omitted from this bounded view.`,'muted'));
  for(const p of r.history){const version=el('details');version.append(el('summary',`Version ${p.version} · ${when(p.at)}`),el('p','Allocation: '+p.allocationId,'mission-hash'),el('p','Review SHA-256: '+p.endpointHash,'mono mission-hash'));observerEndpoint(version,p.endpoint);history.append(version);}wrap.append(history);
  wrap.append(section('Saved collection reports','Historical metadata only, not current activity, complete evidence or permission to run. No report is collected by opening this page.'));
  if(r.reportsStatus==='unavailable')wrap.append(callout('Saved reports unavailable','Retained evidence is damaged or exceeds its inspection bound. Ask the operator to reconcile it; there is no older healthy fallback.'));
  else if(!r.reports.length)wrap.append(el('p','No saved collection report. After separate setup, only the designated brain can explicitly collect through its existing command.','muted'));
  for(const p of r.reports){const detail=observerDisclosure('report:'+p.reportHash,`Report v${p.version} · ${when(p.finishedAt)} · ${p.collectionUnavailable?'collection unavailable':observerReportStale(p)?'historical / stale':'recent metadata only'}`);detail.append(el('p','Allocation: '+p.allocationId,'mission-hash'),el('p',`Recorded samples: ${p.sampleCount} · running ${p.activityCounts.running} · idle ${p.activityCounts.idle} · unknown ${p.activityCounts.unknown}`),el('p',`Tracked terminals: ${p.trackedTerminalCount}. A zero count is not OS cleanup proof.`),el('p',`Endpoint review ${p.endpointCurrent?'matches':'changed or revoked'} · effect context not revalidated · complete evidence unavailable`),el('p','Report SHA-256: '+p.reportHash,'mono mission-hash'));wrap.append(detail);}
  if(r.omittedReports)wrap.append(el('p',`${r.omittedReports} older reports omitted from this bounded view.`,'muted'));
}
function observerEditor(root,r){
  const d=observerDrafts.get(workspaceId),form=el('form',null,'mission-form');
  form.append(section('Choose an existing endpoint','Use only a trusted installed executable and existing private local socket. Preview fingerprints files but never executes or connects. No endpoint or identity is inferred.'));
  const label=el('label','Existing phase allocation'),select=el('select');select.required=true;const blank=el('option','Choose explicitly');blank.value='';select.append(blank);
  for(const a of r.allocations){const option=el('option',a.allocationId+' · '+a.repositories.join(', '));option.value=a.allocationId;select.append(option);}select.value=r.allocations.some(a=>a.allocationId===d.allocationId)?d.allocationId:'';select.onchange=()=>{d.allocationId=select.value;selected='observer-edit';};label.append(select);form.append(label);
  for(const [key,title] of [['executable','Canonical installed executable path'],['socket','Existing private socket path'],['serverIdentityHash','Expected server identity SHA-256']]){const label=el('label',title),input=el('input');input.type='text';input.required=true;input.value=d[key];input.maxLength=key==='serverIdentityHash'?64:4096;if(key==='serverIdentityHash')input.pattern='[a-f0-9]{64}';input.autocomplete='off';input.spellcheck=false;input.oninput=()=>{d[key]=input.value;selected='observer-edit';};label.append(input);form.append(label);}
  form.append(el('p','The identity hash must come from a separately verified initialization identity, not a guess. Keep raw identity details private. No credentials, URLs or command arguments belong in these fields.','muted'));
  const submit=el('button','Preview endpoint access');submit.type='submit';submit.disabled=busy||!connected||observerStale(r);form.append(submit,button('Close endpoint editor · keep draft',()=>{if(!busy){d.editing=false;selected=null;render();}}));
  form.onsubmit=e=>{e.preventDefault();if(form.reportValidity()&&!submit.disabled)previewObserverControls({operation:'review',expectedRevision:r.workspaceRevision,contextHash:r.contextHash,...Object.fromEntries(['allocationId','executable','socket','serverIdentityHash'].map(k=>[k,d[k]]))});};root.append(form);
}
function observerConfirmation(root,entry){
  const p=entry.proposal.document,review=p.operation==='review',wrap=el('section',null,'mission-review retention-preview');wrap.id='observer-confirmation';wrap.tabIndex=-1;
  wrap.append(section(review?'Confirm metadata-read access':'Confirm endpoint revocation',`Project ${p.workspaceId} · expires ${when(p.expiresAt)}. Nothing has been changed yet.`));
  if(review){wrap.append(el('p','Allocation: '+p.allocation.allocationId,'mission-hash'));observerEndpoint(wrap,p.request.endpoint);}
  else wrap.append(el('p','Exact endpoint review SHA-256: '+p.request.endpointHash,'mono mission-hash'));
  wrap.append(callout('No connection or execution from this confirmation',review?'This grants the brain only the existing bounded metadata-read path to the exact endpoint. It does not start a server, collect now, run tasks, change usage or enable Play.':'This blocks later collection but cannot cancel a read already in flight. It does not stop native tasks or delete saved evidence.'));
  const label=el('label'),check=el('input');check.type='checkbox';check.checked=false;label.append(check,el('span',review?'I verified these exact endpoint fingerprints and authorize only the bounded metadata-read path.':'I revoke this exact endpoint review.'));wrap.append(label);
  const submit=button(entry.uncertain?'Retry the same endpoint confirmation':review?'Record endpoint review':'Revoke endpoint access',()=>{if(check.checked)confirmObserverControls(entry);},'primary');submit.disabled=true;check.onchange=()=>submit.disabled=busy||!connected||!check.checked;wrap.append(submit,button('Back to observer setup',()=>{if(!busy){observerPreviews.delete(workspaceId);selected=null;render();}}));
  if(entry.uncertain)wrap.append(el('p','Response not confirmed. Manual retry uses the identical signed request and cannot restore revoked access.','muted'));root.append(wrap);
}
async function inspectObserverControls(){
  const wid=workspaceId,generation=workspaceGeneration;if(!wid||busy||!connected||observerPending.has(wid))return;const token={};observerPending.set(wid,token);observerPreviews.delete(wid);selected=null;render();
  try{const r=await api('/api/native-observer-controls');if(workspaceId===wid&&workspaceGeneration===generation&&r.workspaceId===wid)observerReports.set(wid,r);}
  catch(error){if(!error.workspaceChanged&&workspaceId===wid&&workspaceGeneration===generation){observerReports.delete(wid);showNotice('Observer inspection failed. No connection or change was made. '+error.message,true);}}
  finally{if(observerPending.get(wid)===token)observerPending.delete(wid);if(workspaceId===wid&&workspaceGeneration===generation&&view==='runReadiness')render();}
}
async function observerPost(path,body,done){
  if(busy||!connected)return false;const wid=workspaceId,generation=workspaceGeneration;busy=true;updateWorkspaceSelector();if(view==='runReadiness')render();
  try{const result=await api(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});if(workspaceId===wid&&workspaceGeneration===generation){done(result);return true;}}
  catch(error){if(!error.workspaceChanged&&workspaceId===wid&&workspaceGeneration===generation){if(path.endsWith('/confirm')&&observerPreviews.has(wid))observerPreviews.get(wid).uncertain=true;showNotice(error.message+' No automatic retry was sent. Your draft is retained.',true);}}
  finally{busy=false;updateWorkspaceSelector();if(workspaceId===wid&&workspaceGeneration===generation&&view==='runReadiness')render();}return false;
}
async function previewObserverControls(body){const wid=workspaceId,generation=workspaceGeneration;const ok=await observerPost('/api/native-observer-controls/preview',body,proposal=>{if(proposal.document.workspaceId!==wid)throw new Error('Foreign observer preview');observerPreviews.set(wid,{proposal,generation,uncertain:false});selected='observer-confirm';});if(ok&&workspaceGeneration===generation&&view==='runReadiness'&&typeof document!=='undefined')document.getElementById('observer-confirmation')?.focus();return ok;}
async function confirmObserverControls(entry){
  const wid=workspaceId,generation=workspaceGeneration;if(entry.generation!==generation||entry!==observerPreviews.get(wid))return false;
  const ok=await observerPost('/api/native-observer-controls/confirm',{proposal:entry.proposal,confirmed:true},result=>{observerPreviews.delete(wid);observerReports.delete(wid);selected=null;if(observerDrafts.has(wid))observerDrafts.get(wid).editing=false;showNotice(result.replayed?'Original endpoint receipt recovered; no access was reapplied.':'Endpoint '+(entry.proposal.document.operation==='review'?'review recorded':'access revoked')+'. No native connection or task was started.');});
  if(ok&&workspaceId===wid&&workspaceGeneration===generation){await refresh();await inspectObserverControls();}return ok;
}
