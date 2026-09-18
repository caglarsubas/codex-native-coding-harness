"use strict";
let workspaceId=null, workspaceGeneration=0, workspaceSwitching=false, workspaceWrites=0, workspaceList=[];
const workspaceTabs=new Map();
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
  decisionDetailsOpen.clear();observationRepo='all';observationPage=0;artifactQuery='';autoObserve=saved?.autoObserve||false;lastAutoAttempt=0;
}
async function initializeWorkspaces(){
  const data=await api('/api/workspaces');workspaceList=data.workspaces;
  if(!data.enabled)return;
  $('workspace-picker').hidden=false;
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
function allWorkspaces(root){
  const container=el('section');container.append(el('p','Loading retained workspace measurements…'));root.append(container);
  api('/api/workspaces/summary').then(data=>{
    if(!container.isConnected)return;container.replaceChildren();
    container.append(callout('Workspace scopes remain separate','This comparison does not authorize work. The assistant remains scoped to the workspace selected in the menu.'));
    const a=data.aggregate,strip=el('div',null,'summary-strip');
    for(const [value,label] of [[a.lines,'measured lines'],[a.tokens,'deduplicated tokens'],[a.managedTasks,'managed tasks'],[a.uniqueArtifactVersions,'artifact versions']]){const item=el('div');item.append(el('strong',num(value)),el('span',label));strip.append(item);}
    container.append(strip,el('p',data.method,'metric-note'));
    if(a.conflictingSessionsExcluded)container.append(el('p',`${a.conflictingSessionsExcluded} shared task summaries conflict and are excluded from aggregate tokens. Review workspace coverage.`,'metric-note'));
    container.append(table(['Workspace','Dispatch / checkpoint','Workers','Code lines','Observed tokens'],data.workspaces.map(w=>{
      const name=el('div');name.append(button(w.name,()=>switchWorkspace(w.id)));
      return [name,w.status==='unavailable'?'Unavailable':textCell(w.paused?'Paused':'Enabled',when(w.lastReconciled)),num(w.activeWorkers),num(w.metrics?.measuredRepositories?w.metrics.lines:null),num(w.usage?.total_tokens)];
    })));
    container.append(section('Artifact versions across workspaces','Oldest first · open in its originating workspace'));
    paginated(container,data.artifacts,['Artifact','Workspace','Version','Creation / reference date'],a=>[
      button(a.name,()=>switchWorkspace(a.workspaceId,{view:'artifacts',id:a.id})),a.workspace,'v'+a.version,when(a.orderAt)]);
    container.append(section('Roadmap sources','Recorded checkboxes are not acceptance evidence'));
    container.append(table(['Workspace / plan','Recorded progress','Observed'],data.roadmaps.map(p=>[
      button(p.workspace+' / '+p.title,()=>switchWorkspace(p.workspaceId,{view:'roadmap'})),p.status==='unavailable'?'Unavailable':`${p.checked} / ${p.total}`,when(p.at)])));
  }).catch(error=>{if(!error.workspaceChanged)container.replaceChildren(el('p',error.message));});
}
