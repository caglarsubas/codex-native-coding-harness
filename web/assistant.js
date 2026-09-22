"use strict";
let assistantHistory=[], assistantPending=false, assistantTurns=0, assistantTokens=0, assistantMissingUsage=0;
const assistantActions=new Map();
function assistantMessages(history,question){
  const messages=[...history.slice(-8),{role:"user",content:question}];
  while(messages.length>1&&(messages.reduce((n,m)=>n+m.content.length,0)>16000||new TextEncoder().encode(JSON.stringify(messages)).length>30000))messages.splice(0,2);
  return messages;
}
function assistantConnectionChanged(){
  const configured=connected&&state?.inference?.configured;
  $('assistant-service').textContent=!connected?"Connect to the ledger to ask a question.":configured?"On-prem inference · "+(state.inference.assistantModel||state.inference.model):"Inference not configured. Ask the local operator to check the private .env.";
  $('assistant-send').disabled=!configured||assistantPending||!$('assistant-question').value.trim();
  $('assistant-question').readOnly=assistantPending;
  $('assistant-clear').disabled=assistantPending||[...assistantActions.values()].some(a=>a.sending);
  $('assistant-context').disabled=!connected||assistantPending;
  document.querySelectorAll('[data-question]').forEach(b=>b.disabled=assistantPending);
  refreshAssistantActions();
  if(typeof updateWorkspaceSelector==='function')updateWorkspaceSelector();
}
function assistantStatus(text,error=false){$('assistant-status').textContent=text;$('assistant-status').dataset.error=String(error);}
function chatTurn(role,content){
  $('assistant-welcome').hidden=true;
  const item=el('article',null,'chat-turn');item.dataset.role=role;
  const body=el('p');
  // Models sometimes emit emphasis despite the plain-text contract. Only bold
  // text is supported; HTML, URLs and Markdown links never become active markup.
  if(role==='assistant')content.split(/(\*\*[^*\n]{1,240}\*\*)/g).forEach(part=>body.append(el(part.startsWith('**')&&part.endsWith('**')?'strong':'span',part.startsWith('**')&&part.endsWith('**')?part.slice(2,-2):part)));
  else body.textContent=content;
  item.append(el('p',role==='user'?'YOU':'AI · ADVISORY','eyebrow'),body);
  $('assistant-log').append(item);return item;
}
function assistantScroll(){const log=$('assistant-log');log.scrollTop=log.scrollHeight;}
function assistantRecordedFacts(context){
  const f1=context.facts.find(f=>f.id==='F1')?.data, f9=context.facts.find(f=>f.id==='F9')?.data;
  const activity=context.facts.find(f=>f.id==='F12')?.data?.activity;
  if(!f1||!f9)return 'Recorded snapshot only; activity may be stale or unavailable.';
  return `Answer snapshot (not live): ${f9.workflow.openDecisions??'unknown'} open decisions · ${f9.workflow.pendingRequests??'unknown'} pending controls · worker dispatch ${f1.dispatchPaused?'paused':'enabled'}. Brain activity: ${activity?.fresh?activity.status:'unknown / stale'}.`;
}
function assistantActionState(action,current=state,now=Date.now()/1000){
  const doc=action.proposal.document;
  const recorded=current?.commands?.find(c=>c.id===doc.command.id)||action.receipt;
  if(recorded){const display=commandPresentation(recorded,current?.brainActivity,now);return {locked:true,label:display.label,detail:display.detail,recorded};}
  if(action.cancelled)return {locked:true,label:'Not submitted',detail:'You dismissed this preview. Nothing was changed.'};
  if(action.rejected)return {locked:true,label:'Confirmation refused',detail:action.rejected+' Ask for a new preview after reviewing the current state.'};
  if(action.sending)return {locked:true,label:'Submitting confirmed action…',detail:'Waiting for the ledger receipt. Do not submit another copy.'};
  if(action.uncertain)return {locked:false,label:'Receipt not confirmed',detail:'Check Control requests in the project. You can retry this exact confirmation; its command ID will not change.'};
  if(now>doc.expiresAt)return {locked:true,label:'Preview expired',detail:'Ask again to review current state. Nothing was submitted from this preview.'};
  if(current?.meta?.revision!==doc.command.expectedRevision)return {locked:true,label:'State changed',detail:'Ask again to review the latest state before confirming. No control was submitted from this preview.'};
  return {locked:false,label:'Awaiting your confirmation',detail:'Review the exact action and target below. Sending a chat message is not confirmation.'};
}
function refreshAssistantActions(){
  for(const action of assistantActions.values()){
    const info=assistantActionState(action);
    action.status.textContent=info.label+'. '+info.detail;
    action.confirm.disabled=!connected||info.locked;
    action.confirm.textContent=info.recorded?'Confirmed':action.uncertain?'Retry same confirmation':'Confirm: '+action.proposal.document.preview.title;
    action.dismiss.disabled=!!info.recorded||action.sending||action.cancelled||action.uncertain;
    action.element.dataset.actionState=info.recorded?'recorded':info.locked?'closed':'review';
    action.element.querySelector('.eyebrow').textContent=info.recorded?'CONFIRMED CONTROL · RECEIPT BELOW':'ACTION PREVIEW · NOT EXECUTED';
  }
}
function assistantActionPreview(item,proposal){
  const doc=proposal.document, preview=doc.preview, section=el('section',null,'chat-action');
  section.setAttribute('aria-label','Review proposed action');
  section.append(el('p','ACTION PREVIEW · NOT EXECUTED','eyebrow'),el('h3',preview.title),
    el('p','Target: '+preview.target),el('p',preview.impact));
  if(preview.details.scope)section.append(el('p','Scope: '+preview.details.scope));
  if(doc.command.kind==='decision_response'){
    section.append(el('p','Exact answer to save'),el('pre',doc.command.payload.note,'chat-answer-preview'));
  }
  const detail=el('details');detail.append(el('summary','Exact scope, binding & expiry'),
    el('p',`State revision ${doc.command.expectedRevision} · expires ${when(doc.expiresAt)}`),
    el('pre',JSON.stringify({kind:doc.command.kind,target:preview.target,payload:doc.command.payload,...preview.details},null,2)));
  section.append(detail);
  const status=el('p',null,'chat-action-status');status.setAttribute('role','status');
  const controls=el('div',null,'assistant-actions'),confirm=el('button',null,'primary'),dismiss=el('button','Dismiss preview');
  confirm.type=dismiss.type='button';controls.append(dismiss,confirm);section.append(status,controls);
  const route=dashboardRoute(preview.href);
  if(route){const link=el('a','Review in project →');link.href=workspaceHref(route.view,route.id);link.onclick=e=>{e.preventDefault();navigateView(route.view,route.id);};section.append(link);}
  const action={proposal,element:section,status,confirm,dismiss,sending:false,cancelled:false,uncertain:false,receipt:null};
  assistantActions.set(doc.command.id,action);
  dismiss.onclick=()=>{action.cancelled=true;refreshAssistantActions();};
  confirm.onclick=async()=>{
    if(!connected||assistantActionState(action).locked)return;
    action.sending=true;action.uncertain=false;assistantConnectionChanged();
    try{
      action.receipt=await api('/api/assistant/confirm',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({proposal,confirmed:true})});
      const receipt=commandPresentation(action.receipt);assistantStatus(receipt.label+'. '+receipt.detail);
      await refresh();
    }catch(error){
      // Retain the same signed command ID. Never auto-retry uncertain delivery.
      if([400,401,403,409].includes(error.status))action.rejected=error.message;
      else action.uncertain=!action.receipt;
      assistantStatus(error.message+' Check the recorded request before retrying.',true);
    }finally{action.sending=false;assistantConnectionChanged();}
  };
  item.append(section);refreshAssistantActions();
}
async function sendAssistant(event){
  event.preventDefault();const question=$('assistant-question').value.trim();
  if(assistantPending||!connected||!state?.inference?.configured||!question)return;
  assistantPending=true;assistantConnectionChanged();
  assistantStatus('Reading a fresh dashboard snapshot… This may take up to a few minutes.');
  const userTurn=chatTurn('user',question);assistantScroll();
  try{
    const messages=assistantMessages(assistantHistory,question);
    const result=await api('/api/assistant',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({view:view==='workspaces'?'overview':view,messages})});
    assistantHistory=[...messages,{role:'assistant',content:result.answer}];
    const item=chatTurn('assistant',result.answer),links=el('div',null,'assistant-links');
    const caution=el('p','AI draft — may be wrong. Verify advice in the linked views.','chat-caution');
    const facts=el('p',assistantRecordedFacts(result.context),'chat-recorded');
    item.insertBefore(caution,item.children[1]);item.insertBefore(facts,item.children[2]);
    for(const link of result.links){
      // Defense in depth: even server-built links may only navigate known inert views.
      const route=dashboardRoute(link.href);if(!route)continue;
      const a=el('a',link.label+' →');a.href=workspaceHref(route.view,route.id);
      a.addEventListener('click',e=>{if(e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;e.preventDefault();navigateView(route.view,route.id);});links.append(a);
    }
    item.append(links);
    if(result.proposal)assistantActionPreview(item,result.proposal);
    const evidence=el('details',null,'chat-evidence');
    evidence.append(el('summary','Snapshot · '+when(result.observedAt)+' · '+result.evidence.join(', ')),
      el('p','AI-generated explanation; verify claims in the linked views. This snapshot will age. No action was executed.'),
      el('p',result.model+' · '+result.durationSeconds+'s · '+num(result.usage.total_tokens)+' service tokens (not a bill)'),
      el('pre',JSON.stringify(result.context,null,2)));
    item.append(evidence);
    assistantTurns++;if(Number.isInteger(result.usage.total_tokens))assistantTokens+=result.usage.total_tokens;else assistantMissingUsage++;
    $('assistant-usage').textContent=`This chat: ${assistantTurns} replies · ${num(assistantTokens)} reported service tokens${assistantMissingUsage?' · usage missing for '+assistantMissingUsage+' replies':''}. Separate from Codex usage; not a bill.`;
    $('assistant-question').value='';assistantStatus(result.proposal?'Review the action preview. Nothing changes until you confirm.':'Answer ready. No action was submitted.');
  }catch(error){
    userTurn.remove();$('assistant-welcome').hidden=assistantHistory.length>0;
    assistantStatus(error.message+' Your question is retained. No automatic retry was sent.',true);
  }finally{
    assistantPending=false;assistantConnectionChanged();assistantScroll();
  }
}
function initAssistant(){
  $('assistant-form').addEventListener('submit',sendAssistant);
  $('assistant-question').addEventListener('input',assistantConnectionChanged);
  $('assistant-question').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)&&!e.isComposing){e.preventDefault();$('assistant-form').requestSubmit();}});
  document.querySelectorAll('[data-question]').forEach(b=>b.addEventListener('click',()=>{$('assistant-question').value=b.dataset.question;assistantConnectionChanged();$('assistant-question').focus();}));
  $('assistant-clear').onclick=()=>{
    if(assistantPending||[...assistantActions.values()].some(a=>a.sending))return;assistantHistory=[];assistantTurns=0;assistantTokens=0;assistantMissingUsage=0;assistantActions.clear();
    $('assistant-log').querySelectorAll('.chat-turn').forEach(e=>e.remove());$('assistant-welcome').hidden=false;
    $('assistant-question').value='';$('assistant-context-preview').textContent='';$('assistant-context-preview').hidden=true;
    $('assistant-usage').textContent='Actions need your confirmation. Recorded requests remain in the ledger after clearing chat.';assistantStatus('Chat cleared from this tab. Recorded controls are unchanged.');assistantConnectionChanged();
  };
  $('assistant-context').onclick=async()=>{
    try{const data=await api('/api/assistant/context?view='+encodeURIComponent(view==='workspaces'?'overview':view));$('assistant-context-preview').textContent=JSON.stringify(data,null,2);$('assistant-context-preview').hidden=false;}
    catch(error){if(!error.workspaceChanged)assistantStatus(error.message,true);}
  };
  assistantConnectionChanged();
}
document.addEventListener('DOMContentLoaded',initAssistant,{once:true});
