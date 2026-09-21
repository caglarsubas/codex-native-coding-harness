"use strict";
Object.assign(titles,{conversation:['Brain conversation','Talk to this project’s existing Codex brain. Messages and replies stay in this workspace.']});
const brainDrafts=new Map(),brainPages=new Map();
function brainMessageState(message){
  if(message.reply)return {label:'Replied',detail:'The workspace brain retained this reply.'};
  if(message.receivedAt)return {label:'Received · reply pending',detail:'The brain received your message. Its reply has not been retained yet.'};
  const n=message.notification;
  if(n?.status==='accepted')return {label:'Sent to Codex',detail:'Waiting for the brain’s receipt. If it is busy, Codex finishes its active turn first.'};
  if(n?.status==='uncertain'||n?.status==='sending')return {label:'Delivery unconfirmed',detail:'Your message is saved. Do not send a duplicate; reconcile delivery before retrying.'};
  if(n?.status==='unavailable')return {label:'Saved · notification unavailable',detail:n.detail};
  return {label:'Saved · not notified',detail:'A stopped brain does not wake for a message. Use the explicit Resume control, or check the configured bridge.'};
}
function conversationEntry(root){
  const panel=el('section',null,'brain-entry'),title=state.brainActivity?.title||'Existing Codex brain';
  panel.append(el('p','PROJECT CONTROL · '+(state.workspace?.name||'Current portfolio'),'eyebrow'),el('h2','Work with your project brain'));
  panel.append(el('p',title+' · '+state.repositories.length+' registered repositories. Ask questions, give scoped direction, and read retained replies here.','checkpoint'));
  const actions=el('div',null,'inline-actions');
  actions.append(button('Open brain conversation',()=>navigateView('conversation'), 'primary'),button('Decisions & approvals',()=>navigateView('decisions')),button('Workers & evidence',()=>navigateView('workers')));
  panel.append(actions);
  const detail=el('details');detail.append(el('summary','Linked brain & repository membership'),el('p',state.meta.brainId,'mono'));
  const list=el('ul');state.repositories.forEach(r=>list.append(el('li',r.id+' · '+r.policyProfile)));detail.append(list);panel.append(detail);root.append(panel);
}
function conversationView(root){
  const key=workspaceId||'legacy',draft=brainDrafts.get(key)||{text:'',confirmed:false,request:null};brainDrafts.set(key,draft);
  const head=el('section');head.append(el('p',(state.workspace?.name||'Current portfolio')+' · '+(state.brainActivity?.title||'Configured Codex brain'),'eyebrow'));
  head.append(el('p','This is the project brain in Codex, not the advisory inference assistant. Only platform messages and retained replies appear here; this is not a full Codex transcript.','checkpoint'));
  const actions=el('div',null,'inline-actions');actions.append(button('Decision inbox',()=>navigateView('decisions')),button('Approved queue',()=>navigateView('queue')),button('Artifact library',()=>navigateView('artifacts')));head.append(actions);root.append(head);
  const stopping=['stop_requested','checkpointing','parked'].includes(state.meta.brainControl?.phase)||['stopping','paused'].includes(state.standard?.run?.status);
  if(stopping)root.append(callout('Brain paused or stopping','Messages stay saved. Use the explicit Resume control to continue from its checkpoint; sending a message does not resume work.'));
  const history=el('section',null,'brain-history');history.setAttribute('aria-label','Workspace brain messages');history.append(el('p','Loading saved conversation…'));root.append(history);
  const form=el('form',null,'brain-composer'),label=el('label','Message your workspace brain'),input=el('textarea');input.id='brain-message';input.rows=5;input.maxLength=8000;input.required=true;input.value=draft.text;label.htmlFor=input.id;form.append(label,input);
  const checkLabel=el('label',null,'decision-confirm'),check=el('input');check.type='checkbox';check.checked=draft.confirmed;checkLabel.append(check,el('span','Send to this workspace’s existing Codex brain. Packet, phase and access approvals still use their review controls.'));form.append(checkLabel);
  const send=el('button',draft.request?'Retry same saved request':'Send to brain','primary');send.type='submit';
  const status=el('p','No secrets. Your message is retained locally and read by this Codex task. Sending may consume your existing Codex allowance.','muted');form.append(status,send);root.append(form);
  let awaiting=true;
  function validate(){send.disabled=busy||!connected||awaiting||(!draft.request&&(!input.value.trim()||!check.checked));input.disabled=!!draft.request;check.disabled=!!draft.request;}
  input.oninput=()=>{draft.text=input.value;validate();};check.onchange=()=>{draft.confirmed=check.checked;validate();};validate();
  form.onsubmit=async event=>{event.preventDefault();if(send.disabled)return;
    draft.request=draft.request||{id:crypto.randomUUID(),kind:'reconcile',expectedRevision:state.meta.revision,payload:{message:draft.text,brainId:state.meta.brainId,confirmed:true}};
    busy=true;validate();updateWorkspaceSelector();
    let sent=false;
    try{await api('/api/commands',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(draft.request)});brainDrafts.delete(key);brainPages.set(key,0);sent=true;}
    catch(error){if(error.message.includes('State changed')){draft.request=null;draft.confirmed=false;check.checked=false;}status.textContent=error.message+' Your message is preserved. An uncertain request keeps its original ID.';}
    finally{busy=false;validate();updateWorkspaceSelector();}
    if(sent){await refresh();showNotice('Message saved. Delivery, brain receipt and reply are shown separately below.');}
  };
  const page=brainPages.get(key)||0;
  api('/api/brain-conversation?page='+page).then(data=>{
    if(!history.isConnected)return;awaiting=data.pending>0;validate();history.replaceChildren();
    if(awaiting)status.textContent='A message is awaiting the brain’s reply. You can still use decisions, Pause and Resume; do not submit duplicate work.';
    history.append(section('Conversation',data.total+' saved '+(data.total===1?'message':'messages')+' · original timestamps'));
    if(!data.messages.length)history.append(empty('Start here','Ask what is happening or describe your next scoped request. The answer will appear here when the brain retains it.'));
    for(const message of data.messages){
      const article=el('article',null,'brain-exchange'),delivery=brainMessageState(message);
      article.append(el('h3','You'),el('p',when(message.createdAt),'muted'),el('p',message.message,'brain-message-text'),badge(delivery.label),el('p',delivery.detail,'muted'));
      if(message.reply){article.append(el('h3','Workspace brain'),el('p',when(message.reply.at),'muted'),el('p',message.reply.message,'brain-message-text'));
        const links=el('div',null,'inline-actions');
        for(const id of message.reply.artifactIds){const item=state.observations?.artifacts?.find(a=>a.id===id);links.append(button(item?'Read '+item.name+' · v'+item.version:'Open retained artifact',()=>navigateView('artifacts',id)));}
        for(const id of message.reply.decisionIds)links.append(button('Review decision',()=>navigateView('decisions',id)));
        article.append(links);
      }history.append(article);
    }
    const pagination=el('div',null,'pagination'),older=button('Older messages',()=>{brainPages.set(key,page+1);render();}),newer=button('Newer messages',()=>{brainPages.set(key,page-1);render();});older.disabled=!data.hasOlder;newer.disabled=page===0;pagination.append(older,el('span','Page '+(page+1)),newer);history.append(pagination);
  }).catch(error=>{if(!error.workspaceChanged&&history.isConnected)history.replaceChildren(el('p',error.message));});
}
