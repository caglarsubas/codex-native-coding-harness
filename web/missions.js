"use strict";
Object.assign(titles,{mission:['Mission & authority','Define the next phase. Review its boundaries before activation.']});
const missionDrafts=new Map(),missionRequests=new Map();
const missionModes={prepare_only:'Prepare only',exact_owner:'Exact owner-approved packets',phase_delegated:'Brain approves within a reviewed phase'};
const missionOperations=['edit','test','commit','push','open_pr','merge'];
const missionLines=value=>value.split('\n').map(x=>x.trim()).filter(Boolean);
function missionSummary(root){
  if(!state.mission)return;
  const m=state.mission,panel=el('section',null,'mission-summary');
  panel.append(el('p','MISSION SETUP · NOT ACTIVE','eyebrow'),el('h2',m.document?m.document.spec.phase.title:'Define what Play should deliver'));
  panel.append(el('p',m.document?`Configuration v${m.version} · ${m.effectiveStatus.replaceAll('_',' ')}. Autonomous Play is not available yet.`:'Set the phase, permitted repositories, owner checkpoint and proposed task/token limits. Existing dispatch controls remain separate.','muted'));
  panel.append(button(m.document?'Review mission & authority':'Configure mission & authority',()=>navigateView('mission')),
    button('Inspect run readiness',()=>navigateView('runReadiness')),button('Task retention',()=>navigateView('retention')));root.append(panel);
}
function missionDocument(parent,hash,label){
  const details=el('details',null,'mission-document'),pre=el('pre','Open to read the immutable document.');
  details.append(el('summary',label),pre);details.addEventListener('toggle',async()=>{
    if(!details.open||details.dataset.loaded)return;
    try{const data=await api('/api/documents/'+hash);if(details.isConnected){pre.textContent=JSON.stringify(data,null,2);details.dataset.loaded='true';}}
    catch(error){if(!error.workspaceChanged)pre.textContent=error.message;}
  });parent.append(details);
}
function missionView(root){
  const m=state.mission;
  if(!m){root.append(empty('Select a registered workspace','Mission configuration belongs to one workspace and its designated brain.'));return;}
  const status=el('section',null,'mission-status');
  status.append(el('p','CONFIGURATION, NOT EXECUTION AUTHORITY','eyebrow'),el('h2',m.document?`Version ${m.version} · ${m.effectiveStatus.replaceAll('_',' ')}`:'No mission configured'));
  status.append(el('p','Saving or reviewing a configuration does not start development, approve packets, enforce these proposed limits, change a model or notify the brain. Existing exact packet approvals and dispatch controls are unchanged.','checkpoint'));
  const activation=el('details');activation.append(el('summary','Why autonomous Play is unavailable'));
  const blockers=el('ul');m.activation.blockers.forEach(reason=>blockers.append(el('li',reason)));activation.append(blockers);
  activation.append(el('p','This release prepares the contract. Play will require a separate owner-bound activation after these gates are implemented. A reviewed version cannot activate automatically after an upgrade.','muted'));status.append(activation);root.append(status);
  if(m.bindingIssues.length)root.append(callout('Configuration needs a new version',m.bindingIssues.join(' ')));
  if(missionDrafts.has(workspaceId)){missionEditor(root,m);return;}
  if(typeof modelControlPanel==='function')modelControlPanel(root);
  if(!m.document){root.append(button('Create mission draft',()=>openMissionEditor(),'primary'));return;}
  const spec=m.document.spec,phase=spec.phase,a=spec.authority;
  root.append(section('The proposed outcome',phase.id),el('h3',spec.goal));
  const list=(title,items)=>{root.append(el('h3',title));const ul=el('ul');items.forEach(item=>ul.append(el('li',item)));root.append(ul);};
  list('Success criteria',spec.successCriteria);root.append(el('h3',phase.title),el('p',phase.objective,'checkpoint'));
  root.append(section('Stop at this owner checkpoint'),el('p',phase.checkpoint,'checkpoint'));list('Stop sooner if…',phase.stopConditions);list('Explicit exclusions',spec.exclusions);
  root.append(section('Repository boundaries','Repository instructions and merge policies still take precedence.'));
  root.append(table(['Repository','Allowed paths','Proposed operations / policy'],phase.scope.map(row=>{
    const binding=m.document.repositoryBindings.find(r=>r.repository===row.repository);
    return [row.repository,row.allowedPaths.join('\n'),textCell(row.operations.join(', '),`${binding.policyProfile} · ${binding.mergePolicy} merge`)];
  })));
  root.append(section('Proposed limits','Not active, reserved or enforced in this release.'));
  root.append(table(['Setting','Proposed value'],[['Packet approval',missionModes[a.approvalMode]],['Parallel tasks',num(a.maxParallelTasks)],['Total tasks in this phase',num(a.maxTasks)],['Phase token allocation',num(a.tokenBudget)],['Included checkpoint reserve',num(a.checkpointReserveTokens)]]));
  root.append(el('p','Token allocations will include brain, workers, review and checkpoint headroom. They are not a subscription bill or a provider-enforced hard stop. Model, effort and speed routing are not configured by this form.','muted'));
  root.append(el('p','Exact configuration SHA-256: '+m.documentHash,'mono mission-hash'));
  const actions=el('section',null,'mission-review');actions.append(button('Revise as a new draft',()=>openMissionEditor()));
  if(m.status==='draft'&&!m.bindingIssues.length)missionConfirmation(actions,m,'review','Record owner review',`I reviewed configuration v${m.version} and its exact hash above. This records review only; it does not activate Play or approve a packet.`);
  if(m.status==='reviewed')missionConfirmation(actions,m,'revoke','Revoke this review','Withdraw review of this configuration. This does not stop an existing brain or worker; use the separate safe-checkpoint control for that.');
  root.append(actions);
  missionDocument(root,m.documentHash,'Read exact configuration · v'+m.version);
  if(m.receiptHash)missionDocument(root,m.receiptHash,'Read latest owner/draft receipt');
  const history=el('section');history.append(section('Version history','Immutable documents; review never rewrites a version.'));root.append(history);
  api('/api/mission').then(data=>{if(!history.isConnected)return;for(const v of data.history)missionDocument(history,v.documentHash,`v${v.version} · ${v.title} · ${when(v.createdAt)}`);if(data.olderDocumentHash)missionDocument(history,data.olderDocumentHash,'Earlier version · follow previousHash for older records');}).catch(error=>{if(history.isConnected&&!error.workspaceChanged)history.append(el('p',error.message));});
}
function missionConfirmation(parent,m,operation,title,explanation){
  const wrap=el('div',null,'mission-confirmation'),label=el('label'),check=el('input');check.type='checkbox';
  label.append(check,el('span',explanation));const submit=button(title,()=>missionWrite({operation,expectedRevision:m.revision,documentHash:m.documentHash,confirmed:true},submit));
  submit.disabled=true;check.onchange=()=>{submit.disabled=!check.checked||busy;selected=check.checked?'mission-review':null;};wrap.append(label,submit);parent.append(wrap);
}
function openMissionEditor(){
  if(busy)return;
  const m=state.mission,spec=m.document?.spec;
  missionDrafts.set(workspaceId,{revision:m.revision,spec:spec?JSON.parse(JSON.stringify(spec)):{goal:'',successCriteria:[],exclusions:[],phase:{id:'',title:'',objective:'',checkpoint:'',stopConditions:[],scope:[]},authority:{approvalMode:'exact_owner',maxParallelTasks:'',maxTasks:'',tokenBudget:'',checkpointReserveTokens:''}}});
  selected='mission-edit';render();document.querySelector('.mission-form textarea')?.focus();
}
function missionEditor(root,m){
  selected='mission-edit';const draft=missionDrafts.get(workspaceId),spec=draft.spec,phase=spec.phase,a=spec.authority;
  const form=el('form',null,'mission-form');form.append(section(m.document?'Revise mission configuration':'New mission configuration','No secrets, credentials or executable commands.'));
  if(draft.revision!==m.revision)form.append(callout('A newer configuration exists','Your edits remain here. Compare the current version before discarding this draft; stale saves will be refused.'));
  function field(label,value,set,{rows=2,type='text',min=1,max=2000}={}){
    const wrap=el('label',label),input=el(type==='number'||rows===0?'input':'textarea');
    if(input.tagName==='TEXTAREA'){input.rows=rows;input.maxLength=max;}else{input.type=type;if(type==='number'){input.min=min;input.max=max;input.step=1;}else input.maxLength=max;}
    input.required=true;input.value=value;input.oninput=()=>set(type==='number'?(input.value===''?'':Number(input.value)):input.value);wrap.append(input);form.append(wrap);return input;
  }
  field('Mission goal',spec.goal,v=>spec.goal=v);
  field('Success criteria · one per line',spec.successCriteria.join('\n'),v=>spec.successCriteria=missionLines(v),{rows:3,max:20000});
  field('Exclusions · one per line',spec.exclusions.join('\n'),v=>spec.exclusions=missionLines(v),{rows:2,max:20000});
  field('Phase ID · lowercase letters, digits and hyphens',phase.id,v=>phase.id=v,{rows:0,max:64});
  field('Phase title',phase.title,v=>phase.title=v,{rows:0});
  field('Phase objective',phase.objective,v=>phase.objective=v);
  field('Mandatory owner checkpoint · what must be reviewed before continuing',phase.checkpoint,v=>phase.checkpoint=v);
  field('Stop conditions · one per line',phase.stopConditions.join('\n'),v=>phase.stopConditions=missionLines(v),{rows:3,max:20000});
  form.append(section('Permitted repositories','Select explicitly; no repository or operation is pre-authorized.'));
  const missing=phase.scope.filter(row=>!state.repositories.some(repo=>repo.id===row.repository));
  if(missing.length){form.append(el('p','No longer registered: '+missing.map(row=>row.repository).join(', '),'muted'),button('Remove unregistered repositories from draft',()=>{phase.scope=phase.scope.filter(row=>!missing.includes(row));render();}));}
  for(const repo of state.repositories){
    const row=phase.scope.find(s=>s.repository===repo.id)||{repository:repo.id,allowedPaths:[],operations:[]};
    const group=el('fieldset'),legend=el('legend',repo.id),label=el('label'),check=el('input');check.type='checkbox';check.checked=phase.scope.includes(row);label.append(check,el('span','Include '+repo.id));group.append(legend,label,el('p',`${repo.policyProfile} · ${repo.mergePolicy} merge policy`,'muted'));
    const pathsLabel=el('label','Allowed paths · one per line; for example src/feature/**'),paths=el('textarea');paths.rows=3;paths.maxLength=16000;paths.value=row.allowedPaths.join('\n');paths.disabled=!check.checked;paths.required=check.checked;pathsLabel.append(paths);group.append(pathsLabel);
    paths.oninput=()=>row.allowedPaths=missionLines(paths.value);
    const ops=el('div',null,'mission-operations'),opInputs=[];
    for(const operation of missionOperations){const opLabel=el('label'),input=el('input');input.type='checkbox';input.checked=row.operations.includes(operation);const forbidden=operation==='merge'&&repo.mergePolicy==='manual';input.disabled=!check.checked||forbidden;input.onchange=()=>{row.operations=input.checked?[...row.operations,operation]:row.operations.filter(x=>x!==operation);};opLabel.append(input,el('span',operation.replaceAll('_',' ')+(forbidden?' · manual only':'')));ops.append(opLabel);opInputs.push({input,forbidden});}
    const update=()=>{paths.disabled=!check.checked;paths.required=check.checked;opInputs.forEach(({input,forbidden})=>input.disabled=!check.checked||forbidden);};
    check.onchange=()=>{phase.scope=check.checked?[...phase.scope,row]:phase.scope.filter(s=>s.repository!==repo.id);update();};
    group.append(ops);form.append(group);
  }
  if(!state.repositories.length)form.append(el('p','No repositories are registered in this workspace. Register a repository before saving a phase.','muted'));
  form.append(section('Proposed authority & limits','No defaults for token or task allowances: choose them explicitly.'));
  const modeLabel=el('label','Packet approval mode'),mode=el('select');for(const [value,label] of Object.entries(missionModes)){const option=el('option',label);option.value=value;mode.append(option);}mode.value=a.approvalMode;mode.onchange=()=>a.approvalMode=mode.value;modeLabel.append(mode);form.append(modeLabel);
  form.append(el('p','Harness scopes require exact owner approval. A phase-delegated configuration is allowed only for standard-policy repositories, and remains inactive in this release.','muted'));
  for(const [key,label,max] of [['maxParallelTasks','Maximum parallel tasks',16],['maxTasks','Maximum tasks in this phase',1000],['tokenBudget','Phase token allocation',1000000000],['checkpointReserveTokens','Checkpoint reserve · included in the allocation',1000000000]])field(label,a[key],v=>a[key]=v,{type:'number',max});
  form.append(el('p','These are proposed local admission limits, not currently enforced budgets or provider hard caps. No model or effort setting changes.','muted'));
  const save=el('button','Save draft','primary');save.type='submit';save.disabled=!state.repositories.length;
  const cancel=button('Discard unsaved edits',()=>{if(busy)return;missionDrafts.delete(workspaceId);selected=null;render();});form.append(save,cancel);
  form.onsubmit=event=>{event.preventDefault();if(!form.reportValidity())return;missionWrite({operation:'save',expectedRevision:draft.revision,spec:JSON.parse(JSON.stringify(spec))},save);};
  root.append(form);
}
async function missionWrite(payload,control){
  if(busy||!connected)return;
  const key=JSON.stringify([workspaceId,payload]);
  if(!missionRequests.has(key))missionRequests.set(key,{id:crypto.randomUUID(),...payload});
  busy=true;control.disabled=true;updateWorkspaceSelector();
  const form=control.closest('form');if(form)form.inert=true;
  if(control.nextElementSibling?.classList.contains('mission-write-status'))control.nextElementSibling.remove();
  const localStatus=el('p',null,'mission-write-status');localStatus.setAttribute('role','status');control.after(localStatus);
  try{
    await api('/api/mission',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(missionRequests.get(key))});
    missionRequests.delete(key);if(payload.operation==='save')missionDrafts.delete(workspaceId);selected=null;
    await refresh();showNotice('Configuration '+({save:'draft saved',review:'review recorded',revoke:'review revoked'}[payload.operation])+'. No execution was authorized and no brain notification was sent.');
  }catch(error){if(!error.workspaceChanged){const message=error.message.replace(/[.!?]$/,'')+'. Your draft is retained. Uncertain retries use the same request ID.';showNotice(message,true);localStatus.textContent=message;}}
  finally{busy=false;control.disabled=false;if(form)form.inert=false;updateWorkspaceSelector();}
}
