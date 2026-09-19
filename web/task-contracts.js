"use strict";
const taskContractDetails=new Map();
function canLegacyApprove(q){return q.status==='proposed'&&!Object.hasOwn(q,'taskContract');}
function taskContractSummary(root,contract){
  if(!contract||contract.status==='not_declared')return;
  const panel=el('section',null,'task-contract');
  panel.append(el('h3','Phase-bound task declaration'),badge(contract.status==='bound'?'Bound · not activated':contract.status),
    el('p','Legacy seed-only approval cannot authorize this task. Run-aware activation and approval are still required.','muted'));
  if(contract.issue)panel.append(el('p',contract.issue));
  if(contract.operations)panel.append(el('p','Declared operations: '+contract.operations.join(', ')),
    el('p','Estimated tokens: '+num(contract.estimatedTokens)+' · estimate only, not a reservation.','muted'));
  if(contract.settings){
    const requested=contract.settings.requested;
    panel.append(table(['Setting','Requested','Applied / observed'],['model','effort','speed'].map(key=>[
      key[0].toUpperCase()+key.slice(1),requested[key]===null?'Use native default':requested[key],'Not applied / unknown'])),
      el('p','Host support and owner execution policy are unverified. No automatic fallback or native setting change.','muted'));
  }
  root.append(panel);
}
function taskContractPanel(root,q){
  if(!Object.hasOwn(q,'taskContract'))return;
  const wid=workspaceId,generation=workspaceGeneration,panel=el('section',null,'task-contract-panel');
  panel.append(el('p','Loading phase-bound task declaration…','muted'));root.append(panel);
  api('/api/task-contract?queueId='+encodeURIComponent(q.id)).then(contract=>{
    if(wid!==workspaceId||generation!==workspaceGeneration)return;
    panel.replaceChildren();taskContractSummary(panel,contract);
    if(contract.document){
      const doc=contract.document;
      panel.append(el('p','Version '+doc.version+' · proposed '+when(doc.createdAt),'muted'),
        el('p',doc.spec.rationale),el('p','New task instead of reuse: '+doc.spec.reuseReason));
      const details=el('details'),key=wid+':'+q.id+':'+contract.contractHash;
      details.open=taskContractDetails.get(key)||false;
      details.append(el('summary','Read exact task declaration & version history'),el('pre',JSON.stringify(contract,null,2)));
      details.addEventListener('toggle',()=>taskContractDetails.set(key,details.open));panel.append(details);
    }
  }).catch(error=>{if(!error.workspaceChanged&&wid===workspaceId&&generation===workspaceGeneration)panel.replaceChildren(el('p','Task declaration unavailable. Legacy approval remains blocked.','muted'));});
}
