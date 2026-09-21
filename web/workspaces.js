"use strict";
let workspaceId=null, workspaceGeneration=0, workspaceSwitching=false, workspaceWrites=0, workspaceList=[];
const workspaceTabs=new Map();
let codeSnapshotPage=0;
const codeDetailsOpen=new Set();
Object.assign(titles,{workspaces:['All workspaces','Recorded measurements across separate development lifecycles.']});
function workspacePath(path,id=workspaceId){
  return id&&path.startsWith('/api/')&&!path.startsWith('/api/workspaces')&&path!=='/api/login'
    ?'/api/workspaces/'+encodeURIComponent(id)+path.slice(4):path;
}
function workspaceHref(target,id=null,wid=workspaceId){return '#/'+(wid?'w/'+wid+'/':'')+target+(id?'/'+id:'');}
function workspaceLocked(){return busy||workspaceWrites>0||workspaceSwitching||assistantPending||[...assistantActions.values()].some(a=>a.sending);}
function updateWorkspaceSelector(){const select=$('workspace-select');if(select)select.disabled=workspaceLocked();}
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
  $('assistant-usage').textContent=saved?.usage||'Chat is private to this workspace and tab. Actions require confirmation.';
  decisionDetailsOpen.clear();codeDetailsOpen.clear();observationRepo='all';observationPage=0;codeSnapshotPage=0;artifactQuery='';autoObserve=saved?.autoObserve||false;lastAutoAttempt=0;
}
async function initializeWorkspaces(){
  const data=await api('/api/workspaces');workspaceList=data.workspaces;
  if(!data.enabled)return;
  $('workspace-picker').hidden=false;
  $('mission-nav').hidden=false;
  $('run-readiness-nav').hidden=false;
  $('phase-checkpoints-nav').hidden=false;
  $('retention-nav').hidden=false;
  if(!workspaceList.length)throw new Error('No registered workspaces are available.');
  const select=$('workspace-select');select.replaceChildren();
  select.onchange=()=>switchWorkspace(select.value);
  for(const w of workspaceList){const option=el('option',w.name);option.value=w.id;select.append(option);}
  const route=dashboardRoute(location.hash);
  let remembered=null;try{remembered=sessionStorage.getItem('orchestrator-workspace');}catch{}
  const id=route?.workspaceId||(workspaceList.some(w=>w.id===remembered)?remembered:workspaceList[0].id);
  if(!workspaceList.some(w=>w.id===id))throw new Error('This workspace link is not registered. Select a workspace from the menu.');
  await selectWorkspaceIdentity(id);
}
async function selectWorkspaceIdentity(id){
  workspaceId=id;workspaceGeneration++;csrf=null;state=null;connected=false;selected=null;view='overview';
  $('workspace-select').value=id;$('notice').hidden=true;
  $('mode').textContent='Connecting to '+workspaceList.find(w=>w.id===id).name+'…';
  $('content').replaceChildren(empty('Opening workspace','Loading only this workspace’s recorded state.'));
  $('export-report').href=workspacePath('/api/export');
  $('assistant-workspace').textContent=workspaceList.find(w=>w.id===id).name;
  assistantConnectionChanged();
  csrf=(await api('/api/session')).csrf;
  try{sessionStorage.setItem('orchestrator-workspace',id);}catch{}
}
async function switchWorkspace(id,route=null){
  if(workspaceLocked()){showNotice('Wait for the in-flight request before switching workspaces. Nothing has been moved or cancelled.',true);$('workspace-select').value=workspaceId;return false;}
  if(!workspaceList.some(w=>w.id===id)){showNotice('Unknown workspace. No data was opened.',true);return false;}
  workspaceSwitching=true;updateWorkspaceSelector();saveWorkspaceTab();
  try{
    restoreWorkspaceTab(id);await selectWorkspaceIdentity(id);await refresh();
    if(!connected)return false;
    navigateView(route?.view||'overview',route?.id||null,true);
    return true;
  }catch(error){showNotice(error.message,true);return false;}
  finally{workspaceSwitching=false;updateWorkspaceSelector();}
}
function projectIntroduction(root){
  const workspace=state.workspace;if(!workspace)return;
  const record=workspace.projectProfile,profile=record?.profile;
  const panel=el('section',null,'project-introduction');
  panel.append(el('p','SELECTED WORKSPACE · '+workspace.name,'eyebrow'),el('h2',profile?.goal||'Introduce this project'));
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
  if(coverage.excludedRows)root.append(callout('Some code measurements are excluded','Old records without identity evidence, changed repository settings and conflicting measurements cannot be counted safely. Open the affected workspace’s Portfolio metrics and refresh observations. Missing values are not zero.'));
  if(coverage.issues?.length){
    const details=el('details'),list=el('ul');details.append(el('summary',`Excluded measurements · ${coverage.issues.length} ${coverage.issues.length===1?'entry':'entries'}`));
    for(const issue of coverage.issues.slice(0,40)){
      const item=el('li'),label=issue.repository+' · '+codeCountingLabel({status:'excluded',issues:issue.codes});
      item.append(workspaceLinks?button(issue.workspaceId+' / '+label,()=>switchWorkspace(issue.workspaceId,{view:'metrics'})):el('span',label));list.append(item);
    }
    details.append(list);if(coverage.issues.length>40)details.append(el('p','Showing the first 40 exclusions. Open individual workspaces for their full repository distribution.','metric-note'));rememberCodeDetails(details,'exclusions/'+(workspaceLinks?'all':workspaceId));root.append(details);
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
  const container=el('section');container.append(el('p','Loading retained workspace measurements…'));root.append(container);
  api('/api/workspaces/summary').then(data=>{
    if(!container.isConnected)return;container.replaceChildren();
    container.append(callout('Workspace scopes remain separate','This comparison does not authorize work. The assistant remains scoped to the workspace selected in the menu.'));
    const a=data.aggregate,strip=el('div',null,'summary-strip');
    for(const [value,label] of [[a.lines,'counted code lines'],[a.tokens,'deduplicated tokens'],[a.managedTasks,'managed tasks'],[a.uniqueArtifactVersions,'artifact versions']]){const item=el('div');item.append(el('strong',num(value)),el('span',label));strip.append(item);}
    container.append(strip);
    if(a.cooperativeTasks)container.append(el('p',`${num(a.cooperativeCompletedTasks)} / ${num(a.cooperativeTasks)} cooperative tasks completed across current workspace phases. Historical log tokens and legacy task totals above remain separate.`,'checkpoint'));
    const method=el('details');method.append(el('summary','How totals are counted'),el('p',data.method,'metric-note'));rememberCodeDetails(method,'method');container.append(method);
    codeCountingCoverage(container,data.codeCoverage,true);
    if(a.conflictingSessionsExcluded)container.append(el('p',`${a.conflictingSessionsExcluded} shared task summaries conflict and are excluded from aggregate tokens. Review workspace coverage.`,'metric-note'));
    container.append(table(['Workspace','Dispatch / checkpoint','Workers','Code lines','Observed tokens'],data.workspaces.map(w=>{
      const name=el('div');name.append(button(w.name,()=>switchWorkspace(w.id)));
      return [name,w.status==='unavailable'?'Unavailable':textCell(w.cooperative?'Cooperative · '+w.cooperative.status:w.paused?'Paused':'Enabled',when(w.lastReconciled)),num(w.cooperative?w.cooperative.active:w.activeWorkers),num(w.metrics?.measuredRepositories?w.metrics.lines:null),num(w.usage?.total_tokens)];
    })));
    container.append(section('Code snapshots counted across workspaces','Each identity and commit counts once. Different commits remain separate; expand aliases to open their workspace.'));
    codeSnapshotTable(container,data.codeSnapshots||[]);
    container.append(section('Artifact versions across workspaces','Oldest first · open in its originating workspace'));
    paginated(container,data.artifacts,['Artifact','Workspace','Version','Creation / reference date'],a=>[
      button(a.name,()=>switchWorkspace(a.workspaceId,{view:'artifacts',id:a.id})),a.workspace,'v'+a.version,when(a.orderAt)]);
    container.append(section('Roadmap sources','Recorded checkboxes are not acceptance evidence'));
    container.append(table(['Workspace / plan','Recorded progress','Observed'],data.roadmaps.map(p=>[
      button(p.workspace+' / '+p.title,()=>switchWorkspace(p.workspaceId,{view:'roadmap'})),p.status==='unavailable'?'Unavailable':`${p.checked} / ${p.total}`,when(p.at)])));
  }).catch(error=>{if(!error.workspaceChanged)container.replaceChildren(el('p',error.message));});
}
