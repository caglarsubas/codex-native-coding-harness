"use strict";
let readinessPending=false;
const readinessExpanded=new Set();
Object.assign(titles,{readiness:['Operational readiness','Prepare one supervised pilot. Every gate has an owner and a reason.']});

function openReadiness() {
 view='readiness';selected=null;
 document.querySelectorAll('[data-view]').forEach(b=>{b.removeAttribute('aria-current');if(b.dataset.view===view)b.setAttribute('aria-current','page');});
 render();window.scrollTo(0,0);
}

function readinessSummary(root) {
 const data=state.readiness;if(!data)return;
 const panel=el('div',null,'readiness-summary');
 panel.append(el('p','OPERATING POSTURE','eyebrow'),el('h2',data.activeWorkers?'Existing work needs supervision':data.pilotPassed?'Review the next approved scope':'Prepare the first supervised pilot'),
  el('p',data.nextAction),button('Review readiness & blockers',openReadiness));
 root.append(panel);
}

async function runReadiness(operation) {
 if(readinessPending||!connected)return;
 readinessPending=true;render();
 try{
  await api('/api/readiness',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({operation})});
  showNotice(operation==='inspect'?'Local metadata checks started. No task or model request.':'Synthetic lifecycle rehearsal started. This cannot certify a real pilot.');
  await refresh();
 }catch(error){showNotice(error.message,true);}
 finally{readinessPending=false;render();}
}

function readiness(root) {
 const d=state.readiness,m=state.meta;if(!d){root.append(empty('Readiness unavailable','Refresh the local connection.'));return;}
 const controls=el('div',null,'observation-toolbar');
 const inspect=button('Inspect local readiness',()=>runReadiness('inspect'),'primary');
 const rehearse=button('Run isolated rehearsal',()=>runReadiness('rehearse'));
 inspect.disabled=rehearse.disabled=readinessPending||d.job?.status==='running';controls.append(inspect,rehearse);root.append(controls);
 if(d.job?.status==='running')root.append(el('p','Running '+d.job.operation+'… No live dispatch or acceptance commands.','metric-note'));
 if(d.job?.status==='complete')root.append(el('p',(d.job.operation==='inspect'?'Local readiness inspection completed':'Synthetic rehearsal completed')+' · '+when(d.job.finishedAt)+'. Controller authority is unchanged.','metric-note'));
 if(d.job?.status==='failed')root.append(callout('Check did not complete',d.job.error));
 root.append(el('p','Local checks: '+when(d.localObservedAt)+' · Native inventory: '+when(d.nativeObservedAt)+'. Observations expire after 15 minutes; packet preflight expires after 5.','metric-note'));
 root.append(callout(d.activeWorkers?'Supervision required':m.paused?'Dispatch parked safely':'Brain verification required',d.nextAction));
 root.append(section('Before the platform drives','A green diagnostic never authorizes work.'));
 root.append(table(['Gate','Recorded state','Next action'],[
  ['Designated brain',textCell(d.brainObservedStatus,d.brainId||'Not configured'),d.brainFresh?'Recent ledger checkpoint; recheck native state at dispatch.':'Open the designated brain and perform a read-only reconciliation.'],
  ['Approved scope',state.queue.filter(q=>q.status==='approved').length+' approved / '+state.queue.length+' prepared','Review one immutable inheritance seed, then approve its exact hashes.'],
  ['Native mappings',d.repositories.filter(r=>r.mappingObserved).length+' / '+d.repositories.length+' observed','Register existing checkouts in Codex; then the brain records exact native IDs.'],
  ['Dispatch',m.paused?'Paused':'Enabled in ledger','Resume is a separate request processed by the brain, never by this diagnostic.'],
  ['Heartbeat',d.heartbeat.status+' (recorded)','A paused heartbeat does not wake from this webpage. Start with the brain handoff below.'],
  ['Real worker pilot',d.pilotPassed?'Recorded accepted':'Not accepted · one worker limit','Complete and independently verify a real approved worker; simulation does not qualify.'],
  ['Pending controls',d.pendingControls+' pending / '+d.uncertainControls+' uncertain','Reconcile uncertain native actions before retrying.']
 ]));
 root.append(section('Repository preparation','Metadata checks do not prove safe setup, CI or acceptance.'));
 root.append(table(['Repository / policy','Checkout & native mapping','Required follow-through'],d.repositories.map(r=>{
  const detail=el('details',null,'readiness-detail');detail.append(el('summary',r.issues.length?r.issues.length+' setup issue(s)':'Registration observed; review execution gates'));
  detail.open=readinessExpanded.has(r.repository);
  detail.addEventListener('toggle',()=>{if(detail.isConnected){if(detail.open)readinessExpanded.add(r.repository);else readinessExpanded.delete(r.repository);}});
  const list=el('ul');r.issues.forEach(v=>list.append(el('li',v)));list.append(el('li',r.setupReview),el('li',r.ciNote));
  if(r.candidateProjectId&&!r.configuredProjectId)list.append(el('li','Observed matching project: '+r.candidateProjectId+'. Mapping has not been applied.'));
  detail.append(list);return[textCell(r.repository,r.profile+' · '+r.mergePolicy+' merge'),textCell(r.commit?.slice(0,12)||'Not observed',r.mappingObserved?'Native mapping observed':'Native mapping unverified'),detail];
 })));
 root.append(section('Packet launch preview','Read-only explanation using the same packet gates as dispatch.'));
 if(!d.packets.length)root.append(el('p','No packet has been prepared. A roadmap checkbox is not an executable queue item. Select one bounded scope and ask the brain to prepare its inheritance and evidence contract.','muted'));
 for(const p of d.packets){const sectionNode=el('section',null,'detail');sectionNode.append(el('h3',p.packetId+' · '+p.repository),badge(p.status==='complete'?'complete':p.status==='dispatched'?'owned':p.ledgerEligible?'ledger gates met':'blocked'),el('p','Seed '+p.seedHash.slice(0,12),'mono'));
  const list=el('ul');p.issues.forEach(i=>list.append(el('li',i.detail)));sectionNode.append(list);if(p.ledgerEligible)sectionNode.append(el('p','Still requires a live brain cycle and current external checks. This preview does not create a task.','muted'));root.append(sectionNode);}
 root.append(section('Safe handoff to the brain','Copy this into the designated Codex task. It requests inspection, not approval.'));
 root.append(el('pre',d.brainPrompt));const copy=button('Copy brain handoff',async()=>{try{await navigator.clipboard.writeText(d.brainPrompt);showNotice('Read-only handoff copied. Paste it into the designated brain task.');}catch{showNotice('Clipboard unavailable. Copy the displayed text manually.',true);}});root.append(copy,el('p','This dashboard cannot open or wake a native task by itself. Queued control requests execute only when the brain is active.','metric-note'));
 root.append(section('Isolated lifecycle rehearsal','No native task, product checkout, inference request or acceptance process.'));
 if(d.rehearsal){root.append(el('p',d.rehearsal.status+' · '+when(d.rehearsal.at)+' · Synthetic only; real pilot remains '+(d.pilotPassed?'separately recorded':'unaccepted'), 'metric-note'));
  root.append(table(['Simulated safety check','Result'],d.rehearsal.steps.map(s=>[s.check,s.status])));
  if(d.rehearsal.artifactId)root.append(button('Read rehearsal evidence',()=>{selected=d.rehearsal.artifactId;render();}));
 }else root.append(el('p','Not run. Use the rehearsal to check controller state transitions before a real pilot.','muted'));
 root.append(el('p',d.limits,'metric-note'));
 if(selected)artifactReader(root,selected);
}
