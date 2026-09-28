"use strict";
// The only automatic request here is a read of the signed preparation preview.
// No polling callback confirms a control or sends a message to the brain.
const developmentHelpViews=new Map();
function developmentHelpProgress(command,current,now=Date.now()/1000){
  if(command.kind==='standard_recovery'){
    const target=current.commands?.find(c=>c.id===command.payload?.messageId),n=command.notification;
    const info=commandPresentation(command,current.brainActivity,now),reply=target?.conversationReply;
    const receiveBy=current.standard?.run?.recovery?.id===command.id?current.standard.run.recovery.receiveBy:null;
    const expired=!command.receivedAt&&!reply&&receiveBy!=null&&now>=receiveBy;
    const rows=[['Recovery request saved','done',command.createdAt],
      ['Native notification',n?.status==='accepted'?'done':n?.status==='unavailable'||n?.status==='uncertain'?'attention':'waiting',n?.finishedAt],
      ['Brain received recovery scope',command.receivedAt?'done':expired?'attention':'waiting',command.receivedAt],
      ['Preparation reply saved',reply?'done':'waiting',reply?.at]];
    return {rows,title:reply?'Recovery reply received':expired?'Recovery receipt window expired':command.receivedAt?'Brain preparing your next step':info.label,
      detail:reply?'Review the saved result. Phase Resume and Play remain separate.':expired?'No brain receipt was saved within the reviewed window. Inspect the existing Codex turn and host binding; do not send another wake.':info.detail,
      attention:expired||n?.status==='unavailable'||n?.status==='uncertain'||/overdue|attention/i.test(info.label)};
  }
  const n=command.notification,reply=command.conversationReply;
  const received=!!command.conversationReceivedAt, message=command.kind==='reconcile'&&!!command.payload?.message;
  let info=commandPresentation(command,current.brainActivity,now);
  if(received&&!reply&&now-command.conversationReceivedAt>300)info={label:'Preparation reply overdue',detail:'The brain recorded receipt, but no preparation reply is saved yet. Inspect its existing turn or native approval prompt. This is not proof of active work.'};
  const attention=/unavailable|unconfirmed|overdue|missing|attention|stopped|resumes/i.test(info.label);
  const rows=[['Request saved','done',command.createdAt],
    ['Notification '+(n?.status==='accepted'?'accepted':n?.status==='unavailable'?'unavailable':'delivery'),n?.status==='accepted'?'done':received||reply?'unverified':attention?'attention':'waiting',n?.finishedAt],
    [message?'Brain received this request':'Control received',received||(!message&&command.status==='completed')?'done':'waiting',command.conversationReceivedAt||command.completedAt]];
  if(message)rows.push(['Preparation reply saved',reply?'done':'waiting',reply?.at]);
  return {rows,title:reply?'Preparation reply received':attention?'Your request needs attention':received?'Brain received your request':info.label,detail:info.detail,attention};
}
function developmentHelpKey(){
  return JSON.stringify([workspaceId,typeof workspaceGeneration==='number'?workspaceGeneration:0,csrf,state?.meta?.revision,state?.standard?.contextHash]);
}
function developmentHelpUpdate(force=false){
  const root=$('assistant-next-step');
  if(!root||!state?.workspace||!state?.standard||!state.repositories?.length||state.repositories.some(r=>r.policyProfile!=='standard'))return false;
  if(!connected){root.replaceChildren(el('p','Reconnect to check preparation progress. Saved requests are not resent.'));return true;}
  const wid=workspaceId,key=developmentHelpKey(),old=developmentHelpViews.get(wid);
  // Preserve a possibly committed request and its exact ID until its receipt is
  // inspected. Never replace it with another signed preparation request.
  if(old?.action?.uncertain||old?.action?.sending){
    if(old.key!==key&&state.commands?.some(c=>c.id===old.action.proposal.document.id))old.key=null;
    else{if(!root.contains(old.action.element))root.replaceChildren(old.action.element);return true;}
  }
  if(old?.key===key&&!force){
    for(const b of old.buttons||[])b.disabled=assistantPending;
    if(old.action&&!old.action.receipt&&!old.action.uncertain&&Date.now()/1000>old.action.proposal.document.expiresAt)return developmentHelpUpdate(true);
    if(old.data&&(!root.contains(old.panel)||old.clock!==Math.floor(Date.now()/30000)))developmentHelpRender(root,old);
    return true;
  }
  const entry={key,workspace:wid,loading:true,draft:old?.draft||''};developmentHelpViews.set(wid,entry);
  root.replaceChildren(el('p','Checking this project’s next step…','muted'));
  api('/api/assistant/help').then(data=>{
    if(workspaceId!==wid||developmentHelpViews.get(wid)!==entry)return;
    entry.data=data;entry.loading=false;developmentHelpRender(root,entry);
  }).catch(error=>{
    if(error.workspaceChanged||workspaceId!==wid||developmentHelpViews.get(wid)!==entry)return;
    entry.loading=false;root.replaceChildren(el('p','Could not prepare help. No new request was sent.','muted'),el('p',error.message),button('Check again',()=>developmentHelpUpdate(true)));
  });
  return true;
}
function developmentHelpRender(root,entry){
  const data=entry.data,panel=entry.panel||el('section',null,'development-help');
  // Keep disclosures and the button stable while only the delivery clock ages.
  if(entry.panel&&root.contains(panel)){
    if(entry.progress){const c=state.commands?.find(c=>c.id===data.requestId);if(c)developmentHelpRenderProgress(entry.progress,c);}
    entry.clock=Math.floor(Date.now()/30000);return;
  }
  entry.panel=panel;entry.clock=Math.floor(Date.now()/30000);panel.replaceChildren();
  panel.setAttribute('aria-label','Guided development help');
  const command=state.commands?.find(c=>c.id===data.requestId);
  if(command){
    const paired=command.kind==='standard_recovery'?state.commands?.find(c=>c.id===command.payload?.messageId):command;
    entry.progress=el('div',null,'development-progress');
    if(paired?.conversationReply){const details=el('details');details.append(el('summary','Details · preparation progress'),entry.progress);panel.append(details);}
    else panel.append(entry.progress);
    developmentHelpRenderProgress(entry.progress,command);
    if(paired?.conversationReply)panel.append(narrative(paired.conversationReply.message,'Preparation result · '+when(paired.conversationReply.at)));
  }
  if(data.proposal){
    // This is a displayed signed preview; its Help button is the owner's direct
    // confirmation of preparation only. Review/Play are never auto-confirmed.
    for(const [id,a] of assistantActions)if(a.guided&&a.workspace===workspaceId&&!a.sending&&!a.uncertain&&!a.receipt)assistantActions.delete(id);
    entry.action=assistantWorkflowPreview(panel,data.proposal,true);
    if(Date.now()/1000>data.proposal.document.expiresAt)panel.append(button('Refresh help preview',()=>developmentHelpUpdate(true)));
  }else{
    const next=el('div',null,'development-next');next.append(el('h3',data.title),el('p',data.detail,'muted'));
    if(data.mode==='decision'&&data.key){const b=button('Review next step',()=>assistantRequestStep(data.key),'primary');b.disabled=assistantPending;entry.buttons=[b];next.append(b);panel.prepend(next);}
    else if(data.mode!=='follow')panel.append(next);
    else if(!command)panel.append(el('p','Your request is recorded. Refreshing its saved progress…','muted'));
    if(data.mode==='needs_input'){
      const label=el('label','Missing evidence or your decision'),input=el('textarea');input.id='help-evidence';input.maxLength=2000;input.rows=2;
      input.value=entry.draft;
      label.setAttribute('for',input.id);input.placeholder='For example, the confirmed task link. No prompt needed.';
      const send=button('Prepare follow-up',()=>{
        if(!input.value.trim()||assistantPending)return;
        const text='Follow up the existing guided preparation request '+data.requestId+'. Inspect the latest ledger and this owner-supplied reference: '+input.value.trim()+'. Reconcile only existing work within current authority. Preserve ownership and usage; no worker retry, changed limits, Play or Resume. Retain the result and exact next decision in this conversation.';
        assistantRequestStep('brain_message',text);
      });send.disabled=!input.value.trim();input.addEventListener('input',()=>{entry.draft=input.value;send.disabled=!input.value.trim()||assistantPending;});
      panel.append(label,input,send);
      const retry=el('details');retry.append(el('summary','Other options'),button('Review another bounded check',()=>assistantRequestStep('phase_help')));panel.append(retry);
    }
    if(data.mode==='blocked')panel.append(button('Inspect saved controls',()=>navigateView('operations')));
  }
  if(state.recovery)panel.append(journeyDisclosure('help-blockers','Details · remaining conditions',body=>recoverySummary(body,state.recovery)));
  root.replaceChildren(panel);
}
function developmentHelpRenderProgress(root,command){
  const progress=developmentHelpProgress(command,state);
  const signature=JSON.stringify(progress);if(root.dataset.progress===signature)return;
  root.dataset.progress=signature;root.replaceChildren(el('p','PREPARATION PROGRESS','eyebrow'));
  const status=el('p',progress.title);status.setAttribute('role','status');root.append(status);
  const list=el('ol',null,'development-progress-steps');
  for(const [label,status,at] of progress.rows){const li=el('li');li.dataset.status=status;
    li.append(el('span',status==='done'?'Recorded':status==='attention'?'Needs attention':status==='unverified'?'Not verified':'Waiting','progress-state'),el('span',label));
    if(at)li.append(el('small',when(at),'muted'));list.append(li);
  }
  root.append(list,el('p',progress.detail,'muted'));
  if(progress.attention){
    root.append(el('p','We kept the original request. No duplicate or automatic retry was sent.','muted'));
    const id=state.meta?.brainId;
    if(typeof id==='string'&&/^[0-9a-f-]{36}$/i.test(id)){const link=el('a','Open existing brain for native attention ↗');link.href='codex://threads/'+id;root.append(link);}
  }
}
function developmentHelpStart(){
  if(!connected||assistantPending)return;
  focusAssistantConversation();
  const entry=developmentHelpViews.get(workspaceId);
  if(!entry||entry.key!==developmentHelpKey()){developmentHelpUpdate(true);return;}
  if(entry.action&&!assistantWorkflowState(entry.action).locked){entry.action.submit();return;}
  if(entry.data?.mode==='decision'){assistantRequestStep(entry.data.key);return;}
  assistantStatus(entry.data?.detail||'The preparation scope is shown above. Use its Help button when ready.');
}
