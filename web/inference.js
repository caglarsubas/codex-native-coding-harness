"use strict";
let inferencePending=false, inferenceDisclosure=false;

async function requestExecutiveBrief(force=false) {
 if(inferencePending||!connected)return;
 inferencePending=true;render();
 try {
  await api('/api/executive-summary',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({force})});
  showNotice('Brief requested. The model can advise, but cannot approve or dispatch work.');
  await refresh();
 }catch(error){showNotice(error.message,true);}
 finally{inferencePending=false;render();}
}

function executiveSummary(root) {
 const data=state.inference;
 if(!data)return;
 const panel=el('section',null,'executive-brief'),heading=el('div',null,'brief-heading');
 panel.setAttribute('aria-label','Executive brief');
 const label=el('div');label.append(el('p','PORTFOLIO INTELLIGENCE · ADVISORY','eyebrow'),el('h2','Executive brief'));
 const running=inferencePending||data.job?.status==='running';
 const action=button(running?'Preparing brief…':data.latest?(data.stale?'Update brief':'Regenerate brief'):'Generate brief',()=>requestExecutiveBrief(Boolean(data.latest&&!data.stale)),'primary');
 action.disabled=!data.configured||running;
 heading.append(label,action);panel.append(heading);
 panel.append(el('p','On request, sends only the aggregate status snapshot below to your configured inference service. No source code, conversations, artifact contents or credentials are included in the prompt.','brief-disclosure'));
 if(!data.configured)panel.append(el('p',data.reason,'metric-note'));
 if(running){const progress=el('p','Reading the recorded evidence with a 90-second network timeout; no automatic retry or external-provider fallback.','metric-note');progress.setAttribute('role','status');panel.append(progress);}
 if(data.job?.status==='failed')panel.append(callout('No new brief published',data.job.error));
 const report=data.latest;
 if(report){
  const meta=el('div',null,'brief-meta');meta.append(badge(data.stale?'stale snapshot':'recent snapshot'),el('span',when(report.generatedAt)+' · '+report.model+' · '+report.durationSeconds+'s'));
  panel.append(meta,el('p','AI-generated draft · Claims are not independently verified. The model can misinterpret counts, scope or dates; compare the evidence before acting.','brief-review'),el('h3',report.brief.headline,'brief-headline'),narrative(report.brief.summary,'AI executive brief'));
  const columns=el('div',null,'brief-columns');
  [['Needs attention','attention'],['Suggested next steps','nextSteps']].forEach(([title,key])=>{
   const column=el('div');column.append(el('h4',title));const list=el('ul');
   report.brief[key].forEach(item=>{const li=el('li');li.append(el('span',item.text),el('span','Evidence: '+item.evidence.join(', '),'subline'));list.append(li);});column.append(list);columns.append(column);
  });panel.append(columns);
  const usage=report.usage;
  panel.append(el('p','Service-reported tokens: '+num(usage.prompt_tokens)+' input / '+num(usage.completion_tokens)+' output / '+num(usage.total_tokens)+' total. Separate from Codex usage; not a bill.','subline'));
  if(data.retainedUsage?.briefsWithUsage)panel.append(el('p','Retained brief usage: '+num(data.retainedUsage.total_tokens)+' tokens across '+num(data.retainedUsage.briefsWithUsage)+' version(s) with usage metadata. Failed/discarded requests and older unmetered versions are excluded.','subline'));
  panel.append(el('p',(data.stale?'Snapshot changed or the 15-minute freshness window expired. ':'')+'The service reported local-inference routing. Evidence IDs are checked; factual interpretation still needs your review. No controls were changed.','metric-note'));
  if(report.artifactId){const download=el('a','Download this brief & evidence','button');download.href='/api/artifacts/'+report.artifactId+'/download';panel.append(download,el('span','Every successful brief is versioned in Artifact library.','subline'));}
 }else if(!running){panel.append(el('p','No brief generated yet. Your recorded evidence remains available below.','metric-note'));}
 const detail=el('details',null,'coverage-details');detail.open=inferenceDisclosure;
 detail.append(el('summary','Inspect evidence & data sent'));
 if(report){detail.append(el('h4','Evidence used for the displayed brief'),el('pre',JSON.stringify(report.evidence,null,2)));}
 detail.append(el('h4','Current snapshot for the next request'),el('pre',JSON.stringify(data.currentEvidence,null,2)));
 detail.addEventListener('toggle',()=>{inferenceDisclosure=detail.open;});panel.append(detail);root.append(panel);
}
