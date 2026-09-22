"use strict";
let workspaceId=null, workspaceGeneration=0, workspaceSwitching=false, workspaceWrites=0, workspaceList=[];
let projectCatalog=null;
function selectedProject(){return workspaceList.find(p=>p.id===workspaceId);}
function unconfiguredProject(){return selectedProject()?.managed===false;}
const workspaceTabs=new Map();
let codeSnapshotPage=0;
const codeDetailsOpen=new Set();
Object.assign(titles,{workspaces:['All projects','Recorded measurements across separate development lifecycles.']});
function workspacePath(path,id=workspaceId){
  return id&&path.startsWith('/api/')&&!path.startsWith('/api/workspaces')&&path!=='/api/login'
    ?'/api/workspaces/'+encodeURIComponent(id)+path.slice(4):path;
}
function workspaceHref(target,id=null,wid=workspaceId){return '#/'+(wid?'w/'+wid+'/':'')+target+(id?'/'+id:'');}
function workspaceLocked(){return busy||workspaceWrites>0||workspaceSwitching||assistantPending||[...assistantActions.values()].some(a=>a.sending);}
function updateWorkspaceSelector(){const select=$('workspace-select');if(select)select.disabled=workspaceLocked();updateNavigationButton();}
function saveWorkspaceTab(){
  if(!workspaceId)return;
  workspaceTabs.set(workspaceId,{history:assistantHistory,turns:assistantTurns,tokens:assistantTokens,missing:assistantMissingUsage,
    actions:[...assistantActions],chat:[...$('assistant-log').querySelectorAll('.chat-turn')],question:$('assistant-question').value,
    status:$('assistant-status').textContent,usage:$('assistant-usage').textContent,drafts:[...decisionDrafts],controls:[...controlRequests],autoObserve});
}
function restoreWorkspaceTab(id){
  const saved=workspaceTabs.get(id);
  assistantHistory=saved?.history||[];assistantTurns=saved?.turns||0;assistantTokens=saved?.tokens||0;assistantMissingUsage=saved?.missing||0;
  for(const [map,entries] of [[assistantActions,saved?.actions],[decisionDrafts,saved?.drafts],[controlRequests,saved?.controls]]){map.clear();for(const [k,v] of entries||[])map.set(k,v);}
  $('assistant-log').querySelectorAll('.chat-turn').forEach(node=>node.remove());
  for(const node of saved?.chat||[])$('assistant-log').append(node);
  $('assistant-question').value=saved?.question||'';$('assistant-welcome').hidden=assistantHistory.length>0;
  $('assistant-context-preview').textContent='';$('assistant-context-preview').hidden=true;
  $('assistant-status').textContent=saved?.status||'';$('assistant-status').dataset.error='false';
  $('assistant-usage').textContent=saved?.usage||'Chat is private to this project and tab. Actions require confirmation.';
  decisionDetailsOpen.clear();codeDetailsOpen.clear();observationRepo='all';observationPage=0;codeSnapshotPage=0;artifactQuery='';autoObserve=saved?.autoObserve||false;lastAutoAttempt=0;
}
async function initializeWorkspaces(){
  const data=await api('/api/workspaces');projectCatalog=data.catalog;
  workspaceList=projectCatalog?.source?[...projectCatalog.projects,...projectCatalog.unlisted]:data.workspaces;
  if(!data.enabled)return;
  $('workspace-picker').hidden=false;
  $('mission-nav').hidden=false;
  $('run-readiness-nav').hidden=false;
  $('phase-checkpoints-nav').hidden=false;
  $('retention-nav').hidden=false;
  if(!workspaceList.length)throw new Error('No registered projects are available.');
  const select=$('workspace-select');select.replaceChildren();
  select.onchange=()=>switchWorkspace(select.value);
  populateProjectSelector();
  const route=dashboardRoute(location.hash);
  let remembered=null;try{remembered=sessionStorage.getItem('orchestrator-workspace');}catch{}
  const id=route?.workspaceId||(workspaceList.some(w=>w.id===remembered)?remembered:(workspaceList.find(w=>w.managed!==false)||workspaceList[0]).id);
  if(!workspaceList.some(w=>w.id===id))throw new Error('This project link is not registered. Select a project from the menu.');
  await selectWorkspaceIdentity(id);
}
async function selectWorkspaceIdentity(id){
  workspaceId=id;workspaceGeneration++;csrf=null;state=null;connected=false;selected=null;view='overview';
  $('workspace-select').value=id;$('notice').hidden=true;
  $('mode').textContent='Connecting to '+workspaceList.find(w=>w.id===id).name+'…';
  $('content').replaceChildren(empty('Opening project','Loading only this project’s recorded state.'));
  $('export-report').href=workspacePath('/api/export');
  $('assistant-workspace').textContent=workspaceList.find(w=>w.id===id).name;
  assistantConnectionChanged();
  $('export-report').hidden=unconfiguredProject();
  if(!unconfiguredProject())csrf=(await api('/api/session')).csrf;
  try{sessionStorage.setItem('orchestrator-workspace',id);}catch{}
}
async function switchWorkspace(id,route=null,updateAddress=true){
  if(updateAddress&&navigationPending){showNotice('Wait for page navigation to finish.',true);$('workspace-select').value=workspaceId;return false;}
  if(workspaceLocked()){showNotice('Wait for the in-flight request before switching projects. Nothing has been moved or cancelled.',true);$('workspace-select').value=workspaceId;return false;}
  if(!workspaceList.some(w=>w.id===id)){showNotice('Unknown project. No data was opened.',true);return false;}
  workspaceSwitching=true;updateWorkspaceSelector();saveWorkspaceTab();
  try{
    restoreWorkspaceTab(id);await selectWorkspaceIdentity(id);await refresh();
    if(!connected&&!unconfiguredProject())return false;
    navigateView(route?.view||'overview',route?.id||null,updateAddress);
    return true;
  }catch(error){showNotice(error.message,true);return false;}
  finally{workspaceSwitching=false;updateWorkspaceSelector();}
}
function populateProjectSelector(){
  const select=$('workspace-select');select.replaceChildren();
  const listed=projectCatalog?.source?projectCatalog.projects:workspaceList;
  for(const p of listed){const option=el('option',p.name);option.value=p.id;select.append(option);}
  if(projectCatalog?.source&&projectCatalog.unlisted.length){
    const group=el('optgroup');group.label='Retained projects · not in Codex list';
    for(const p of projectCatalog.unlisted){const option=el('option',p.name);option.value=p.id;group.append(option);}select.append(group);
  }
  select.value=workspaceId;
}
async function reloadProjectCatalog(){
  const data=await api('/api/workspaces');
  projectCatalog=data.catalog;
  const next=projectCatalog?.source?[...projectCatalog.projects,...projectCatalog.unlisted]:data.workspaces;
  // Keep the current identity stable; removal is a visible retained entry, never a fallback to another ledger.
  const old=selectedProject();
  if(old&&!next.some(p=>p.id===old.id))next.push({...old,managed:false,bindingStatus:'not_listed'});
  workspaceList=next;populateProjectSelector();
  if(old&&!$('workspace-select').value){const option=el('option',old.name+' · no longer listed');option.value=old.id;$('workspace-select').append(option);$('workspace-select').value=old.id;}
}
function projectCatalogPanel(root){
  const block=el('section',null,'project-introduction');
  block.append(section('Codex projects','Native names and order from the last successful Codex project-list observation.'));
  block.append(el('p',projectCatalog?.source?'Last synced '+when(projectCatalog.observedAt)+'. This is a retained list, not a live connection.':'No Codex project list has been synced yet. Registered project history remains available.','muted'));
  block.append(button('Reload saved list',async()=>{try{await reloadProjectCatalog();render();}catch(error){showNotice(error.message,true);}}));
  block.append(table(['Project','Host','Orchestration'],(projectCatalog?.projects||[]).map(p=>[
    button(p.name,()=>switchWorkspace(p.id)),p.hostId,p.managed?'Configured':p.bindingStatus==='needs_review'?'Binding needs review':'Not configured'
  ])));
  const refreshers=workspaceList.filter(p=>p.managed!==false);
  if(refreshers.length){
    const detail=el('details');detail.append(el('summary','Sync changes from Codex'),el('p','Prepare a request to an existing project brain, then review and send it in Brain conversation. This uses your Codex allowance; it does not start development or resume a paused brain.'));
    for(const p of refreshers)detail.append(button('Ask '+p.name+' to sync projects',()=>prepareProjectSync(p.id)));
    block.append(detail);
  }
  root.append(block);
}
async function prepareProjectSync(id){
  const existing=brainDrafts.get(id);
  if(existing?.text||existing?.request){showNotice('This project already has an unsent conversation draft. Open its Brain conversation and preserve or send that draft first.',true);return;}
  if(!await switchWorkspace(id,{view:'conversation'}))return;
  brainDrafts.set(id,{text:'Refresh the platform’s Codex project catalog only. Read docs/PROJECT-CATALOG.md in the dashboard source checkout referenced by this notification, call the native list_projects tool, and import its complete result with the original observation time using project-sync. Preserve all project-to-ledger bindings. Do not create tasks, register ledgers, start development, change authority or resume paused work. Retain a reply with the result.',confirmed:false,request:null});
  render();showNotice('Sync request prepared, not sent. Review the message and confirm its recipient.');
}
function renderUnconfiguredProject(){
  const p=selectedProject();if(!p)return;
  document.querySelector('.page-actions').hidden=true;
  $('pause').disabled=true;$('reconcile').disabled=true;$('export-report').hidden=true;
  $('mode').textContent=p.name+' · '+(p.bindingStatus==='not_listed'?'No longer listed in Codex':'Orchestration not configured');
  $('connection').textContent='Project catalog · no ledger connected';
  $('title').textContent=view==='workspaces'?'All projects':p.name;
  $('subtitle').textContent='A Codex project is not automatically an authorized development run.';
  const root=$('content');root.replaceChildren();
  if(view==='workspaces'){allWorkspaces(root);return;}
  root.append(empty(p.bindingStatus==='needs_review'?'Project binding needs review':'Set up this project for orchestration',
    'This project is listed in Codex, but no verified development ledger is connected here. No other project’s conversation, metrics or controls are shown.'));
  const steps=el('ol');
  for(const line of ['Choose the existing Codex task that will act as this project’s brain.','Register a separate private ledger and explicitly bind it to this Codex project identity.','Review its mission, phase checkpoints and budget before using Play.'])steps.append(el('li',line));
  root.append(steps,el('p','Selection alone never creates tasks or starts development. Setup is currently an operator step; the catalog sync request only updates this list.','muted'),button('All projects',()=>navigateView('workspaces')));
}
function projectIntroduction(root){
  const workspace=state.workspace;if(!workspace)return;
  const record=workspace.projectProfile,profile=record?.profile;
  const panel=el('section',null,'project-introduction');
  panel.append(el('p','SELECTED PROJECT · '+workspace.name,'eyebrow'),el('h2',profile?.goal||'Introduce this project'));
  if(profile){
    panel.append(el('p',profile.roadmap||'Roadmap summary not supplied.','checkpoint'));
    const detail=el('details');detail.append(el('summary','Success criteria, architecture & technology'));
    detail.append(el('h3','Success criteria'));const list=el('ul');profile.successCriteria.forEach(c=>list.append(el('li',c)));detail.append(list);
    detail.append(el('h3','Architecture'),el('p',profile.architecture||'Not supplied.'),el('h3','Technology'),el('p',profile.techStack.join(' · ')||'Not supplied.'));
    if(profile.references.length){detail.append(el('h3','Source references'));profile.references.forEach(ref=>detail.append(el('p',ref,'mono')));}
    detail.append(el('p',`Owner-maintained introduction · version ${record.version} · ${when(record.updatedAt)}. Not a live progress or acceptance claim.`,'muted'));panel.append(detail);
  }else panel.append(el('p','Add the goal, success criteria, architecture, stack and roadmap summary. Saving this introduction does not authorize development.','muted'));
  panel.append(button(profile?'Edit project introduction':'Add project introduction',()=>editProjectIntroduction(panel),profile?'':'primary'));
  root.append(panel);
}
function editProjectIntroduction(panel){
  if(panel.querySelector('form'))return;
  const record=state.workspace.projectProfile,value=record.profile||{},form=el('form',null,'project-profile-form');
  const fields={goal:'Goal / short introduction',successCriteria:'Success criteria · one per line',architecture:'Architecture',techStack:'Technology stack · one per line',roadmap:'Roadmap summary & next owner checkpoint',references:'Source references · one per line'};
  const inputs={};
  for(const [key,title] of Object.entries(fields)){const label=el('label',title),input=el('textarea');input.rows=['goal','techStack','references'].includes(key)?2:3;input.maxLength=4000;input.value=Array.isArray(value[key])?value[key].join('\n'):value[key]||'';inputs[key]=input;label.append(input);form.append(label);}
  const confirm=el('button','Save introduction','primary');confirm.type='submit';
  form.append(el('p','No secrets. This is descriptive project metadata, not permission to start tasks or approve packets. It may be included in assistant context when you explicitly send a message.','muted'),confirm,button('Cancel',()=>form.remove()));
  form.onsubmit=async event=>{event.preventDefault();if(busy)return;busy=true;confirm.disabled=true;
    const profile=Object.fromEntries(Object.keys(fields).map(key=>[key,['successCriteria','techStack','references'].includes(key)?inputs[key].value.split('\n').map(x=>x.trim()).filter(Boolean):inputs[key].value.trim()]));
    try{await api('/api/profile',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({profile,expectedVersion:record.version})});await refresh();showNotice('Project introduction saved. No development was started.');}
    catch(error){showNotice(error.message+' Your edits remain in this form.',true);}
    finally{busy=false;confirm.disabled=false;updateWorkspaceSelector();}
  };
  panel.append(form);inputs.goal.focus();
}
function codeCountingLabel(counting){
  if(counting?.status==='included')return 'Counted once';
  if(counting?.status==='alias')return 'Alias · counted elsewhere';
  const codes=counting?.issues||[];
  if(codes.some(c=>c.includes('conflict')))return 'Excluded · conflicting observations';
  if(codes.includes('repository_configuration_changed'))return 'Excluded · repository settings changed';
  if(codes.includes('identity_refresh_required'))return 'Excluded · refresh identity evidence';
  return 'Excluded · measurement unavailable or invalid';
}
function rememberCodeDetails(details,key,onOpen=null){
  details.open=codeDetailsOpen.has(key);
  details.addEventListener('toggle',()=>{
    if(details.isConnected===false)return;
    if(details.open){codeDetailsOpen.add(key);if(onOpen)onOpen();}else codeDetailsOpen.delete(key);
  });
  if(details.open&&onOpen)onOpen();
}
function codeCountingCoverage(root,coverage,workspaceLinks=false){
  if(!coverage)return;
  root.append(el('p',`${coverage.configuredRows} repository entries · ${coverage.duplicateAliases} duplicate aliases · ${coverage.excludedRows} excluded from totals.`,'metric-note'));
  if(coverage.excludedRows)root.append(callout('Some code measurements are excluded','Old records without identity evidence, changed repository settings and conflicting measurements cannot be counted safely. Open the affected project’s Portfolio metrics and refresh observations. Missing values are not zero.'));
  if(coverage.issues?.length){
    const details=el('details'),list=el('ul');details.append(el('summary',`Excluded measurements · ${coverage.issues.length} ${coverage.issues.length===1?'entry':'entries'}`));
    for(const issue of coverage.issues.slice(0,40)){
      const item=el('li'),label=issue.repository+' · '+codeCountingLabel({status:'excluded',issues:issue.codes});
      item.append(workspaceLinks?button(issue.workspaceId+' / '+label,()=>switchWorkspace(issue.workspaceId,{view:'metrics'})):el('span',label));list.append(item);
    }
    details.append(list);if(coverage.issues.length>40)details.append(el('p','Showing the first 40 exclusions. Open individual projects for their full repository distribution.','metric-note'));rememberCodeDetails(details,'exclusions/'+(workspaceLinks?'all':workspaceId));root.append(details);
  }
  if(coverage.localOnlySnapshots)root.append(el('p',`${coverage.localOnlySnapshots} snapshots use local Git identity only. Separate clones without a supported origin cannot be matched automatically.`,'metric-note'));
}
function codeSnapshotTable(root,snapshots){
  const block=el('section');root.append(block);
  function draw(){
    block.replaceChildren();const pages=Math.max(1,Math.ceil(snapshots.length/40));
    codeSnapshotPage=Math.max(0,Math.min(codeSnapshotPage,pages-1));
    block.append(table(['Commit / counting basis','Repository aliases','Counted lines','State'],snapshots.slice(codeSnapshotPage*40,(codeSnapshotPage+1)*40).map(s=>{
      const aliases=el('details');aliases.append(el('summary',`${s.aliases.length} repository ${s.aliases.length===1?'entry':'entries'}`));
      rememberCodeDetails(aliases,'snapshot/'+(s.id||s.commit),()=>{if(aliases.dataset.loaded)return;aliases.dataset.loaded='true';
        const list=el('ul');for(const a of s.aliases){const item=el('li');item.append(button(a.workspaceId+' / '+a.repository,()=>switchWorkspace(a.workspaceId,{view:'metrics'})));list.append(item);}aliases.append(list);});
      return [textCell(s.commit.slice(0,12),s.identityBasis==='conventional_origin'?'Same conventional origin':'Same local Git directory'),aliases,num(s.lines),s.status==='counted'?'Counted once':'Conflicting measurements'];
    })));
    const actions=el('div',null,'pagination'),prev=button('Previous code snapshots',()=>{codeSnapshotPage--;draw();}),next=button('Next code snapshots',()=>{codeSnapshotPage++;draw();});
    prev.disabled=codeSnapshotPage===0;next.disabled=codeSnapshotPage===pages-1;actions.append(prev,el('span',`Page ${codeSnapshotPage+1} / ${pages} · ${snapshots.length} code snapshots`),next);block.append(actions);
  }
  draw();
}
function allWorkspaces(root){
  projectCatalogPanel(root);
  const container=el('section');container.append(el('p','Loading retained project measurements…'));root.append(container);
  api('/api/workspaces/summary').then(data=>{
    if(!container.isConnected)return;container.replaceChildren();
    container.append(callout('Project scopes remain separate','This comparison does not authorize work. The assistant remains scoped to the project selected in the menu.'));
    const a=data.aggregate,strip=el('div',null,'summary-strip');
    for(const [value,label] of [[a.lines,'counted code lines'],[a.tokens,'deduplicated tokens'],[a.managedTasks,'managed tasks'],[a.uniqueArtifactVersions,'artifact versions']]){const item=el('div');item.append(el('strong',num(value)),el('span',label));strip.append(item);}
    container.append(strip);
    if(a.cooperativeTasks)container.append(el('p',`${num(a.cooperativeCompletedTasks)} / ${num(a.cooperativeTasks)} cooperative tasks completed across current project phases. Historical log tokens and legacy task totals above remain separate.`,'checkpoint'));
    const method=el('details');method.append(el('summary','How totals are counted'),el('p',data.method,'metric-note'));rememberCodeDetails(method,'method');container.append(method);
    codeCountingCoverage(container,data.codeCoverage,true);
    if(a.conflictingSessionsExcluded)container.append(el('p',`${a.conflictingSessionsExcluded} shared task summaries conflict and are excluded from aggregate tokens. Review project coverage.`,'metric-note'));
    container.append(table(['Project','Dispatch / checkpoint','Workers','Code lines','Observed tokens'],data.workspaces.map(w=>{
      const name=el('div');name.append(button(w.name,()=>switchWorkspace(w.id)));
      return [name,w.status==='unavailable'?'Unavailable':textCell(w.cooperative?'Cooperative · '+w.cooperative.status:w.paused?'Paused':'Enabled',when(w.lastReconciled)),num(w.cooperative?w.cooperative.active:w.activeWorkers),num(w.metrics?.measuredRepositories?w.metrics.lines:null),num(w.usage?.total_tokens)];
    })));
    container.append(section('Code snapshots counted across projects','Each identity and commit counts once. Different commits remain separate; expand aliases to open their project.'));
    codeSnapshotTable(container,data.codeSnapshots||[]);
    container.append(section('Artifact versions across projects','Oldest first · open in its originating project'));
    paginated(container,data.artifacts,['Artifact','Project','Version','Creation / reference date'],a=>[
      button(a.name,()=>switchWorkspace(a.workspaceId,{view:'artifacts',id:a.id})),a.workspace,'v'+a.version,when(a.orderAt)]);
    container.append(section('Roadmap sources','Recorded checkboxes are not acceptance evidence'));
    container.append(table(['Project / plan','Recorded progress','Observed'],data.roadmaps.map(p=>[
      button(p.workspace+' / '+p.title,()=>switchWorkspace(p.workspaceId,{view:'roadmap'})),p.status==='unavailable'?'Unavailable':`${p.checked} / ${p.total}`,when(p.at)])));
  }).catch(error=>{if(!error.workspaceChanged)container.replaceChildren(el('p',error.message));});
}
