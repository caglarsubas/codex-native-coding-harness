"use strict";
let assistantHistory=[], assistantPending=false, assistantTurns=0, assistantTokens=0, assistantMissingUsage=0;
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
  $('assistant-clear').disabled=assistantPending;
  $('assistant-context').disabled=!connected||assistantPending;
  document.querySelectorAll('[data-question]').forEach(b=>b.disabled=assistantPending);
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
  if(!f1||!f9)return 'Recorded snapshot only; current native activity is not included.';
  return `Recorded: ${f9.workflow.openDecisions??'unknown'} open decisions · ${f9.workflow.pendingRequests??'unknown'} pending controls · worker dispatch ${f1.dispatchPaused?'paused':'enabled'}. Current native activity is not included.`;
}
async function sendAssistant(event){
  event.preventDefault();const question=$('assistant-question').value.trim();
  if(assistantPending||!connected||!state?.inference?.configured||!question)return;
  assistantPending=true;assistantConnectionChanged();
  assistantStatus('Reading a fresh dashboard snapshot… This may take up to a few minutes.');
  const userTurn=chatTurn('user',question);assistantScroll();
  try{
    const messages=assistantMessages(assistantHistory,question);
    const result=await api('/api/assistant',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({view,messages})});
    assistantHistory=[...messages,{role:'assistant',content:result.answer}];
    const item=chatTurn('assistant',result.answer),links=el('div',null,'assistant-links');
    const caution=el('p','AI draft — may be wrong. Verify advice in the linked views.','chat-caution');
    const facts=el('p',assistantRecordedFacts(result.context),'chat-recorded');
    item.insertBefore(caution,item.children[1]);item.insertBefore(facts,item.children[2]);
    for(const link of result.links){
      // Defense in depth: even server-built links may only navigate known inert views.
      const route=dashboardRoute(link.href);if(!route)continue;
      const a=el('a',link.label+' →');a.href=link.href;
      a.addEventListener('click',e=>{if(e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;e.preventDefault();navigateView(route.view,route.id);});links.append(a);
    }
    item.append(links);
    const evidence=el('details',null,'chat-evidence');
    evidence.append(el('summary','Snapshot · '+when(result.observedAt)+' · '+result.evidence.join(', ')),
      el('p','AI-generated explanation; verify claims in the linked views. This snapshot will age. No action was executed.'),
      el('p',result.model+' · '+result.durationSeconds+'s · '+num(result.usage.total_tokens)+' service tokens (not a bill)'),
      el('pre',JSON.stringify(result.context,null,2)));
    item.append(evidence);
    assistantTurns++;if(Number.isInteger(result.usage.total_tokens))assistantTokens+=result.usage.total_tokens;else assistantMissingUsage++;
    $('assistant-usage').textContent=`This chat: ${assistantTurns} replies · ${num(assistantTokens)} reported service tokens${assistantMissingUsage?' · usage missing for '+assistantMissingUsage+' replies':''}. Separate from Codex usage; not a bill.`;
    $('assistant-question').value='';assistantStatus('Advisory answer ready. Links navigate only.');
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
    if(assistantPending)return;assistantHistory=[];assistantTurns=0;assistantTokens=0;assistantMissingUsage=0;
    $('assistant-log').querySelectorAll('.chat-turn').forEach(e=>e.remove());$('assistant-welcome').hidden=false;
    $('assistant-question').value='';$('assistant-context-preview').textContent='';$('assistant-context-preview').hidden=true;
    $('assistant-usage').textContent='Advisory only. Links open views; they do not take actions.';assistantStatus('Chat cleared from this tab.');assistantConnectionChanged();
  };
  $('assistant-context').onclick=async()=>{
    try{const data=await api('/api/assistant/context?view='+encodeURIComponent(view));$('assistant-context-preview').textContent=JSON.stringify(data,null,2);$('assistant-context-preview').hidden=false;}
    catch(error){assistantStatus(error.message,true);}
  };
  assistantConnectionChanged();
}
document.addEventListener('DOMContentLoaded',initAssistant,{once:true});
