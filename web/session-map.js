"use strict";
Object.assign(titles, {
  overview:['Session map','Follow your brain, its tasks, and what needs you next.'],
  operations:['Advanced controls','Inspect saved history, brain recovery and local setup.']
});
// Presentation only: saved records never become execution or parentage authority.
const sessionMapPreferences=new Map();
const SESSION_PAGE_SIZE=4;
const SESSION_FILTERS={repository:'all',commit:'all',pr:'all',ci:'all',roadmap:'all',activity:'all',from:'',through:'',sort:'recorded'};
const SESSION_COMMIT_LABELS={recorded:'Commit recorded',matches_remote:'Matches remote tip',differs_remote:'Differs from remote tip',unknown:'Unknown'};
const SESSION_PR_LABELS={draft:'Draft',open:'Open',merged:'Merged',closed:'Closed',linked:'Linked · status unknown',unknown:'Unknown'};
const SESSION_CI_LABELS={verified:'Verified evidence',failed:'Failed evidence',not_applicable:'Not applicable',unverified:'Unverified / not recorded'};
function sessionTimestamp(value){return typeof value==='number'&&Number.isFinite(value)&&value>0?value:null;}
function sessionDelivery(task,snapshot,source,now){
  const git=(snapshot.observations?.git||[]).find(r=>r.repository===task.repository);
  const local=git?.status==='measured'?git:null;
  const worktree=task.worktree?local?.worktrees?.find(w=>w.path===task.worktree):null;
  const branch=task.branch||worktree?.branch||null;
  const branchRecord=branch?local?.branches?.find(b=>b.branch===branch):null;
  const sha=value=>typeof value==='string'&&/^[a-f0-9]{40}$/i.test(value)?value:null;
  const commit=sha(task.commit)||sha(worktree?.commit)||sha(branchRecord?.commit);
  // A failed refresh must not silently recover an older successful observation.
  const remote=git?.remoteStatus==='observed'?git:git?.remoteStatus==='not_requested'&&git.previousRemote?.remoteStatus==='observed'?git.previousRemote:null;
  const observed=sessionTimestamp(remote?.remoteAt),remoteAt=observed!==null&&observed<=now?observed:null;
  const pulls=remoteAt?(remote.pullRequests||[]).filter(p=>task.pr?p.url===task.pr:commit&&(p.head===commit||p.mergeCommit===commit)):[];
  const pr=pulls.length===1?pulls[0]:null;
  const prStatus=pr&&['open','closed','merged'].includes(pr.state)?pr.state==='open'&&pr.draft?'draft':pr.state:task.pr?'linked':'unknown';
  const remoteBranch=branch?remote?.branches?.find(b=>b.branch===branch):null;
  const commitStatus=!commit?'unknown':remoteAt&&sha(remoteBranch?.remoteCommit)?remoteBranch.remoteCommit===commit?'matches_remote':'differs_remote':'recorded';
  const ci=task.evidence?.ci;
  const ciStatus=ci&&Object.hasOwn(SESSION_CI_LABELS,ci.status)&&!(ci.status==='verified'&&!ci.reference)?ci.status:'unverified';
  const roadmapId=(source==='standard'?snapshot.standard?.run?.phaseId:task.packetId)||null;
  const timestamps=['updatedAt','observedAt','finishedAt','completedAt','issuedAt','createdAt'].map(k=>sessionTimestamp(task[k])).filter(at=>at!==null&&at<=now);
  return {commit,branch,commitStatus,prStatus,prNumber:pr?.number||null,prUrl:pr?.url||task.pr||null,remoteAt,
    remoteUnavailable:git?.remoteStatus==='unavailable',ciStatus,ciReference:ci?.reference||null,roadmapId,
    roadmapKind:source==='standard'?'Phase ID':'Packet ID',lastActivity:timestamps.length?Math.max(...timestamps):null};
}
function sessionFresh(at,now){return Number.isFinite(at)&&at>0&&now>=at&&now-at<120;}
function sessionActivity(observation={},now=Date.now()/1000,task=null){
  if(task?.archived)return {kind:'archived',label:'Archived',moving:false};
  if(['complete','completed','not_created'].includes(task?.status))return {kind:'complete',label:task.status==='not_created'?'Not created':'Completed',moving:false};
  if(task&&!task.threadId)return {kind:'pending',label:'Not confirmed',moving:false};
  const at=observation.observedAt,fresh=observation.fresh!==false&&sessionFresh(at,now);
  const status=observation.status;
  const kind=fresh?['active','running'].includes(status)?'active':['idle','completed'].includes(status)?'idle':['interrupted','failed'].includes(status)?'attention':'unknown':at&&at<=now?'stale':'unknown';
  return {kind,label:{active:'Active',idle:'Idle',attention:status==='failed'?'Turn failed':'Interrupted',stale:'Stale',unknown:'Unknown'}[kind],
    moving:kind==='active',observedAt:at||null,source:observation.source||'Recorded native observation',
    reason:observation.reason||(kind==='stale'?'Last observation is over two minutes old. This does not mean inactive.':kind==='unknown'?'Current activity has not been observed.':'Recent recorded activity; not a continuous native connection.')};
}
function sessionTaskObservation(task,snapshot){
  const saved={status:task.nativeStatus,observedAt:task.observedAt,source:'Recorded native observation'};
  const telemetry=task.threadId&&snapshot.taskActivity?.[task.threadId];
  if(telemetry?.source==='unavailable')return telemetry;
  return telemetry&&(!saved.observedAt||telemetry.observedAt>=saved.observedAt)?telemetry:saved;
}
function sessionActivityIndicator(activity,edge=false){
  const badge=el('span',null,'session-activity-indicator');badge.dataset.activity=activity.kind;
  const ring=el('span',activity.kind==='complete'?'✓':activity.kind==='attention'?'!':activity.kind==='unknown'?'?':'','session-activity-ring');ring.setAttribute('aria-hidden','true');
  badge.append(ring,el('span',(edge?'Task ':'')+activity.label));
  badge.title=[activity.reason,activity.observedAt?'Observed '+when(activity.observedAt):null,edge?'Connection reflects this task’s activity, not a message transfer.':null].filter(Boolean).join(' ');
  return badge;
}
function sessionTaskState(task,now){
  if(task.archived===true)return {group:'history',label:'Archived · recorded',tone:'history',moving:false};
  if(['complete','completed'].includes(task.status))return {group:'history',label:'Completed · recorded',tone:'done',moving:false};
  if(task.status==='not_created')return {group:'history',label:'Not created',tone:'history',moving:false};
  if(['failed','blocked','held'].includes(task.status))return {group:'attention',label:task.status==='failed'?'Failed · recorded':'Needs attention',tone:'attention',moving:false};
  if(!task.threadId)return {group:'attention',label:task.clientThreadId?'Creation pending':'Task not confirmed',tone:'pending',moving:false};
  const fresh=sessionFresh(task.observedAt,now),native=task.nativeStatus;
  if(fresh&&['active','running'].includes(native))return {group:'open',label:'Working · observed',tone:'active',moving:true};
  if(fresh&&native==='idle')return {group:'open',label:'Idle · observed',tone:'idle',moving:false};
  if(fresh&&['completed','failed'].includes(native))return {group:'attention',label:native==='failed'?'Turn failed':'Awaiting result review',tone:'attention',moving:false};
  return {group:'open',label:task.observedAt?'Activity stale':'Activity unknown',tone:'unknown',moving:false};
}
function sessionGraphModel(snapshot,now=Date.now()/1000){
  const meta=snapshot.meta||{},activity=snapshot.brainActivity||{},fresh=activity.fresh===true&&sessionFresh(activity.observedAt,now);
  const brain={id:'brain',kind:'brain',title:activity.title||'Project brain',threadId:meta.brainId,
    label:fresh?activityLabel({...activity,fresh:true}):'Activity not current',tone:fresh&&activity.status==='running'?'active':'unknown',
    moving:fresh&&activity.status==='running',note:activity.phase||'Coordinates the approved project scope',raw:activity,activity:sessionActivity(activity,now)};
  const tasks=[],seen=new Set();
  for(const [source,rows] of [['standard',snapshot.standard?.run?.tasks||[]],['worker',snapshot.workers||[]]]){
    for(const task of rows){
      const identity=task.threadId||source+':'+task.id;
      if(seen.has(identity))continue;seen.add(identity);
      const observation=sessionTaskObservation(task,snapshot),status=sessionTaskState({...task,nativeStatus:observation.status,observedAt:observation.observedAt},now);
      tasks.push({id:source+':'+task.id,kind:'task',source,title:task.title||task.packetId||'Registered task',
        threadId:task.threadId,repository:task.repository||'Repository not recorded',raw:task,...status,activity:sessionActivity(observation,now,task),delivery:sessionDelivery(task,snapshot,source,now),
        relation:task.archived?'Retained history':task.status==='not_created'?'Attempt closed':status.tone==='done'?'Result recorded':!task.threadId?'Creation pending':'Delegates scope'});
    }
  }
  const groups={all:tasks.length,open:0,attention:0,history:0};tasks.forEach(t=>groups[t.group]++);
  return {brain,tasks,groups};
}
function sessionDateBoundary(value,end=false){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(value||''))return null;
  const [year,month,day]=value.split('-').map(Number),date=new Date(year,month-1,day);
  if(date.getFullYear()!==year||date.getMonth()!==month-1||date.getDate()!==day)return null;
  if(end)date.setDate(date.getDate()+1);
  return date.getTime()/1000;
}
function sessionVisibleTasks(model,prefs,now=Date.now()/1000){
  const query=(prefs.query||'').trim().toLocaleLowerCase(),f={...SESSION_FILTERS,...prefs.facets};
  const from=sessionDateBoundary(f.from),through=sessionDateBoundary(f.through,true);
  const rows=model.tasks.filter(n=>{
    const d=n.delivery;
    if(prefs.filter&&prefs.filter!=='all'&&n.group!==prefs.filter)return false;
    if(query&&![n.title,n.repository,n.raw.id,n.threadId,n.label,d.commit,d.branch,d.roadmapId,d.prNumber&&'#'+d.prNumber].filter(Boolean).join(' ').toLocaleLowerCase().includes(query))return false;
    if(f.repository!=='all'&&'repo:'+n.repository!==f.repository)return false;
    if(f.commit!=='all'&&(f.commit==='recorded'?!d.commit:d.commitStatus!==f.commit))return false;
    if(f.pr!=='all'&&d.prStatus!==f.pr)return false;
    if(f.ci!=='all'&&d.ciStatus!==f.ci)return false;
    if(f.roadmap!=='all'&&(f.roadmap==='unknown'?!!d.roadmapId:'scope:'+d.roadmapId!==f.roadmap))return false;
    const at=d.lastActivity;
    if(f.activity==='unknown')return at===null;
    if(f.activity==='custom')return at!==null&&(!f.from||from!==null&&at>=from)&&(!f.through||through!==null&&at<through);
    if(f.activity!=='all'){
      if(at===null)return false;
      const age=now-at,days={'24h':1,'7d':7,'30d':30};
      if(f.activity==='older')return age>30*86400;
      if(days[f.activity])return age>=0&&age<=days[f.activity]*86400;
    }
    return true;
  });
  if(f.sort==='newest'||f.sort==='oldest')rows.sort((a,b)=>a.delivery.lastActivity===null?b.delivery.lastActivity===null?0:1:b.delivery.lastActivity===null?-1:(a.delivery.lastActivity-b.delivery.lastActivity)*(f.sort==='newest'?-1:1));
  if(f.sort==='title')rows.sort((a,b)=>a.title.localeCompare(b.title));
  return rows;
}
function sessionIcon(type){
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');svg.classList.add('session-icon');
  const path=document.createElementNS(svg.namespaceURI,'path');
  path.setAttribute('d',type==='brain'?'M12 5c-3-4-8-1-7 3-4 1-3 7 0 8-1 4 4 6 7 3V5Zm0 0c3-4 8-1 7 3 4 1 3 7 0 8 1 4-4 6-7 3M8 8c3 0 4 2 4 4M5 16c0-3 2-4 4-4m7-4c-3 0-4 2-4 4m7 4c0-3-2-4-4-4':'M5 4h14v16H5zM8 8h8M8 12h5M8 16h3');
  svg.append(path);return svg;
}
function sessionStatus(node){const pill=el('span',node.label,'session-status');pill.dataset.tone=node.tone;return pill;}
function sessionFacts(root,rows){
  const dl=el('dl',null,'session-facts');
  rows.forEach(([label,value])=>{const row=el('div');row.append(el('dt',label),el('dd',value===null||value===undefined||value===''?'Not recorded':String(value)));dl.append(row);});root.append(dl);
}
function sessionNativeLink(root,id,label='Open full conversation in Codex'){
  if(!/^[a-zA-Z0-9_-]{1,100}$/.test(id||''))return;
  const link=el('a',label+' ↗','button');link.href='codex://threads/'+encodeURIComponent(id);root.append(link);
}
function sessionPick(prefs,id,edge=false){
  prefs.selected=id;prefs.edge=edge;prefs.tab='summary';prefs.inspectorSignature=null;render();
  const inspector=$('session-inspector');inspector?.scrollIntoView({block:'nearest',behavior:'auto'});inspector?.focus({preventScroll:true});
}
function sessionNode(node,prefs){
  const card=button('',()=>sessionPick(prefs,node.id),'session-node');
  card.dataset.node=node.id;card.dataset.focus='node:'+node.id;card.dataset.tone=node.tone;card.dataset.moving=String(node.moving);
  card.setAttribute('aria-pressed',String(prefs.selected===node.id&&!prefs.edge));card.setAttribute('aria-controls','session-inspector');
  card.setAttribute('aria-label',(node.kind==='brain'?'Brain: ':'Task: ')+node.title+'. '+node.label+'. Activity: '+node.activity.label);
  const heading=el('span',null,'session-node-heading');heading.append(sessionIcon(node.kind),el('span',node.kind==='brain'?'PROJECT BRAIN':node.repository,'session-node-role'));
  heading.append(sessionActivityIndicator(node.activity));card.dataset.activity=node.activity.kind;
  card.append(heading,el('strong',node.title,'session-node-title'),sessionStatus(node));
  if(node.kind==='task'){
    const d=node.delivery,caption=el('span',`PR ${d.prNumber?'#'+d.prNumber+' ':''}${SESSION_PR_LABELS[d.prStatus]} · CI ${SESSION_CI_LABELS[d.ciStatus]}`,'session-node-meta');caption.title=caption.textContent;card.append(caption);
  }
  return card;
}
function sessionMap(root){
  const key=workspaceId||'legacy';
  let prefs=sessionMapPreferences.get(key);
  if(!prefs){prefs={selected:'brain',edge:false,tab:'summary',filter:'all',query:'',page:0,layout:'graph',facets:{...SESSION_FILTERS},filtersOpen:false,zoom:'fit'};sessionMapPreferences.set(key,prefs);}
  const model=sessionGraphModel(state);
  if(!connected)for(const node of [model.brain,...model.tasks]){node.moving=false;node.activity={kind:'disconnected',label:'Disconnected',moving:false,reason:'Dashboard connection lost. Current activity is unknown.'};if(node.tone==='active'){node.tone='unknown';node.label='Connection lost';}}
  if(prefs.selected!=='brain'&&!model.tasks.some(n=>n.id===prefs.selected)){prefs.selected='brain';prefs.edge=false;prefs.tab='summary';}
  let shell=root.querySelector('.session-home');
  if(!shell||shell.dataset.workspace!==key){
    shell=el('div',null,'session-home');shell.dataset.workspace=key;
    shell.append(el('section',null,'session-pulse'),el('section',null,'session-board'),el('section',null,'session-inspector'));
    shell.lastElementChild.id='session-inspector';shell.lastElementChild.tabIndex=-1;shell.lastElementChild.setAttribute('aria-label','Selected session details');
    root.replaceChildren(shell);prefs.graphSignature=null;prefs.inspectorSignature=null;
  }
  sessionPulse(shell.querySelector('.session-pulse'),model);
  // Polling must not destroy focused controls, an open conversation, or a draft.
  const signature=JSON.stringify([model,prefs.filter,prefs.query,prefs.facets,sessionVisibleTasks(model,prefs).map(n=>n.id),prefs.page,prefs.layout,prefs.selected,prefs.edge,connected]);
  const board=shell.querySelector('.session-board'),controlSignature=JSON.stringify([prefs.filter,prefs.query,prefs.facets,prefs.page,prefs.layout,prefs.selected,prefs.edge]);
  const editingFilter=board.contains(document.activeElement)&&document.activeElement.matches('select,input[type=date]');
  const activitySignature=JSON.stringify([model.brain,...model.tasks].map(n=>[n.id,n.activity.kind]));
  const deferPoll=prefs.controlSignature===controlSignature&&prefs.activitySignature===activitySignature&&(editingFilter||prefs.panning);
  if(signature!==prefs.graphSignature&&!deferPoll){
    const focus=board.contains(document.activeElement)?document.activeElement.dataset.focus:null;
    const viewport=board.querySelector('.session-canvas-scroll'),scroll={left:viewport?.scrollLeft||0,top:viewport?.scrollTop||0};
    const caret=focus==='search'?[document.activeElement.selectionStart,document.activeElement.selectionEnd]:null;
    sessionBoard(board,model,prefs);prefs.graphSignature=signature;prefs.controlSignature=controlSignature;prefs.activitySignature=activitySignature;
    board.querySelector('.session-canvas-scroll')?.scrollTo(scroll);
    if(focus){const target=[...board.querySelectorAll('[data-focus]')].find(n=>n.dataset.focus===focus);target?.focus({preventScroll:true});if(caret&&target)target.setSelectionRange(...caret);}
  }
  const node=prefs.selected==='brain'?model.brain:model.tasks.find(n=>n.id===prefs.selected);
  const detailNode=['conversation','controls'].includes(prefs.tab)?node.id:prefs.tab==='evidence'?[node.id,node.raw.seedHash,node.raw.result,node.raw.completionHash,node.raw.evidence,state.observations?.artifacts]:node;
  const detailSignature=JSON.stringify([detailNode,node.label,node.activity.kind,prefs.edge,prefs.tab,state.meta.revision,connected]);
  const editingConversation=prefs.tab==='conversation'&&shell.querySelector('.session-inspector').contains(document.activeElement)&&document.activeElement.matches('input,textarea');
  if(prefs.inspectorSignature!==detailSignature&&!(prefs.inspectorSignature&&editingConversation)){
    sessionInspector(shell.querySelector('.session-inspector'),node,prefs);prefs.inspectorSignature=detailSignature;
  }
}
function sessionPulse(root,model){
  const run=state.standard?.run,open=state.workflow?.openDecisions??(state.decisions||[]).filter(d=>d.status==='open').length;
  const pending=(state.commands||[]).filter(c=>['queued','processing'].includes(c.status)).length;
  const summary=run?({running:'Phase in progress',stopping:'Reaching a safe checkpoint',paused:'Phase paused',completed:'Phase completed',blocked:'Phase needs attention'}[run.status]||'Phase status recorded'):state.meta.paused?'New task dispatch paused':'Approved dispatch enabled';
  const signature=JSON.stringify([summary,open,pending,model.groups,state.brainActivity?.observedAt,connected]);
  if(root.dataset.signature===signature)return;root.dataset.signature=signature;root.replaceChildren();
  const story=el('div',null,'session-story');story.append(el('span',state.workspace?.name||'Current project','eyebrow'),el('h2',summary),el('p',open?`${open} decision${open===1?' needs':'s need'} your input.`:model.groups.attention?`${model.groups.attention} task${model.groups.attention===1?' needs':'s need'} a closer look.`:pending?`${pending} saved request${pending===1?' is':'s are'} awaiting completion.`:'Select a session to follow its work.','muted'));
  const facts=el('div',null,'session-counts');
  [[model.tasks.length,'registered tasks'],[model.groups.history,'in history'],[open,'decisions']].forEach(([value,label])=>{const item=el('div');item.append(el('strong',num(value)),el('span',label));facts.append(item);});
  root.append(story,facts);
}
function sessionResetFilters(prefs){prefs.filter='all';prefs.query='';prefs.page=0;prefs.facets={...SESSION_FILTERS};render();}
function sessionFilterPanel(root,model,prefs){
  const f=prefs.facets,count=Object.keys(SESSION_FILTERS).filter(k=>!['sort','from','through'].includes(k)&&f[k]!==SESSION_FILTERS[k]).length;
  const details=el('details',null,'session-filter-panel');details.open=prefs.filtersOpen;
  const summary=el('summary','Filters'+(count?' · '+count+' active':''));summary.dataset.focus='filters';
  details.append(summary);details.addEventListener('toggle',()=>{if(details.isConnected)prefs.filtersOpen=details.open;});
  const fields=el('div',null,'session-filter-fields');
  const select=(key,label,choices)=>{
    const field=el('label'),input=el('select');input.dataset.focus='facet:'+key;input.setAttribute('aria-label',label);
    for(const [value,text] of choices){const option=el('option',text);option.value=value;input.append(option);}
    // Do not silently drop a selected ID when a later snapshot removes its task.
    if(!choices.some(([value])=>value===f[key])){const option=el('option',f[key].replace(/^(repo|scope):/,'')+' · no longer in snapshot');option.value=f[key];input.append(option);}
    input.value=f[key];input.addEventListener('change',()=>{f[key]=input.value;prefs.page=0;render();});
    field.append(el('span',label),input);fields.append(field);
  };
  select('repository','Repository',[['all','All repositories'],...[...new Set(model.tasks.map(n=>n.repository))].sort().map(r=>['repo:'+r,r])]);
  select('commit','Commit',[['all','Any commit status'],...Object.entries(SESSION_COMMIT_LABELS)]);
  select('pr','Pull request',[['all','Any PR status'],...Object.entries(SESSION_PR_LABELS)]);
  select('ci','CI checks / evidence',[['all','Any CI status'],...Object.entries(SESSION_CI_LABELS)]);
  const scopes=new Map();for(const n of model.tasks)if(n.delivery.roadmapId)scopes.set(n.delivery.roadmapId,n.delivery.roadmapKind);
  select('roadmap','Roadmap / scope ID',[['all','All packet & phase IDs'],...Array.from(scopes).sort(([a],[b])=>a.localeCompare(b)).map(([id,kind])=>['scope:'+id,id+' · '+kind]),['unknown','Not recorded']]);
  select('activity','Last recorded activity',[['all','Any date'],['24h','Last 24 hours'],['7d','Last 7 days'],['30d','Last 30 days'],['older','More than 30 days ago'],['custom','Date range…'],['unknown','Not recorded']]);
  if(f.activity==='custom')for(const [key,label] of [['from','From'],['through','Through']]){
    const field=el('label'),input=el('input');input.type='date';input.value=f[key];input.dataset.focus='facet:'+key;input.setAttribute('aria-label',label);
    input.addEventListener('change',()=>{f[key]=input.value;prefs.page=0;render();});field.append(el('span',label),input);fields.append(field);
  }
  select('sort','Order tasks',[['recorded','Recorded order'],['newest','Most recently active'],['oldest','Least recently active'],['title','Task title']]);
  const reset=button('Reset filters',()=>sessionResetFilters(prefs));reset.dataset.focus='reset-filters';fields.append(reset);details.append(fields);
  details.append(el('p','Filters combine. Roadmap uses recorded packet or phase IDs. CI uses retained task evidence; missing checks never count as passing. Date ranges use your local timezone.','session-filter-note'));
  if(f.activity==='custom'&&f.from&&f.through&&f.from>f.through){const warning=el('p','Choose a Through date on or after From.','session-filter-error');warning.setAttribute('role','alert');details.append(warning);}
  root.append(details);
}
function sessionZoomValue(value,width,height){
  if(value==='fit')return Math.min(1,width/Math.max(820,width),Math.min(520,height)/height);
  return Math.min(2,Math.max(.25,Number(value)||1));
}
function sessionViewport(root,wrap,canvas,prefs,height){
  const stage=el('div',null,'session-canvas-stage');stage.append(canvas);wrap.append(stage);
  const controls=el('div',null,'session-viewport-controls'),group=el('div',null,'session-zoom-controls');group.setAttribute('role','group');group.setAttribute('aria-label','Map zoom');
  let width=820,scale=1;
  const out=button('−',()=>zoom(scale-.25)),value=el('output','100%'),inside=button('+',()=>zoom(scale+.25));
  out.setAttribute('aria-label','Zoom out');inside.setAttribute('aria-label','Zoom in');value.setAttribute('aria-label','Map zoom level');value.setAttribute('aria-live','polite');
  const fit=button('Fit',()=>zoom('fit')),reset=button('100%',()=>zoom(1));fit.setAttribute('aria-label','Fit map');reset.setAttribute('aria-label','Reset zoom to 100%');
  for(const [node,key] of [[out,'out'],[inside,'in'],[fit,'fit'],[reset,'reset']])node.dataset.focus='zoom:'+key;
  group.append(out,value,inside,fit,reset);controls.append(group,el('span','Drag background to pan · Ctrl/⌘ + scroll to zoom','session-pan-hint'));root.append(controls,wrap);
  const apply=()=>{
    const available=wrap.clientWidth;if(!available)return;
    width=Math.max(820,available);scale=sessionZoomValue(prefs.zoom,available,height);
    stage.style.width=width*scale+'px';stage.style.height=height*scale+'px';
    canvas.style.width=width+'px';canvas.style.height=height+'px';canvas.style.transform=`scale(${scale})`;
    wrap.style.height=Math.max(280,Math.min(520,height*scale))+'px';
    value.textContent=Math.round(scale*100)+'%';out.disabled=scale<=.25;inside.disabled=scale>=2;
    fit.setAttribute('aria-pressed',String(prefs.zoom==='fit'));
  };
  const zoom=(next,point)=>{
    const center=point||{x:wrap.clientWidth/2,y:wrap.clientHeight/2};
    const x=(wrap.scrollLeft+center.x)/scale,y=(wrap.scrollTop+center.y)/scale;
    prefs.zoom=next==='fit'?'fit':sessionZoomValue(next,width,height);apply();
    wrap.scrollTo(next==='fit'?{left:0,top:0}:{left:x*scale-center.x,top:y*scale-center.y});
  };
  wrap.addEventListener('wheel',event=>{
    if(!event.ctrlKey&&!event.metaKey)return;
    event.preventDefault();const rect=wrap.getBoundingClientRect();zoom(scale*Math.exp(-event.deltaY*.005),{x:event.clientX-rect.left,y:event.clientY-rect.top});
  },{passive:false});
  wrap.addEventListener('keydown',event=>{
    if(event.target!==wrap)return;
    if(['+','=','-','0','f','F'].includes(event.key)){event.preventDefault();zoom(event.key==='0'?1:['f','F'].includes(event.key)?'fit':scale+(event.key==='-'?-.25:.25));}
  });
  let pan=null;
  wrap.addEventListener('pointerdown',event=>{
    if(event.button!==0||event.pointerType==='touch'||event.target.closest('button,[role=button]'))return;
    pan={id:event.pointerId,x:event.clientX,y:event.clientY,left:wrap.scrollLeft,top:wrap.scrollTop};prefs.panning=true;wrap.setPointerCapture(event.pointerId);wrap.classList.add('is-panning');event.preventDefault();wrap.focus({preventScroll:true});
  });
  wrap.addEventListener('pointermove',event=>{if(pan&&event.pointerId===pan.id)wrap.scrollTo({left:pan.left+pan.x-event.clientX,top:pan.top+pan.y-event.clientY});});
  const end=()=>{pan=null;prefs.panning=false;wrap.classList.remove('is-panning');};wrap.addEventListener('pointerup',end);wrap.addEventListener('pointercancel',end);wrap.addEventListener('lostpointercapture',end);
  const observer=new ResizeObserver(()=>{if(!wrap.isConnected){observer.disconnect();return;}apply();});prefs.resizeObserver=observer;observer.observe(wrap);apply();
}
function sessionBoard(root,model,prefs){
  prefs.resizeObserver?.disconnect();
  prefs.panning=false;
  root.replaceChildren();
  const heading=el('div',null,'session-board-heading'),intro=el('div');intro.append(el('h2','The work, connected'),el('p','Select a node or connection to explore below.'));
  const actions=el('div',null,'inline-actions');
  actions.append(button('Focus map',()=>{for(const name of ['navigation','assistant'])panePreferences.collapsed[name]=true;panePreferences.focus='workspace';savePanes();applyPanes();}));
  for(const [value,label] of [['graph','Graph'],['list','List']]){const b=button(label,()=>{prefs.layout=value;render();});b.dataset.focus='layout:'+value;b.setAttribute('aria-pressed',String(prefs.layout===value));actions.append(b);}
  heading.append(intro,actions);root.append(heading);
  const toolbar=el('div',null,'session-map-toolbar'),filters=el('div',null,'session-filters');filters.setAttribute('aria-label','Filter registered tasks');
  for(const [value,label] of [['all','All'],['open','Open'],['attention','Attention'],['history','History']]){
    const b=button(label+' '+model.groups[value],()=>{prefs.filter=value;prefs.page=0;render();});b.dataset.focus='filter:'+value;b.setAttribute('aria-pressed',String(prefs.filter===value));filters.append(b);
  }
  const search=el('input');search.type='search';search.placeholder='Find a task…';search.value=prefs.query;search.setAttribute('aria-label','Find a task by title, repository or ID');search.dataset.focus='search';
  search.addEventListener('input',()=>{prefs.query=search.value;prefs.page=0;render();});toolbar.append(filters,search);root.append(toolbar);sessionFilterPanel(root,model,prefs);
  const rows=sessionVisibleTasks(model,prefs),pages=Math.max(1,Math.ceil(rows.length/SESSION_PAGE_SIZE));prefs.page=Math.min(prefs.page,pages-1);
  const visible=rows.slice(prefs.page*SESSION_PAGE_SIZE,(prefs.page+1)*SESSION_PAGE_SIZE);
  const result=el('div',null,'session-filter-result');result.append(el('span',`${rows.length} of ${model.tasks.length} tasks match · brain always shown`));result.setAttribute('role','status');root.append(result);
  if(prefs.selected!=='brain'&&!visible.some(n=>n.id===prefs.selected))result.append(el('span','Selected task is outside this view. Its details remain below.'));
  const wrap=el('div',null,'session-canvas-scroll');wrap.tabIndex=0;wrap.setAttribute('aria-label',prefs.layout==='graph'?'Session relationships. Use plus or minus to zoom, 0 for 100%, F to fit, and arrow keys to pan.':'Session tasks');wrap.dataset.focus='canvas';
  const canvas=el('div',null,'session-canvas');canvas.dataset.layout=prefs.layout;canvas.style.setProperty('--map-height',Math.max(360,visible.length*144+44)+'px');
  const brain=sessionNode(model.brain,prefs);brain.classList.add('session-brain');canvas.append(brain);
  if(visible.length){
    const height=Math.max(360,visible.length*144+44),center=height/2;
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.classList.add('session-connections');svg.setAttribute('viewBox',`0 0 820 ${height}`);svg.setAttribute('preserveAspectRatio','none');svg.setAttribute('role','group');svg.setAttribute('aria-label','Brain responsibility connections');
    visible.forEach((node,i)=>{
      const y=84+i*144,path=document.createElementNS(svg.namespaceURI,'path');
      path.setAttribute('d',`M 270 ${center} C 360 ${center}, 425 ${y}, 544 ${y}`);path.classList.add('session-connection');path.dataset.tone=node.tone;path.dataset.activity=node.activity.kind;path.dataset.moving=String(node.activity.moving);
      path.setAttribute('role','button');path.setAttribute('tabindex','0');path.setAttribute('aria-label','Relationship: '+model.brain.title+' to '+node.title+'. Task '+node.activity.label);path.setAttribute('aria-controls','session-inspector');path.setAttribute('aria-pressed',String(prefs.edge&&prefs.selected===node.id));path.dataset.focus='path:'+node.id;
      path.addEventListener('click',()=>sessionPick(prefs,node.id,true));path.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();sessionPick(prefs,node.id,true);}});svg.append(path);
      const row=el('div',null,'session-task-row');row.style.setProperty('--node-y',(24+i*144)+'px');
      const edge=button(node.relation,()=>sessionPick(prefs,node.id,true),'session-edge-label');edge.dataset.focus='edge:'+node.id;edge.setAttribute('aria-label',node.relation+': '+node.title+'. Task '+node.activity.label);edge.setAttribute('aria-pressed',String(prefs.edge&&prefs.selected===node.id));edge.setAttribute('aria-controls','session-inspector');
      edge.append(sessionActivityIndicator(node.activity,true));edge.dataset.activity=node.activity.kind;
      row.append(edge,sessionNode(node,prefs));canvas.append(row);
    });canvas.prepend(svg);
  }else{
    const blank=el('div',null,'session-map-empty');blank.append(el('h3',model.tasks.length?'No matching tasks':'Your brain is the starting point'),el('p',model.tasks.length?'Try another filter or search. The brain stays visible.':'Registered tasks will branch out here as the brain records them. Select the brain to read messages or review the next phase.'));if(model.tasks.length)blank.append(button('Reset filters',()=>sessionResetFilters(prefs)));canvas.append(blank);
  }
  if(prefs.layout==='graph')sessionViewport(root,wrap,canvas,prefs,Math.max(360,visible.length*144+44));else{wrap.append(canvas);root.append(wrap);}
  const foot=el('div',null,'session-map-foot'),legend=el('div',null,'session-legend');
  for(const [kind,label] of [['active','Active'],['idle','Idle'],['complete','Completed'],['stale','Stale'],['unknown','Unknown']])legend.append(sessionActivityIndicator({kind,label}));foot.append(legend);
  if(pages>1){const paging=el('div',null,'inline-actions'),previous=button('←',()=>{prefs.page--;render();}),next=button('→',()=>{prefs.page++;render();});previous.setAttribute('aria-label','Previous tasks');next.setAttribute('aria-label','Next tasks');previous.disabled=prefs.page===0;next.disabled=prefs.page===pages-1;paging.append(previous,el('span',`${prefs.page*SESSION_PAGE_SIZE+1}–${Math.min(rows.length,(prefs.page+1)*SESSION_PAGE_SIZE)} of ${rows.length}`),next);foot.append(paging);}
  root.append(foot,el('p',(connected?'Activity checked every 5 seconds while visible. ':'Disconnected · showing the last saved snapshot. ')+'Spinning rings mean recently observed activity. Edge indicators follow the task; they do not show message traffic. Stale and unknown do not mean idle. Completed does not mean archived.','session-boundary'));
}
function sessionInspector(root,node,prefs){
  const previousFocus=root.contains(document.activeElement)?document.activeElement.dataset.focus:null;
  root.replaceChildren();
  const header=el('div',null,'session-inspector-heading'),identity=el('div');
  identity.append(el('p',prefs.edge?'SELECTED CONNECTION':node.kind==='brain'?'SELECTED BRAIN':'SELECTED TASK','eyebrow'),el('h2',prefs.edge?'Brain → '+node.title:node.title));header.append(identity,sessionActivityIndicator(node.activity,prefs.edge));root.append(header);
  const tabs=el('div',null,'session-detail-tabs');tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','Session detail sections');
  const tabChoices=[['summary',prefs.edge?'Responsibility':'Overview'],['conversation','Conversation'],['evidence','Evidence'],['metadata','Metadata']];
  if(node.kind==='brain')tabChoices.push(['controls','Controls']);
  const panel=el('div',null,'session-detail-content');panel.id='session-detail-panel';panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby','session-tab-'+prefs.tab);
  for(const [id,label] of tabChoices){
    const b=button(label,()=>{prefs.tab=id;prefs.inspectorSignature=null;render();document.getElementById('session-tab-'+id)?.focus({preventScroll:true});});
    b.id='session-tab-'+id;b.dataset.focus='tab:'+id;b.setAttribute('role','tab');b.setAttribute('aria-selected',String(prefs.tab===id));b.setAttribute('aria-controls',panel.id);b.tabIndex=prefs.tab===id?0:-1;
    b.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const index=tabChoices.findIndex(t=>t[0]===id),next=e.key==='Home'?0:e.key==='End'?tabChoices.length-1:(index+(e.key==='ArrowRight'?1:-1)+tabChoices.length)%tabChoices.length;prefs.tab=tabChoices[next][0];prefs.inspectorSignature=null;render();document.getElementById('session-tab-'+prefs.tab)?.focus({preventScroll:true});});tabs.append(b);
  }
  root.append(tabs,panel);
  if(['summary','metadata'].includes(prefs.tab)){
    const signal=el('div',null,'session-activity-detail');signal.append(sessionActivityIndicator(node.activity),el('span',node.activity.observedAt?'Observed '+when(node.activity.observedAt):'No current activity observation'));
    if(node.activity.reason)signal.append(el('p',node.activity.reason));panel.append(signal);
  }
  if(prefs.tab==='conversation'){
    if(node.kind==='brain')conversationView(panel);
    else{panel.append(el('h3','Continue in the native task'),el('p','Full worker conversations remain in Codex. This dashboard retains task metadata, linked artifacts and results; it does not import the transcript.'));sessionNativeLink(panel,node.threadId);if(!node.threadId)panel.append(el('p','A confirmed task ID is not available. A pending creation is not a session link.','muted'));sessionTaskDocuments(panel,node);}
  }else if(prefs.tab==='metadata'){
    sessionFacts(panel,node.kind==='brain'?[
      ['Native task ID',node.threadId],['Observed at',when(node.raw.observedAt)],['Source',node.raw.source],['Last checkpoint',when(state.meta.lastReconciled)],['Recorded control',state.meta.brainControl?.phase],['Freshness',node.raw.reason]
    ]:[['Registered task ID',node.raw.id],['Native task ID',node.threadId],['Pending client ID',node.raw.clientThreadId],['Record type',node.source==='standard'?'Cooperative phase task':'Managed worker'],['Repository',node.repository],['Ledger status',node.raw.status],['Native observation',node.raw.nativeStatus||'Not observed'],['Observed at',when(node.raw.observedAt)],['Created at',when(node.raw.createdAt)],['Model requested',node.raw.model],['Effort requested',node.raw.effort],['Observed tokens (partial)',node.raw.observedTokens],['Branch',node.raw.branch],['Worktree',node.raw.worktree]]);
    if(node.kind!=='brain'){sessionDeliveryFacts(panel,node);panel.append(el('p','Requested model settings are not verified applied settings. Missing usage is not zero.','muted'));}
  }else if(prefs.tab==='evidence'){
    if(node.kind==='task'){
      const axes=Object.entries(node.raw.evidence||{});
      if(axes.length)panel.append(table(['Evidence axis','Recorded status','Reference'],axes.map(([axis,value])=>[axis,value.status||'Not recorded',value.reference||'Not supplied'])));
      sessionTaskDocuments(panel,node);
    }
    const artifacts=(state.observations?.artifacts||[]).filter(a=>node.threadId&&a.references?.some(r=>r.session===node.threadId));
    for(const artifact of artifacts)panel.append(button(artifact.name+' · v'+artifact.version,()=>navigateView('artifacts',artifact.id)));
    if(!artifacts.length)panel.append(el('p','No session-linked artifacts in the current library.','muted'));
    panel.append(el('p','Source, tests, merge, runtime and preservation are separate evidence. A completed task does not establish all of them.','muted'));
  }else if(prefs.tab==='controls'){
    if(state.standard&&state.repositories?.length&&state.repositories.every(repo=>repo.policyProfile==='standard'))roadmapJourney(panel);
    else if(state.workspace)workspacePausePanel(panel);
    else brainActivity(panel);
    panel.append(button('Advanced controls & recovery',()=>navigateView('operations')));
  }else{
    const columns=el('div',null,'session-detail-columns'),main=el('div',null,'session-detail-story'),side=el('aside',null,'session-recent');
    if(node.kind==='brain'){
      main.append(el('h3','Coordinating this project'),narrative(node.note,'Brain update'),el('p',state.meta.brainControl?.desired==='stopped'?'The brain is stopped or stopping. Saved messages wait for explicit Resume.':state.meta.paused?'New task dispatch is paused. The brain can still plan, reconcile and retain results.':'Only approved work can be delegated. Node activity does not grant authority.','muted'));
      sessionFacts(main,[['Activity observed',when(node.raw.observedAt)],['Checkpoint retained',when(state.meta.lastReconciled)]]);
      const actions=el('div',null,'inline-actions');actions.append(button('Read & message brain',()=>{prefs.tab='conversation';prefs.inspectorSignature=null;render();}),button('Review controls',()=>{prefs.tab='controls';prefs.inspectorSignature=null;render();}));sessionNativeLink(actions,node.threadId,'Open brain in Codex');main.append(actions);
    }else{
      main.append(el('h3',prefs.edge?node.relation:'Task responsibility'),narrative(node.raw.rationale||node.raw.note||node.title,'Task responsibility'));
      if(prefs.edge)main.append(el('p','The designated project brain coordinates this registered task and reviews its returned evidence. This link represents the ledger association; it does not assert an observed native parent/child relationship.','muted'));
      sessionFacts(main,[['Repository',node.repository],['Recorded outcome',node.raw.status],['Allowed paths',node.raw.paths?.join(', ')||'See the retained inheritance seed']]);
      sessionDeliveryFacts(main,node);
      sessionNativeLink(main,node.threadId);
      if(!node.threadId)main.append(el('p','Creation is not confirmed. Keep the existing attempt until its outcome is reconciled.','muted'));
      if(['complete','completed'].includes(node.raw.status))main.append(el('p','Completion is recorded. Native archival is a separate action and observation.','muted'));
    }
    side.append(el('h3',node.kind==='brain'?'Recent recorded activity':'Task lifecycle'));
    const timeline=el('ol',null,'session-timeline');
    const events=node.kind==='brain'?[...(state.brainActivity?.events||[])].sort((a,b)=>b.at-a.at).slice(0,4).map(e=>[e.at,e.label]):[[node.raw.createdAt,'Registered task'],[node.raw.issuedAt,'Creation issued'],[node.raw.observedAt,'Native status: '+(node.raw.nativeStatus||'unknown')],[node.raw.finishedAt||node.raw.completedAt,'Result recorded']].filter(([at])=>at);
    events.forEach(([at,label])=>{const item=el('li');item.append(el('span',label),el('time',when(at)));timeline.append(item);});
    if(!events.length)side.append(el('p','No timestamped activity is available in this snapshot.','muted'));else side.append(timeline);
    if(node.kind==='brain')side.append(button('Decision inbox',()=>navigateView('decisions')));
    columns.append(main,side);panel.append(columns);
  }
  if(previousFocus)[...root.querySelectorAll('[data-focus]')].find(n=>n.dataset.focus===previousFocus)?.focus({preventScroll:true});
}
function sessionDeliveryFacts(root,node){
  const d=node.delivery;
  root.append(el('h3','Delivery & activity'));
  sessionFacts(root,[['Commit',d.commit],['Remote comparison',SESSION_COMMIT_LABELS[d.commitStatus]],
    ['Pull request',(d.prNumber?'#'+d.prNumber+' · ':'')+SESSION_PR_LABELS[d.prStatus]],['GitHub observed',d.remoteAt?when(d.remoteAt):'Not recorded'],
    ['CI checks / evidence',SESSION_CI_LABELS[d.ciStatus]],['CI reference',d.ciReference],
    [d.roadmapKind,d.roadmapId],['Last recorded activity',d.lastActivity?when(d.lastActivity):'Not recorded']]);
  root.append(el('p',d.remoteUnavailable?'Latest GitHub refresh was unavailable. Older remote status is not used for filtering.':'PR and commit status use saved observations. CI is the retained task evidence axis, not a live provider check list. Packet and phase IDs identify recorded scope; no roadmap link is inferred from titles.','muted'));
}
function sessionTaskDocuments(root,node){
  let count=0;
  for(const [id,label] of [[node.raw.seedHash,'Read inherited scope'],[node.raw.result||node.raw.completionHash,'Read result & preservation']])if(/^[a-f0-9]{64}$/.test(id||'')){missionDocument(root,id,label);count++;}
  if(!count)root.append(el('p','No retained scope or result document is linked to this task.','muted'));
}
