"use strict";
const modelReports=new Map(),modelDrafts=new Map(),modelPreviews=new Map(),modelPending=new Map(),modelDetails=new Map();
const modelComplexities=['routine','standard','complex','critical'];
function modelStale(r){return r.workspaceRevision!==state.meta.revision||!(Date.now()/1000-r.inspectedAt>=0&&Date.now()/1000-r.inspectedAt<=60);}
function modelDisclosure(key,label){const id=workspaceId+':'+key,d=el('details');d.open=modelDetails.get(id)===true;d.append(el('summary',label));d.ontoggle=()=>modelDetails.set(id,d.open);return d;}
function modelProfileTable(profiles){return table(['Profile / model','Effort / owner quality','Minimum work tokens'],profiles.map(p=>[p.id+' · '+p.settings.model,p.settings.effort+' · tier '+p.quality,num(p.minimumWorkTokens)]));}
function modelControlPanel(root){
  if(!state.workspace)return;
  const wrap=el('section',null,'mission-status model-policy-panel'),r=modelReports.get(workspaceId),pending=modelPending.has(workspaceId);
  wrap.append(el('p','OWNER CONFIGURATION · NATIVE TASK SETTINGS','eyebrow'),section('Model & effort policy','Choose which profiles the brain may select under a separately authorized run. This is not the dashboard assistant’s inference model.'));
  const inspect=button(pending?'Inspecting saved policy…':r?'Inspect model policy again':'Inspect model policy',inspectModelControls,'primary');inspect.disabled=busy||pending||!connected;wrap.append(inspect);root.append(wrap);
  if(!r){wrap.append(el('p','No policy inspection in this tab. Inspection reads saved evidence only; it never queries a provider or changes task settings.','muted'));return;}
  wrap.append(el('p',`${modelStale(r)?'Earlier inspection · inspect again':'Recorded inspection · not applied settings'} · ${when(r.inspectedAt)}`,'muted'));
  if(r.status==='unavailable'){wrap.append(callout('Policy evidence unavailable',r.reviewBlocker));return;}
  wrap.append(el('p','Catalog: '+r.capabilityStatus.replaceAll('_',' ')+(r.capability?' · observed '+when(r.capability.observedAt):''),'muted'));
  if(r.capability){const cap=modelDisclosure('catalog','Recorded models & supported efforts');cap.append(el('p','Designated-brain observations, not independent host attestation. Speed and Ultra remain unavailable for this adapter.','muted'),table(['Model','Recorded efforts'],r.capability.catalog.models.map(m=>[m.model,m.efforts.join(', ')])));wrap.append(cap);}
  if(r.policy){wrap.append(section(r.policy.revoked?'Recorded policy revoked':'Recorded policy · not activation'),modelProfileTable(r.policy.profiles),el('p','Maximum per-task escalations: '+r.policy.maxEscalations));if(r.policyIssue)wrap.append(el('p',r.policyIssue,'muted'));}
  else wrap.append(el('p','No model policy has been reviewed. Native defaults remain a separate run choice; this page does not change them.','muted'));
  if(!r.canReview)wrap.append(callout('Policy review unavailable',r.reviewBlocker));
  let entry=modelPreviews.get(workspaceId);if(entry&&entry.generation!==workspaceGeneration){modelPreviews.delete(workspaceId);entry=null;}
  if(entry){selected='model-confirm';modelConfirmation(wrap,entry);}
  else{
    if(r.canReview){if(modelDrafts.get(workspaceId)?.editing)modelEditor(wrap,r);else wrap.append(button('Configure profiles',()=>openModelDraft(r)));}
    if(r.canRevoke)modelRevokeEditor(wrap,r);
  }
  const history=modelDisclosure('history',`Policy versions · ${r.history.length}`);history.append(el('p','Newest first, original times. Older policies are superseded, not renewed by viewing them.','muted'));
  for(const p of r.history){history.append(el('h3',when(p.at)),el('p','Policy SHA-256: '+p.policyHash,'mono mission-hash'),modelProfileTable(p.profiles),el('p','Quality floors: '+modelComplexities.map(c=>c+' '+p.qualityFloors[c]).join(' · ')),el('p','Maximum escalations: '+p.maxEscalations));}
  wrap.append(history);
}
function openModelDraft(r){
  if(busy)return;
  if(!modelDrafts.get(workspaceId)?.profiles)modelDrafts.set(workspaceId,{missionHash:r.candidate.missionHash,profiles:[],qualityFloors:Object.fromEntries(modelComplexities.map(c=>[c,''])),maxEscalations:'',reason:modelDrafts.get(workspaceId)?.reason||''});
  modelDrafts.get(workspaceId).editing=true;selected='model-edit';render();
}
function modelEditor(root,r){
  const draft=modelDrafts.get(workspaceId),form=el('form',null,'mission-form model-policy-form');
  form.append(section('Choose approved profiles',`Reviewed phase ${r.candidate.phaseId}. No profile, model, quality tier or token allowance is selected for you.`),el('p','Quality tiers 1–4 are your relative judgments, not benchmarks. Work-token floors are minimum estimates, not spending caps. Budget shortage stops work; it cannot authorize a lower quality tier.','muted'));
  if(draft.missionHash!==r.candidate.missionHash){form.append(callout('Draft belongs to an earlier mission','Your choices are retained. Read the current mission and explicitly rebind before previewing.'),button('Use draft for this mission',()=>{if(!busy){draft.missionHash=r.candidate.missionHash;render();}}));}
  if(r.policy)form.append(button('Copy recorded policy into draft',()=>{if(busy)return;Object.assign(draft,JSON.parse(JSON.stringify({profiles:r.policy.profiles,qualityFloors:r.policy.qualityFloors,maxEscalations:r.policy.maxEscalations})));render();}));
  function field(parent,label,value,set,options={}){
    const wrap=el('label',label),input=el('input');input.type=options.type||'text';input.required=true;input.value=value;
    if(input.type==='number'){input.min=options.min??1;input.max=options.max??1000000000;input.step=1;}else{input.maxLength=100;input.pattern='[A-Za-z0-9][A-Za-z0-9._:\\-]{0,99}';}
    input.oninput=()=>{set(input.type==='number'?(input.value===''?'':Number(input.value)):input.value);selected='model-edit';};wrap.append(input);parent.append(wrap);
  }
  function choose(parent,label,value,choices,set){const wrap=el('label',label),input=el('select');input.required=true;const blank=el('option','Choose explicitly');blank.value='';input.append(blank);for(const c of choices){const o=el('option',c.label||String(c.value));o.value=String(c.value);input.append(o);}input.value=choices.some(c=>String(c.value)===String(value))?String(value):'';input.onchange=()=>{set(input.value);selected='model-edit';};wrap.append(input);parent.append(wrap);return input;}
  for(const [i,p] of draft.profiles.entries()){
    const group=el('fieldset');group.append(el('legend','Profile '+(i+1)));
    field(group,'Profile '+(i+1)+' ID',p.id,v=>p.id=v);
    choose(group,'Profile '+(i+1)+' model',p.settings.model,r.capability.catalog.models.map(m=>({value:m.model})),v=>{p.settings.model=v;p.settings.effort='';render();});
    const efforts=(r.capability.catalog.models.find(m=>m.model===p.settings.model)?.efforts||[]).filter(e=>e!=='ultra');
    choose(group,'Profile '+(i+1)+' effort',p.settings.effort,efforts.map(e=>({value:e})),v=>p.settings.effort=v);
    choose(group,'Profile '+(i+1)+' quality tier',p.quality,[1,2,3,4].map(n=>({value:n,label:n+' · owner tier'})),v=>p.quality=v===''?'':Number(v));
    field(group,'Profile '+(i+1)+' minimum work tokens',p.minimumWorkTokens,v=>p.minimumWorkTokens=v,{type:'number'});
    group.append(button('Remove profile '+(i+1),()=>{if(!busy){draft.profiles.splice(i,1);render();}}));form.append(group);
  }
  const add=button('Add profile',()=>{if(!busy&&draft.profiles.length<16){draft.profiles.push({id:'',settings:{model:'',effort:'',speed:null},quality:'',minimumWorkTokens:''});render();}});add.disabled=busy||draft.profiles.length>=16;form.append(add);
  if(!draft.profiles.length)form.append(el('p','Add at least one profile. Up to 16 distinct model/effort combinations may be reviewed.','muted'));
  form.append(section('Quality and escalation limits','Complexity floors must not decrease; at least one profile must meet the highest floor.'));
  for(const c of modelComplexities)choose(form,c+' minimum quality tier',draft.qualityFloors[c],[1,2,3,4].map(n=>({value:n})),v=>draft.qualityFloors[c]=v===''?'':Number(v));
  choose(form,'Maximum per-task escalations',draft.maxEscalations,[0,1,2].map(n=>({value:n})),v=>draft.maxEscalations=v===''?'':Number(v));
  const submit=el('button','Preview model policy');submit.type='submit';submit.disabled=busy||!connected||modelStale(r)||!draft.profiles.length||draft.missionHash!==r.candidate.missionHash;
  form.append(submit,button('Close editor · keep draft',()=>{if(!busy){draft.editing=false;selected=null;render();}}));
  form.onsubmit=event=>{event.preventDefault();if(!form.reportValidity()||submit.disabled)return;previewModelControls({operation:'review',expectedRevision:r.workspaceRevision,contextHash:r.contextHash,...JSON.parse(JSON.stringify({profiles:draft.profiles,qualityFloors:draft.qualityFloors,maxEscalations:draft.maxEscalations}))});};root.append(form);
}
function modelRevokeEditor(root,r){
  if(!modelDrafts.has(workspaceId))modelDrafts.set(workspaceId,{reason:''});const draft=modelDrafts.get(workspaceId),form=el('form',null,'mission-form model-policy-form');
  form.append(section('Revoke this policy','This fences future adaptive effects. It does not kill a task or restore native defaults; use safe Pause for running work.'));
  const label=el('label','Revocation reason · no secrets'),input=el('textarea');input.required=true;input.rows=2;input.maxLength=2000;input.value=draft.reason||'';input.oninput=()=>{draft.reason=input.value;selected='model-revoke';};label.append(input);form.append(label);
  const submit=el('button','Preview model policy revocation');submit.type='submit';submit.disabled=busy||!connected||modelStale(r);form.append(submit);
  form.onsubmit=e=>{e.preventDefault();if(form.reportValidity()&&!submit.disabled)previewModelControls({operation:'revoke',expectedRevision:r.workspaceRevision,contextHash:r.contextHash,policyHash:r.policy.policyHash,reason:input.value});};root.append(form);
}
function modelConfirmation(root,entry){
  const d=entry.proposal.document,r=d.request,review=d.operation==='review',wrap=el('section',null,'mission-review retention-preview');wrap.id='model-policy-confirmation';wrap.tabIndex=-1;
  wrap.append(section(review?'Confirm model policy':'Confirm policy revocation',`Preview expires ${when(d.expiresAt)}. No policy change has been recorded yet.`),el('p','Project: '+d.workspaceId));
  if(review){wrap.append(el('p','Reviewed phase: '+d.scope.mission.phaseId),modelProfileTable(r.profiles),el('p','Quality floors: '+modelComplexities.map(c=>c+' '+r.qualityFloors[c]).join(' · ')),el('p','Maximum per-task escalations: '+r.maxEscalations),el('p','Capability observed: '+when(d.scope.capability.observedAt)));}
  else wrap.append(el('p','Policy SHA-256: '+r.policyHash,'mono mission-hash'),el('p',r.reason));
  wrap.append(callout('Existing run authority will be fenced','No model is called, task switched, usage reset or Play started. Policy review does not stop native work at a checkpoint; use Pause separately. A subsequent run still needs exact owner authorization.'));
  const label=el('label'),check=el('input');check.type='checkbox';check.checked=false;label.append(check,el('span',review?'I reviewed these exact profiles and limits for this mission and understand the run fence.':'I revoke this exact policy and understand the run fence.'));wrap.append(label);
  const submit=button(entry.uncertain?'Retry the same policy confirmation':review?'Record model policy review':'Revoke model policy',()=>{if(check.checked)confirmModelControls(entry);},'primary');submit.disabled=true;check.onchange=()=>submit.disabled=busy||!connected||!check.checked;
  wrap.append(submit,button('Back to model policy',()=>{if(!busy){modelPreviews.delete(workspaceId);selected=null;render();}}));
  if(entry.uncertain)wrap.append(el('p','Response not confirmed. Retry uses the identical signed request; it cannot restore a subsequently revoked policy.','muted'));
  const exactScope=el('details');exactScope.append(el('summary','Exact mission, capability and policy scope'),el('pre',JSON.stringify(d,null,2)));wrap.append(exactScope);root.append(wrap);
}
async function inspectModelControls(){
  const wid=workspaceId,generation=workspaceGeneration;if(!wid||busy||!connected||modelPending.has(wid))return;
  const token={};modelPending.set(wid,token);modelPreviews.delete(wid);selected=null;render();
  try{const r=await api('/api/model-policy-controls');if(workspaceId===wid&&workspaceGeneration===generation&&r.workspaceId===wid)modelReports.set(wid,r);}
  catch(error){if(!error.workspaceChanged&&workspaceId===wid&&workspaceGeneration===generation){modelReports.delete(wid);showNotice('Policy inspection failed. No settings changed. '+error.message,true);}}
  finally{if(modelPending.get(wid)===token)modelPending.delete(wid);if(workspaceId===wid&&workspaceGeneration===generation&&view==='mission')render();}
}
async function modelPost(path,body,done){
  if(busy||!connected)return false;const wid=workspaceId,generation=workspaceGeneration;busy=true;updateWorkspaceSelector();if(view==='mission')render();
  try{const result=await api(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});if(workspaceId===wid&&workspaceGeneration===generation){done(result);return true;}}
  catch(error){if(!error.workspaceChanged&&workspaceId===wid&&workspaceGeneration===generation){if(path.endsWith('/confirm')&&modelPreviews.has(wid))modelPreviews.get(wid).uncertain=true;showNotice(error.message+' No automatic retry was sent. Your draft is retained.',true);}}
  finally{busy=false;updateWorkspaceSelector();if(workspaceId===wid&&workspaceGeneration===generation&&view==='mission')render();}return false;
}
async function previewModelControls(body){
  const wid=workspaceId,generation=workspaceGeneration;const saved=await modelPost('/api/model-policy-controls/preview',body,proposal=>{if(proposal.document.workspaceId!==wid)throw new Error('Foreign policy preview');modelPreviews.set(wid,{proposal,generation,uncertain:false});selected='model-confirm';});
  if(saved&&workspaceGeneration===generation&&view==='mission'&&typeof document!=='undefined')document.getElementById('model-policy-confirmation')?.focus();return saved;
}
async function confirmModelControls(entry){
  const wid=workspaceId,generation=workspaceGeneration;if(entry.generation!==generation||entry!==modelPreviews.get(wid))return false;
  const saved=await modelPost('/api/model-policy-controls/confirm',{proposal:entry.proposal,confirmed:true},result=>{modelPreviews.delete(wid);modelReports.delete(wid);selected=null;if(modelDrafts.has(wid))modelDrafts.get(wid).editing=false;showNotice(result.replayed?'Original policy receipt recovered; no authority was reapplied.':'Model policy '+(entry.proposal.document.operation==='review'?'review recorded':'revoked')+'. Run authority is fenced; no native settings changed.');});
  if(saved&&workspaceId===wid&&workspaceGeneration===generation){await refresh();await inspectModelControls();}return saved;
}
