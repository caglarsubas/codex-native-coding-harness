"use strict";
Object.assign(titles,{conversation:['Brain conversation','Talk to this project’s existing Codex brain. Messages and replies stay in this project.']});
const brainDrafts=new Map(),brainPages=new Map();
const brainRequestFocus=new Map();
const nativePermissionPreviews=new Map();
const nativePermissionFocusRequests=new Map();
const turnRecoveryPreviews=new Map();
const receiptRecoveryPreviews=new Map();
function receiptRecoveryPanel(article,message){
  const key=workspaceId||'legacy',generation=typeof workspaceGeneration==='undefined'?0:workspaceGeneration;
  const same=()=>article.isConnected&&key===(workspaceId||'legacy')&&generation===(typeof workspaceGeneration==='undefined'?0:workspaceGeneration);
  const recovery=message.receiptRecovery;
  if(recovery&&!message.reply){
    const n=recovery.notification||{},detail=recovery.receivedAt?'Receipt-only recovery received; waiting for the saved reply.':
      n.status==='accepted'?'Recovery turn started; waiting for its separate receipt and reply.':
      ['sending','uncertain'].includes(n.status)?'Recovery delivery is unconfirmed. Do not send another wake.':
      'Recovery saved but not delivered. Inspect its host and current controls; no automatic retry.';
    article.append(el('p',detail,'checkpoint'));
    return;
  }
  if(message.reply||state.replyRecovery?.messageId!==message.id)return;
  const panel=el('section',null,'receipt-recovery');article.append(panel);
  const post=(path,body)=>api(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});
  function paint(initial=false){
    if(!initial&&!same())return;panel.replaceChildren();
    if(receiptRecoveryPreviews.get(key)?.proposal.document.command.payload.messageId!==message.id)receiptRecoveryPreviews.delete(key);
    const cached=receiptRecoveryPreviews.get(key),proposal=cached?.proposal,doc=proposal?.document;
    panel.append(el('h4','Recover the missing reply'),el('p','Check the original turn, then review one receipt-only wake. The original instruction will not be rerun.','muted'));
    if(!proposal){
      const check=button('Check missing brain reply',async()=>{
        check.disabled=true;
        try{const p=await post('/api/assistant/preview',{key:'reply_recovery'});if(!same())return;
          receiptRecoveryPreviews.set(key,{proposal:p,uncertain:false});paint();
        }catch(error){if(same())panel.append(el('p','Recovery check unavailable: '+error.message+' Nothing was sent.','checkpoint'));}
        finally{check.disabled=false;}
      });panel.append(check);return;
    }
    const list=el('ul');for(const text of doc.preview.details.summary||[])list.append(el('li',text));panel.append(list);
    const details=el('details');details.append(el('summary','Details · scope, native observation & expiry'),
      el('p',doc.preview.impact),el('p','Expires '+when(doc.expiresAt)),el('pre',JSON.stringify(doc.preview.details.turn,null,2)));panel.append(details);
    const label=el('label',null,'decision-confirm'),check=el('input');check.type='checkbox';
    label.append(check,el('span','Confirm one receipt-only wake for this original request. No original command retry or Play.'));panel.append(label);
    const confirm=button(cached.uncertain?'Recover same confirmation receipt':'Confirm receipt-only recovery',async()=>{
      if(!check.checked)return;confirm.disabled=true;
      try{await post('/api/assistant/confirm',{proposal,confirmed:true});if(!same())return;
        receiptRecoveryPreviews.delete(key);showNotice('Receipt-only recovery saved. Follow its delivery, receipt and reply.');await refresh();
      }catch(error){if(!same())return;cached.uncertain=![400,401,403,409].includes(error.status);
        if(!cached.uncertain){receiptRecoveryPreviews.delete(key);paint();}
        panel.append(el('p',error.message+(cached.uncertain?' Recover only this same confirmation receipt; do not submit another wake.':' Nothing new was sent; check current state.'),'checkpoint'));
        confirm.textContent=cached.uncertain?'Recover same confirmation receipt':'Confirm receipt-only recovery';
      }finally{confirm.disabled=!check.checked;}
    },'primary');confirm.disabled=true;check.onchange=()=>{confirm.disabled=!check.checked;};panel.append(confirm);
    if(!cached.uncertain)panel.append(button('Dismiss preview',()=>{receiptRecoveryPreviews.delete(key);paint();}));
  }
  // Build the initial controls before this article is attached to the inspector.
  // Asynchronous updates still require the exact connected workspace generation.
  paint(true);
}
// Notice polling reads only the already-retained owner request. It never
// collects native evidence, creates a preview or grants a permission.
function nativePermissionNoticePaint(panel,value){
  const visible=value.status==='pending'||value.status==='attention_required'||
    value.status==='response_claimed'&&['claimed','queued','response_written','uncertain','blocked'].includes(value.delivery);
  const signature=JSON.stringify([value.status,value.commandId,value.requestHash,value.delivery,value.detail]);
  if(panel._permissionSignature===signature)return;
  panel._permissionSignature=signature;panel.hidden=!visible;panel.replaceChildren();
  if(!visible)return;
  const copy=el('div'),waiting=value.status==='pending';
  copy.append(el('strong',waiting?'The brain needs a permission decision':'This native request needs attention'),
    el('p',waiting?'Review the Codex request here. Nothing is approved automatically.':value.detail));
  const review=button(waiting?'Review native permission':'Inspect existing request',()=>{
    nativePermissionFocusRequests.set(workspaceId||'legacy',typeof workspaceGeneration==='undefined'?0:workspaceGeneration);
    navigateView('conversation');
  });
  panel.append(copy,review);
}
function nativePermissionNotice(root){
  const key=workspaceId||'legacy',generation=typeof workspaceGeneration==='undefined'?0:workspaceGeneration;
  root.hidden=true;root.setAttribute('role','status');root.setAttribute('aria-live','polite');
  const same=()=>root.isConnected&&key===(workspaceId||'legacy')&&generation===(typeof workspaceGeneration==='undefined'?0:workspaceGeneration);
  async function load(){
    try{
      const value=await api('/api/native-permission');if(!same())return;
      // Keep only a compact, transient summary on the shell. Never copy the raw
      // prompt into project state, storage, the graph or the advisory guide.
      const summary={status:value.status,commandId:value.pending?.commandId||value.commandId,
        requestHash:value.pending?.requestHash,delivery:value.delivery,detail:value.detail};
      root._permissionSummary=summary;nativePermissionNoticePaint(root,summary);
      const mirror=root.parentElement?.querySelector('.session-inspector-permission');
      if(mirror)nativePermissionNoticePaint(mirror,summary);
    }catch(error){
      if(same()){
        const summary={status:'attention_required',detail:'Permission status could not be checked. Inspect the existing request; do not repeat Play.'};
        root._permissionSummary=summary;nativePermissionNoticePaint(root,summary);
        const mirror=root.parentElement?.querySelector('.session-inspector-permission');
        if(mirror)nativePermissionNoticePaint(mirror,summary);
      }
    }finally{if(same()&&typeof window!=='undefined')window.setTimeout(load,5000);}
  }
  load();
}
function nativePermissionPanel(root){
  const panel=el('section',null,'brain-exchange native-permission');root.append(panel);
  const key=workspaceId||'legacy',generation=typeof workspaceGeneration==='undefined'?0:workspaceGeneration;
  const same=()=>panel.isConnected&&generation===(typeof workspaceGeneration==='undefined'?0:workspaceGeneration)&&key===(workspaceId||'legacy');
  let shown=null,expiredRequest=null;
  function focusReview(){
    if(!same()||!panel.children.length||nativePermissionFocusRequests.get(key)!==generation)return;
    nativePermissionFocusRequests.delete(key);panel.setAttribute('tabindex','-1');panel.setAttribute('aria-label','Native permission review');
    panel.scrollIntoView({block:'nearest',behavior:'auto'});panel.focus({preventScroll:true});
  }
  function post(path,body){return api(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});}
  function paint(value,force=false){
    if(!same())return;
    const cached=nativePermissionPreviews.get(key),expired=!!cached&&cached.document?.expiresAt<=Date.now()/1000;
    if(expired)expiredRequest=value.pending?.requestHash||null;
    else if(cached||value.status!=='pending'||expiredRequest!==value.pending.requestHash)expiredRequest=null;
    const signature=value.status==='pending'?'pending:'+value.pending.requestHash+':'+(value.pending.canAccept?'accept':'no-accept')+':'+expiredRequest:value.status+':'+(value.delivery||'')+':'+(value.detail||'');
    if(!force&&signature===shown){focusReview();return;}
    shown=signature;
    panel.replaceChildren();
    if(expired)nativePermissionPreviews.delete(key);
    if(value.status!=='pending'){
      nativePermissionPreviews.delete(key);
      if(value.status!=='disabled'&&value.detail&&value.detail!=='No current native permission request; inspect the brain before retrying')
        panel.append(el('p',(value.status==='response_claimed'?'Native permission · '+value.delivery+': ':'Native permission: ')+value.detail,'muted'));
      if(['attention_required','turn_recovered'].includes(value.status)&&value.commandId)turnRecoveryPanel(panel,value.commandId);
      focusReview();return;
    }
    const pending=value.pending,preview=nativePermissionPreviews.get(key);
    if(preview&&(preview.document?.requestHash!==pending.requestHash||preview.document?.decision==='accept'&&!pending.canAccept))nativePermissionPreviews.delete(key);
    const current=nativePermissionPreviews.get(key);
    panel.append(el('p','NATIVE CODEX PERMISSION · EXACT OWNER REVIEW','eyebrow'),el('h3','The brain is waiting for a native permission decision'),
      el('p','This is a Codex security prompt, not phase or task approval. No permission is granted automatically.','checkpoint'));
    const facts=el('ul');
    facts.append(el('li','Type: '+pending.method),el('li','Observed: '+when(pending.observedAt)),
      el('li','Owned connection waiting until: '+when(pending.expiresAt)),el('li','Approval available here: '+(pending.canAccept?'yes, after exact review':'no; decline or inspect in Codex')));
    panel.append(facts);
    if(expiredRequest)panel.append(el('p','Your confirmation preview expired, but this native request is still waiting. Choose a response below to review it again. Nothing was sent.','checkpoint'));
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
    focusReview();
  }
  function load(){
    api('/api/native-permission').then(value=>paint(value)).catch(error=>{if(same())panel.replaceChildren(el('p','Native permission status unavailable: '+error.message,'muted'));})
      .finally(()=>{if(same()&&typeof window!=='undefined')window.setTimeout(load,5000);});
  }
  load();
}
function turnRecoveryPanel(root,commandId){
  const panel=el('section',null,'turn-recovery');root.append(panel);
  const key=workspaceId||'legacy',generation=typeof workspaceGeneration==='undefined'?0:workspaceGeneration;
  const same=()=>panel.isConnected&&key===(workspaceId||'legacy')&&generation===(typeof workspaceGeneration==='undefined'?0:workspaceGeneration);
  const post=(path,body)=>api(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});
  function paint(value){
    if(!same())return;panel.replaceChildren();
    if(value.status==='unavailable'){
      panel.append(el('p','Recovery is not available here: '+value.detail,'muted'));return;
    }
    panel.append(el('h3',value.status==='controller_recovered'?'Recovery recorded':'Recover the stranded brain turn'),el('p',value.detail));
    if(value.status==='controller_recovered'){
      turnRecoveryPreviews.delete(key);
      panel.append(button('Review safe phase checkpoint',()=>{journeyAction('pause');},'primary'));return;
    }
    if(value.status!=='review_available'){
      turnRecoveryPreviews.delete(key);
      const check=button('Check this existing turn again',async()=>{
        check.disabled=true;
        try{const result=await post('/api/turn-recovery/reconcile',{commandId:value.commandId});if(same()){paint(result);await refresh();}}
        catch(error){if(same())showNotice('Recovery check unavailable. Nothing was resent. '+error.message,true);}
        finally{check.disabled=false;}
      });panel.append(check);return;
    }
    let preview=turnRecoveryPreviews.get(key);
    if(preview?.document?.commandId!==commandId){turnRecoveryPreviews.delete(key);preview=null;}
    const expired=preview&&preview.document.expiresAt<=Date.now()/1000;
    const review=button(preview?'Refresh recovery review':'Review turn recovery',async()=>{
      review.disabled=true;
      try{const result=await post('/api/turn-recovery/preview',{commandId});if(same()){turnRecoveryPreviews.set(key,result);paint(value);}}
      catch(error){if(same())showNotice('Cannot inspect the reviewed host. Nothing was cancelled or loaded. '+error.message,true);}
      finally{review.disabled=false;}
    });panel.append(review);
    if(!preview)return;
    const doc=preview.document;
    const inspectionLoad=doc.action==='load_for_inspection_then_reconcile';
    panel.append(el('h4',inspectionLoad?'Load for inspection, without starting work':doc.action==='cancel_then_reconcile'?'Cancel this turn and check that it ended':'Check this already-ended turn'),
      el('p',doc.boundary,'checkpoint'),el('p','This review expires '+when(doc.expiresAt)+'. It does not extend the phase.','muted'));
    if(doc.hostContinuity)panel.append(el('p',inspectionLoad?
      'The replacement host has not loaded this brain. One inspection-only load enables fresh terminal checks. Unknown terminals remain unknown; acknowledgment alone cannot recover the controller. No turn or Play is started.':
      'This is an ended-turn check on a separately reviewed replacement host. No cancellation or thread loading will be sent.','checkpoint'));
    const details=el('details');details.append(el('summary','Details · Exact recovery target'),
      el('p','Project: '+doc.workspaceId),el('p','Brain: '+doc.brainId),el('p','Turn: '+doc.turnId),
      el('p','Observed: '+doc.observation.status+' · '+when(doc.observation.observedAt)));
    if(inspectionLoad)details.append(el('p','Current tracked terminals: unknown (thread not loaded). Historical terminal and effect gaps remain retained.'),
      el('p','Inspection settings: workspace-write · on-request · owner approval review · Code Mode disabled. No model, instructions or history replacement.'));
    if(doc.controllerCredential)details.append(el('p','After verified inactivity, preserve the matching abandoned controller credential in a private archive and retire its active filename. A changed or newer credential will not be replaced.'),
      el('p','Reviewed credential byte hash: '+doc.controllerCredential.sha256));
    if(doc.hostContinuity)details.append(el('p','Original host binding: '+doc.originalBindingHash),
      el('p','Reviewed replacement binding: '+doc.bindingHash),
      el('p','Brain, checkout, workspace, both project identities and restricted native policy are unchanged.'));
    const boundBrain=doc.hostContinuity?.candidateBinding?.brains?.[doc.brainId];
    if(boundBrain)details.append(el('p','Native project: '+boundBrain.projectId),
      el('p','Codex catalog project: '+(boundBrain.catalogProjectId||boundBrain.projectId)),el('p','Checkout: '+boundBrain.cwd));
    if(doc.retiredHost)details.append(el('p','Original host PID: '+doc.retiredHost.processId),
      el('p','Original host launch claim: '+doc.retiredHost.launchClaimHash));
    panel.append(details);
    const label=el('label',null,'decision-confirm'),check=el('input');check.type='checkbox';
    label.append(check,el('span','I confirm this exact turn recovery. Development stays stopped.'));panel.append(label);
    const confirm=button('Confirm turn recovery',async()=>{
      if(!check.checked)return;
      if(doc.expiresAt<=Date.now()/1000){paint(value);return;}
      confirm.disabled=true;
      try{const result=await post('/api/turn-recovery/confirm',{proposal:preview,confirmed:true});if(same()){turnRecoveryPreviews.delete(key);paint(result);showNotice(result.detail);await refresh();}}
      catch(error){if(same())showNotice('Recovery result not confirmed. Check the existing recovery before any new action. '+error.message,true);}
      finally{confirm.disabled=!check.checked||doc.expiresAt<=Date.now()/1000;}
    },'primary');confirm.disabled=true;check.onchange=()=>{confirm.disabled=!check.checked||doc.expiresAt<=Date.now()/1000;};panel.append(confirm);
    if(expired)panel.append(el('p','This review expired. Refresh recovery review above; nothing was sent.','checkpoint'));
  }
  api('/api/turn-recovery').then(paint).catch(error=>{if(same())panel.append(el('p','Recovery status unavailable. '+error.message,'muted'));});
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
  if(n?.nativeTurnStatus==='connection_lost')return {label:'Connection lost · request unresolved',detail:'The owned Codex connection was lost. Your message and any existing receipt are preserved. Repair the host and reconcile this request; do not send another message.'};
  if(n?.nativeTurnStatus==='unconfirmed')return {label:'Native connection ended · outcome unknown',detail:'The observer ended without a confirmed turn result. Inspect this existing request and host before any new wake.'};
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
      if(typeof wakeFailureDetails==='function')wakeFailureDetails(article,message.notification,message.id);
      receiptRecoveryPanel(article,message);
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
