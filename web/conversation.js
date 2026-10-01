"use strict";
Object.assign(titles,{conversation:['Brain conversation','Talk to this project’s existing Codex brain. Messages and replies stay in this project.']});
const brainDrafts=new Map(),brainPages=new Map();
const brainRequestFocus=new Map();
const nativePermissionPreviews=new Map();
function nativePermissionPanel(root){
  const panel=el('section',null,'brain-exchange native-permission');root.append(panel);
  const key=workspaceId||'legacy',generation=typeof workspaceGeneration==='undefined'?0:workspaceGeneration;
  const same=()=>panel.isConnected&&generation===(typeof workspaceGeneration==='undefined'?0:workspaceGeneration)&&key===(workspaceId||'legacy');
  let shown=null;
  function post(path,body){return api(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});}
  function paint(value,force=false){
    if(!same())return;
    const signature=value.status==='pending'?'pending:'+value.pending.requestHash+':'+(value.pending.canAccept?'accept':'no-accept'):value.status+':'+(value.delivery||'');
    if(!force&&signature===shown)return;
    shown=signature;
    panel.replaceChildren();
    if(value.status!=='pending'){
      nativePermissionPreviews.delete(key);
      if(value.status!=='disabled'&&value.detail&&value.detail!=='No current native permission request; inspect the brain before retrying')
        panel.append(el('p',(value.status==='response_claimed'?'Native permission · '+value.delivery+': ':'Native approval unavailable: ')+value.detail,'muted'));
      return;
    }
    const pending=value.pending,preview=nativePermissionPreviews.get(key);
    if(preview&&(preview.document?.requestHash!==pending.requestHash||preview.document?.decision==='accept'&&!pending.canAccept))nativePermissionPreviews.delete(key);
    const current=nativePermissionPreviews.get(key);
    panel.append(el('p','NATIVE CODEX PERMISSION · EXACT OWNER REVIEW','eyebrow'),el('h3','The brain is waiting for a native permission decision'),
      el('p','This is a Codex security prompt, not phase or task approval. No permission is granted automatically.','checkpoint'));
    const facts=el('ul');
    facts.append(el('li','Type: '+pending.method),el('li','Observed: '+when(pending.observedAt)),
      el('li','Expires: '+when(pending.expiresAt)),el('li','Approval available here: '+(pending.canAccept?'yes, after exact review':'no; decline or inspect in Codex')));
    panel.append(facts);
    const details=el('details'),exact=el('pre',JSON.stringify({request:pending.request,item:pending.item||null},null,2),'brain-message-text');
    details.open=true;details.append(el('summary','Exact native request and item context'),exact);panel.append(details);
    const actions=el('div',null,'inline-actions');
    for(const [decision,label] of [['accept','Approve this request once'],['decline','Decline'],['cancel','Cancel']]){
      if(!pending.allowedDecisions?.includes(decision)||decision==='accept'&&!pending.canAccept)continue;
      const b=button(label,async()=>{
        b.disabled=true;
        try{const proposal=await post('/api/native-permission/preview',{commandId:pending.commandId,requestHash:pending.requestHash,decision});
          if(!same())return;nativePermissionPreviews.set(key,proposal);paint(value,true);
        }catch(error){if(same())showNotice('Native permission preview failed: '+error.message,true);}
        finally{b.disabled=false;}
      });actions.append(b);
    }
    panel.append(actions);
    if(current){
      const p=current.document;
      const review=el('div',null,'brain-exchange');review.append(el('h4','Confirm one native response: '+p.decision),
        el('p',p.boundary,'checkpoint'),el('p','This preview is bound to the current brain, turn, request and browser session. It expires '+when(p.expiresAt)+'.','muted'));
      const checkLabel=el('label',null,'decision-confirm'),check=el('input');check.type='checkbox';
      checkLabel.append(check,el('span','I reviewed the exact native request above and confirm this one response.'));review.append(checkLabel);
      const confirm=button('Confirm '+p.decision,async()=>{
        if(!check.checked)return;
        confirm.disabled=true;
        try{const result=await post('/api/native-permission/confirm',{proposal:current,confirmed:true});
          if(!same())return;nativePermissionPreviews.delete(key);showNotice(result.detail||'Native permission response claimed.');
          const refreshed=await api('/api/native-permission');if(same())paint(refreshed,true);await refresh();
        }catch(error){if(same())showNotice('Native permission result is uncertain or stale: '+error.message+' Inspect before any new action.',true);}
        finally{confirm.disabled=false;}
      },'primary');confirm.disabled=true;check.onchange=()=>{confirm.disabled=!check.checked;};review.append(confirm);panel.append(review);
    }
  }
  function load(){
    api('/api/native-permission').then(value=>paint(value)).catch(error=>{if(same())panel.replaceChildren(el('p','Native permission status unavailable: '+error.message,'muted'));})
      .finally(()=>{if(same()&&typeof window!=='undefined')window.setTimeout(load,5000);});
  }
  load();
}
function brainDraftStorageKey(key){return 'orchestrator-brain-draft:'+key;}
function loadBrainDraft(key){
  try{const saved=JSON.parse(sessionStorage.getItem(brainDraftStorageKey(key)));if(saved&&typeof saved.text==='string'&&saved.text.length<=8000)return {text:saved.text,confirmed:saved.confirmed===true,request:saved.request?.kind==='reconcile'&&saved.request?.id?saved.request:null};}catch{}
  return {text:'',confirmed:false,request:null};
}
function saveBrainDraft(key,draft){try{sessionStorage.setItem(brainDraftStorageKey(key),JSON.stringify(draft));}catch{}}
function clearBrainDraft(key){try{sessionStorage.removeItem(brainDraftStorageKey(key));}catch{}}
function conversationActivity(root,activity){
  if(!activity)return;
  root.append(section('Project activity','Run outcomes and next actions — separate from message replies'));
  root.append(el('p',activity.boundary,'muted'));
  if(!activity.phases.length)root.append(el('p','No retained cooperative phase outcomes yet. Native-only messages are not imported here.','muted'));
  for(const phase of activity.phases){
    const article=el('article',null,'brain-exchange');
    article.append(el('h3','Phase '+phase.phaseId+' · '+phase.status),el('p','Recorded '+when(phase.at),'muted'));
    if(phase.checkpoint)article.append(phaseNarrative(phase.checkpoint,phase.tasks));
    for(const task of phase.tasks){
      article.append(el('h4',task.title),el('p',task.repository+' · '+task.status,'muted'));
      if(task.issue)article.append(el('p',task.issue,'checkpoint'));
      if(task.evidence){
        article.append(narrative(task.evidence.summary,'Task outcome'));
        const details=el('details');details.append(el('summary','Source, tests & preservation'));
        for(const key of ['source','tests','preservation'])details.append(el('h4',key),el('p',task.evidence[key],'brain-message-text'));
        article.append(details);
      }
      for(const pr of task.pullRequests){
        // Result text is inert. Only exact public GitHub PR URLs become links.
        if(!/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/pull\/[1-9][0-9]*$/.test(pr.url))continue;
        const link=el('a','Open PR #'+pr.url.split('/').pop(),'button');link.href=pr.url;link.target='_blank';link.rel='noopener noreferrer';article.append(link);
        const known=['open','closed','merged'].includes(pr.state),label=known?pr.state:'not observed';
        article.append(el('p','GitHub state: '+label+(pr.observedAt?' · observed '+when(pr.observedAt):' · refresh GitHub status in Git & delivery'),'muted'));
        if(pr.refreshStatus==='unavailable')article.append(el('p','Latest GitHub refresh failed. Any state above is an older observation.','checkpoint'));
        const next=pr.state==='open'?'Next: review the PR and merge manually when ready.':pr.state==='merged'?'Next: verify rollout separately; merged does not mean deployed.':pr.state==='closed'?'Next: review the closed PR outcome before planning more work.':'Next: check the PR state before deciding whether to merge.';
        article.append(el('p',next,'checkpoint'));
      }
      if(task.result&&/^[a-f0-9]{64}$/.test(task.result))missionDocument(article,task.result,'Read retained task result');
    }
    root.append(article);
  }
  for(const issue of activity.issues||[])root.append(el('p',issue,'checkpoint'));
  if(activity.limited)root.append(el('p','Older phase versions are outside this bounded view; retained documents remain in Controls & setup history.','muted'));
  const actions=el('div',null,'inline-actions');actions.append(button('Git & delivery · refresh PR status',()=>navigateView('gitStatus')),button('Phase & run details',()=>navigateView('operations')));root.append(actions);
}
function sessionTaskOutcomeSummary(root,node){
  const task=node.raw,heading=el('h3','Recorded result');root.append(heading);
  if(node.source==='standard'&&['complete','completed'].includes(task.status)&&/^[a-f0-9]{64}$/.test(task.result||'')){
    const target=el('div',null,'session-task-outcome');target.append(el('p','Reading the retained task result…','muted'));root.append(target);
    const generation=workspaceGeneration,project=workspaceId;
    api('/api/documents/'+task.result).then(doc=>{
      if(!target.isConnected||generation!==workspaceGeneration||project!==workspaceId)return;
      if(doc.taskId!==task.id||doc.runId!==state.standard?.run?.id||doc.outcome!=='completed')throw new Error('Result identity did not match this registered task.');
      target.replaceChildren(narrative(doc.evidence?.summary||'A completed result is retained without a short summary.','Task outcome'));
      target.append(el('p','This is a retained task claim. Review source, tests, preservation and PR state separately.','muted'));
    }).catch(error=>{if(target.isConnected)target.replaceChildren(el('p','Result summary unavailable: '+error.message,'muted'));});
  }else if(['complete','completed'].includes(task.status)&&task.note)root.append(narrative(task.note,'Task outcome'));
  else root.append(el('p',task.result?'A result is retained; open Results & evidence for the exact record.':'No completed task result has been retained.','muted'));
}
function brainMessageState(message){
  if(message.reply)return {label:'Replied',detail:'The project brain retained this reply.'};
  const n=message.notification;
  if(message.receivedAt){
    if(n?.nativeTurnStatus==='native_attention_required')return {label:'Received · native attention reported',detail:'Codex reported a native permission or input request. Inspect the current prompt; its report is not an approval or a saved reply.'};
    if(['completed','failed','interrupted'].includes(n?.nativeTurnStatus))return {label:'Native turn ended · reply missing',detail:'The brain received your message, but this turn ended without a retained reply. Inspect the existing turn and host before reconciliation; do not send a duplicate.'};
    return {label:'Received · reply pending',detail:'The brain received your message. Its reply has not been retained yet.'};
  }
  if(n?.status==='accepted'){
    if(n.nativeTurnStatus==='native_attention_required')return {label:'Native attention required',detail:'The owned Codex host requested native approval or input; no permission was granted here.'};
    if(['completed','failed','interrupted'].includes(n.nativeTurnStatus))return {label:'Native turn ended · receipt missing',detail:'Codex ended this turn, but the project brain recorded neither a ledger receipt nor a reply. Inspect the existing turn and host binding; do not send a duplicate.'};
    if(n.nativeDelivery==='owned_turn_start')return {label:'Brain turn started',detail:'Waiting for the brain’s separate ledger receipt and retained reply.'};
    if(n.nativeDelivery==='owned_active_queue')return {label:'Queued on active brain',detail:'Waiting for its active turn and then the separate ledger receipt.'};
    return {label:'Sent to Codex',detail:'The desktop queue accepted this, but an unloaded brain might not start. Check for a ledger receipt.'};
  }
  if(n?.status==='uncertain'||n?.status==='sending')return {label:'Delivery unconfirmed',detail:'Your message is saved. Do not send a duplicate; reconcile delivery before retrying.'};
  if(n?.status==='unavailable')return {label:'Saved · notification unavailable',detail:n.detail};
  if(state?.standard?.run?.status==='paused')return {label:'Held at checkpoint',detail:'The phase is paused, so this message was not sent. Review the recovery-only preparation wake; it can reuse this request without resuming development.'};
  return {label:'Saved · not notified',detail:'The brain has not been notified. Check its recorded controls and configured bridge before another request.'};
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
  if(typeof journeyReturn==='function')journeyReturn(root,'Brain conversation');
  const key=workspaceId||'legacy',draft=brainDrafts.get(key)||loadBrainDraft(key);brainDrafts.set(key,draft);
  const head=el('section');head.append(el('p',(state.workspace?.name||'Current portfolio')+' · '+(state.brainActivity?.title||'Configured Codex brain'),'eyebrow'));
  head.append(el('p','This is the project brain in Codex, not the advisory inference assistant. Project outcomes, platform messages and retained replies appear here; this is not a full Codex transcript.','checkpoint'));
  const actions=el('div',null,'inline-actions');actions.append(button('Decision inbox',()=>navigateView('decisions')),button('Approved queue',()=>navigateView('queue')),button('Artifact library',()=>navigateView('artifacts')));head.append(actions);root.append(head);
  const stopping=['stop_requested','checkpointing','parked'].includes(state.meta.brainControl?.phase)||['stopping','paused'].includes(state.standard?.run?.status);
  if(stopping)root.append(callout('Brain paused or stopping',state.standard?.run?.status==='paused'?'Messages stay saved. If the phase has blockers, review the recovery-only preparation wake; ordinary Resume cannot bypass them.':'Messages stay saved. Sending a message does not resume the phase.'));
  nativePermissionPanel(root);
  const history=el('section',null,'brain-history');history.setAttribute('aria-label','Project brain messages');history.append(el('p','Loading saved conversation…'));root.append(history);
  const form=el('form',null,'brain-composer'),label=el('label','Message your project brain'),input=el('textarea');input.id='brain-message';input.setAttribute('data-focus','brain-message');input.rows=5;input.maxLength=8000;input.required=true;input.value=draft.text;label.htmlFor=input.id;form.append(label,input);
  const checkLabel=el('label',null,'decision-confirm'),check=el('input');check.type='checkbox';check.checked=draft.confirmed;checkLabel.append(check,el('span','Send to this project’s existing Codex brain. Packet, phase and access approvals still use their review controls.'));form.append(checkLabel);
  const send=el('button',draft.request?'Retry same saved request':'Send to brain','primary');send.type='submit';
  const status=el('p','No secrets. Your message is retained locally and read by this Codex task. Sending may consume your existing Codex allowance.','muted');form.append(status,send);root.append(form);
  let awaiting=true;
  function validate(){send.disabled=busy||!connected||awaiting||(!draft.request&&(!input.value.trim()||!check.checked));input.disabled=!!draft.request;check.disabled=!!draft.request;}
  input.oninput=()=>{draft.text=input.value;saveBrainDraft(key,draft);validate();};check.onchange=()=>{draft.confirmed=check.checked;saveBrainDraft(key,draft);validate();};validate();
  form.onsubmit=async event=>{event.preventDefault();if(send.disabled)return;
    draft.request=draft.request||{id:crypto.randomUUID(),kind:'reconcile',expectedRevision:state.meta.revision,payload:{message:draft.text,brainId:state.meta.brainId,confirmed:true}};
    saveBrainDraft(key,draft);
    busy=true;validate();updateWorkspaceSelector();
    let sent=false;
    try{await api('/api/commands',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(draft.request)});brainDrafts.delete(key);clearBrainDraft(key);brainPages.set(key,0);sent=true;}
    catch(error){if(error.message.includes('State changed')){draft.request=null;draft.confirmed=false;check.checked=false;}saveBrainDraft(key,draft);status.textContent=error.message+' Your message is preserved. An uncertain request keeps its original ID.';}
    finally{busy=false;validate();updateWorkspaceSelector();}
    if(sent){await refresh();showNotice('Message saved. Delivery, brain receipt and reply are shown separately below.');}
  };
  const page=brainPages.get(key)||0;
  api('/api/brain-conversation?page='+page).then(data=>{
    if(!history.isConnected||key!==(workspaceId||'legacy'))return;awaiting=data.pending>0;validate();history.replaceChildren();
    conversationActivity(history,data.activity);
    if(awaiting)status.textContent='A message is awaiting the brain’s reply. You can still use decisions, Pause and Resume; do not submit duplicate work.';
    history.append(section('Conversation',data.total+' saved '+(data.total===1?'message':'messages')+' · original timestamps'));
    if(!data.messages.length)history.append(empty('Start here','Ask what is happening or describe your next scoped request. The answer will appear here when the brain retains it.'));
    let requestTarget=null;
    for(const message of data.messages){
      const article=el('article',null,'brain-exchange'),delivery=brainMessageState(message);
      if(brainRequestFocus.get(key)===message.id){
        article.setAttribute('tabindex','-1');article.setAttribute('data-focus','saved-request:'+message.id);requestTarget=article;
      }
      article.append(el('h3','You'),el('p',when(message.createdAt),'muted'),narrative(message.message,'Your message'),badge(delivery.label),el('p',delivery.detail,'muted'));
      if(message.reply){article.append(el('h3','Project brain'),el('p',when(message.reply.at),'muted'),narrative(message.reply.message,'Brain reply'));
        const links=el('div',null,'inline-actions');
        for(const id of message.reply.artifactIds){const item=state.observations?.artifacts?.find(a=>a.id===id);links.append(button(item?'Read '+item.name+' · v'+item.version:'Open retained artifact',()=>navigateView('artifacts',id)));}
        for(const id of message.reply.decisionIds)links.append(button('Review decision',()=>navigateView('decisions',id)));
        article.append(links);
      }history.append(article);
    }
    const pagination=el('div',null,'pagination'),older=button('Older messages',()=>{brainPages.set(key,page+1);render();}),newer=button('Newer messages',()=>{brainPages.set(key,page-1);render();});older.disabled=!data.hasOlder;newer.disabled=page===0;pagination.append(older,el('span','Page '+(page+1)),newer);history.append(pagination);
    if(requestTarget){brainRequestFocus.delete(key);requestTarget.scrollIntoView?.({block:'nearest'});requestTarget.focus?.({preventScroll:true});}
  }).catch(error=>{if(!error.workspaceChanged&&history.isConnected)history.replaceChildren(el('p',error.message));});
}
