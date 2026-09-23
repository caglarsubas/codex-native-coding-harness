"use strict";
Object.assign(titles, {
  overview:['Session map','Follow your brain, its tasks, and what needs you next.'],
  operations:['Controls & setup','Review phase controls, authority, checkpoints and project configuration.']
});
// Presentation only: saved records never become execution or parentage authority.
const sessionMapPreferences=new Map();
const SESSION_PAGE_SIZE=4;
function sessionFresh(at,now){return Number.isFinite(at)&&at>0&&now>=at&&now-at<120;}
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
    moving:fresh&&activity.status==='running',note:activity.phase||'Coordinates the approved project scope',raw:activity};
  const tasks=[],seen=new Set();
  for(const [source,rows] of [['standard',snapshot.standard?.run?.tasks||[]],['worker',snapshot.workers||[]]]){
    for(const task of rows){
      const identity=task.threadId||source+':'+task.id;
      if(seen.has(identity))continue;seen.add(identity);
      const status=sessionTaskState(task,now);
      tasks.push({id:source+':'+task.id,kind:'task',source,title:task.title||task.packetId||'Registered task',
        threadId:task.threadId,repository:task.repository||'Repository not recorded',raw:task,...status,
        relation:task.archived?'Retained history':task.status==='not_created'?'Attempt closed':status.tone==='done'?'Result recorded':!task.threadId?'Creation pending':'Delegates scope'});
    }
  }
  const groups={all:tasks.length,open:0,attention:0,history:0};tasks.forEach(t=>groups[t.group]++);
  return {brain,tasks,groups};
}
function sessionVisibleTasks(model,prefs){
  const query=prefs.query.trim().toLocaleLowerCase();
  return model.tasks.filter(n=>(prefs.filter==='all'||n.group===prefs.filter)&&(!query||[n.title,n.repository,n.threadId||'',n.label].join(' ').toLocaleLowerCase().includes(query)));
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
  card.setAttribute('aria-label',(node.kind==='brain'?'Brain: ':'Task: ')+node.title+'. '+node.label);
  const heading=el('span',null,'session-node-heading');heading.append(sessionIcon(node.kind),el('span',node.kind==='brain'?'PROJECT BRAIN':node.repository,'session-node-role'));
  card.append(heading,el('strong',node.title,'session-node-title'),sessionStatus(node));return card;
}
function sessionMap(root){
  const key=workspaceId||'legacy';
  let prefs=sessionMapPreferences.get(key);
  if(!prefs){prefs={selected:'brain',edge:false,tab:'summary',filter:'all',query:'',page:0,layout:'graph'};sessionMapPreferences.set(key,prefs);}
  const model=sessionGraphModel(state);
  if(!connected)for(const node of [model.brain,...model.tasks]){node.moving=false;if(node.tone==='active'){node.tone='unknown';node.label='Connection lost';}}
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
  const signature=JSON.stringify([model,prefs.filter,prefs.query,prefs.page,prefs.layout,prefs.selected,prefs.edge,connected]);
  if(signature!==prefs.graphSignature){
    const board=shell.querySelector('.session-board'),focus=board.contains(document.activeElement)?document.activeElement.dataset.focus:null;
    const scroll=board.querySelector('.session-canvas-scroll')?.scrollLeft||0;
    const caret=focus==='search'?[document.activeElement.selectionStart,document.activeElement.selectionEnd]:null;
    sessionBoard(board,model,prefs);prefs.graphSignature=signature;
    if(scroll)board.querySelector('.session-canvas-scroll')?.scrollTo({left:scroll});
    if(focus){const target=[...board.querySelectorAll('[data-focus]')].find(n=>n.dataset.focus===focus);target?.focus({preventScroll:true});if(caret&&target)target.setSelectionRange(...caret);}
  }
  const node=prefs.selected==='brain'?model.brain:model.tasks.find(n=>n.id===prefs.selected);
  const detailNode=['conversation','controls'].includes(prefs.tab)?node.id:prefs.tab==='evidence'?[node.id,node.raw.seedHash,node.raw.result,node.raw.completionHash,node.raw.evidence,state.observations?.artifacts]:node;
  const detailSignature=JSON.stringify([detailNode,node.label,prefs.edge,prefs.tab,state.meta.revision,connected]);
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
function sessionBoard(root,model,prefs){
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
  search.addEventListener('input',()=>{prefs.query=search.value;prefs.page=0;render();});toolbar.append(filters,search);root.append(toolbar);
  const rows=sessionVisibleTasks(model,prefs),pages=Math.max(1,Math.ceil(rows.length/SESSION_PAGE_SIZE));prefs.page=Math.min(prefs.page,pages-1);
  const visible=rows.slice(prefs.page*SESSION_PAGE_SIZE,(prefs.page+1)*SESSION_PAGE_SIZE);
  const wrap=el('div',null,'session-canvas-scroll');wrap.tabIndex=0;wrap.setAttribute('aria-label','Session relationships; use the List view on narrow screens');wrap.dataset.focus='canvas';
  const canvas=el('div',null,'session-canvas');canvas.dataset.layout=prefs.layout;canvas.style.setProperty('--map-height',Math.max(360,visible.length*116+44)+'px');
  const brain=sessionNode(model.brain,prefs);brain.classList.add('session-brain');canvas.append(brain);
  if(visible.length){
    const height=Math.max(360,visible.length*116+44),center=height/2;
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.classList.add('session-connections');svg.setAttribute('viewBox',`0 0 820 ${height}`);svg.setAttribute('preserveAspectRatio','none');svg.setAttribute('role','group');svg.setAttribute('aria-label','Brain responsibility connections');
    visible.forEach((node,i)=>{
      const y=80+i*116,path=document.createElementNS(svg.namespaceURI,'path');
      path.setAttribute('d',`M 270 ${center} C 360 ${center}, 425 ${y}, 544 ${y}`);path.classList.add('session-connection');path.dataset.tone=node.tone;path.dataset.moving=String(node.moving);
      path.setAttribute('role','button');path.setAttribute('tabindex','0');path.setAttribute('aria-label','Relationship: '+model.brain.title+' to '+node.title);path.setAttribute('aria-controls','session-inspector');path.setAttribute('aria-pressed',String(prefs.edge&&prefs.selected===node.id));path.dataset.focus='path:'+node.id;
      path.addEventListener('click',()=>sessionPick(prefs,node.id,true));path.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();sessionPick(prefs,node.id,true);}});svg.append(path);
      const row=el('div',null,'session-task-row');row.style.setProperty('--node-y',(24+i*116)+'px');
      const edge=button(node.relation,()=>sessionPick(prefs,node.id,true),'session-edge-label');edge.dataset.focus='edge:'+node.id;edge.setAttribute('aria-label',node.relation+': '+node.title);edge.setAttribute('aria-pressed',String(prefs.edge&&prefs.selected===node.id));edge.setAttribute('aria-controls','session-inspector');
      row.append(edge,sessionNode(node,prefs));canvas.append(row);
    });canvas.prepend(svg);
  }else{
    const blank=el('div',null,'session-map-empty');blank.append(el('h3',model.tasks.length?'No matching tasks':'Your brain is the starting point'),el('p',model.tasks.length?'Try another filter or search. The brain stays visible.':'Registered tasks will branch out here as the brain records them. Select the brain to read messages or review the next phase.'));canvas.append(blank);
  }
  wrap.append(canvas);root.append(wrap);
  const foot=el('div',null,'session-map-foot'),legend=el('div',null,'session-legend');
  for(const [tone,label] of [['active','Fresh activity'],['attention','Attention'],['done','Completed'],['unknown','Unknown / stale']]){const item=el('span',label);item.dataset.tone=tone;legend.append(item);}foot.append(legend);
  if(pages>1){const paging=el('div',null,'inline-actions'),previous=button('←',()=>{prefs.page--;render();}),next=button('→',()=>{prefs.page++;render();});previous.setAttribute('aria-label','Previous tasks');next.setAttribute('aria-label','Next tasks');previous.disabled=prefs.page===0;next.disabled=prefs.page===pages-1;paging.append(previous,el('span',`${prefs.page*SESSION_PAGE_SIZE+1}–${Math.min(rows.length,(prefs.page+1)*SESSION_PAGE_SIZE)} of ${rows.length}`),next);foot.append(paging);}
  root.append(foot,el('p',(connected?'Updates every 5 seconds while visible. ':'Disconnected · showing the last saved snapshot. ')+'Connections show recorded brain responsibility, not a complete native task tree. Completed does not mean archived.','session-boundary'));
}
function sessionInspector(root,node,prefs){
  const previousFocus=root.contains(document.activeElement)?document.activeElement.dataset.focus:null;
  root.replaceChildren();
  const header=el('div',null,'session-inspector-heading'),identity=el('div');
  identity.append(el('p',prefs.edge?'SELECTED CONNECTION':node.kind==='brain'?'SELECTED BRAIN':'SELECTED TASK','eyebrow'),el('h2',prefs.edge?'Brain → '+node.title:node.title));header.append(identity,sessionStatus(node));root.append(header);
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
  if(prefs.tab==='conversation'){
    if(node.kind==='brain')conversationView(panel);
    else{panel.append(el('h3','Continue in the native task'),el('p','Full worker conversations remain in Codex. This dashboard retains task metadata, linked artifacts and results; it does not import the transcript.'));sessionNativeLink(panel,node.threadId);if(!node.threadId)panel.append(el('p','A confirmed task ID is not available. A pending creation is not a session link.','muted'));sessionTaskDocuments(panel,node);}
  }else if(prefs.tab==='metadata'){
    sessionFacts(panel,node.kind==='brain'?[
      ['Native task ID',node.threadId],['Observed at',when(node.raw.observedAt)],['Source',node.raw.source],['Last checkpoint',when(state.meta.lastReconciled)],['Recorded control',state.meta.brainControl?.phase],['Freshness',node.raw.reason]
    ]:[['Registered task ID',node.raw.id],['Native task ID',node.threadId],['Pending client ID',node.raw.clientThreadId],['Record type',node.source==='standard'?'Cooperative phase task':'Managed worker'],['Repository',node.repository],['Ledger status',node.raw.status],['Native observation',node.raw.nativeStatus||'Not observed'],['Observed at',when(node.raw.observedAt)],['Created at',when(node.raw.createdAt)],['Model requested',node.raw.model],['Effort requested',node.raw.effort],['Observed tokens (partial)',node.raw.observedTokens],['Branch',node.raw.branch],['Worktree',node.raw.worktree]]);
    if(node.kind!=='brain')panel.append(el('p','Requested model settings are not verified applied settings. Missing usage is not zero.','muted'));
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
    if(state.standard)standardPanel(panel);
    else if(state.workspace)workspacePausePanel(panel);
    else brainActivity(panel);
    panel.append(button('All controls & setup',()=>navigateView('operations')));
  }else{
    const columns=el('div',null,'session-detail-columns'),main=el('div',null,'session-detail-story'),side=el('aside',null,'session-recent');
    if(node.kind==='brain'){
      main.append(el('h3','Coordinating this project'),el('p',node.note),el('p',state.meta.brainControl?.desired==='stopped'?'The brain is stopped or stopping. Saved messages wait for explicit Resume.':state.meta.paused?'New task dispatch is paused. The brain can still plan, reconcile and retain results.':'Only approved work can be delegated. Node activity does not grant authority.','muted'));
      sessionFacts(main,[['Activity observed',when(node.raw.observedAt)],['Checkpoint retained',when(state.meta.lastReconciled)]]);
      const actions=el('div',null,'inline-actions');actions.append(button('Read & message brain',()=>{prefs.tab='conversation';prefs.inspectorSignature=null;render();}),button('Review controls',()=>{prefs.tab='controls';prefs.inspectorSignature=null;render();}));sessionNativeLink(actions,node.threadId,'Open brain in Codex');main.append(actions);
    }else{
      main.append(el('h3',prefs.edge?node.relation:'Task responsibility'),el('p',node.raw.rationale||node.raw.note||node.title));
      if(prefs.edge)main.append(el('p','The designated project brain coordinates this registered task and reviews its returned evidence. This link represents the ledger association; it does not assert an observed native parent/child relationship.','muted'));
      sessionFacts(main,[['Repository',node.repository],['Recorded outcome',node.raw.status],['Allowed paths',node.raw.paths?.join(', ')||'See the retained inheritance seed']]);
      sessionNativeLink(main,node.threadId);
      if(!node.threadId)main.append(el('p','Creation is not confirmed. Keep the existing attempt until its outcome is reconciled.','muted'));
      if(['complete','completed'].includes(node.raw.status))main.append(el('p','Completion is recorded. Native archival is a separate action and observation.','muted'));
    }
    side.append(el('h3',node.kind==='brain'?'Recent recorded activity':'Task lifecycle'));
    const timeline=el('ol',null,'session-timeline');
    const events=node.kind==='brain'?[...(state.brainActivity?.events||[])].sort((a,b)=>b.at-a.at).slice(0,4).map(e=>[e.at,e.label]):[[node.raw.createdAt,'Registered task'],[node.raw.issuedAt,'Creation issued'],[node.raw.observedAt,'Native status: '+(node.raw.nativeStatus||'unknown')],[node.raw.completedAt,'Result recorded']].filter(([at])=>at);
    events.forEach(([at,label])=>{const item=el('li');item.append(el('span',label),el('time',when(at)));timeline.append(item);});
    if(!events.length)side.append(el('p','No timestamped activity is available in this snapshot.','muted'));else side.append(timeline);
    if(node.kind==='brain')side.append(button('Decision inbox',()=>navigateView('decisions')));
    columns.append(main,side);panel.append(columns);
  }
  if(previousFocus)[...root.querySelectorAll('[data-focus]')].find(n=>n.dataset.focus===previousFocus)?.focus({preventScroll:true});
}
function sessionTaskDocuments(root,node){
  let count=0;
  for(const [id,label] of [[node.raw.seedHash,'Read inherited scope'],[node.raw.result||node.raw.completionHash,'Read result & preservation']])if(/^[a-f0-9]{64}$/.test(id||'')){missionDocument(root,id,label);count++;}
  if(!count)root.append(el('p','No retained scope or result document is linked to this task.','muted'));
}
