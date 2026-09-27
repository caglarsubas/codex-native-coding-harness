"use strict";
// Presentation only: never rewrite retained evidence or infer a successful outcome.
const narrativeDisclosures=new Map();
function recoverySummary(root,recovery,showTitle=true){
  if(!recovery)return;
  const card=el('section',null,'recovery-summary');card.setAttribute('role','status');
  card.append(el('p','RECORDED CONDITIONS · NOT LIVE ACTIVITY','eyebrow'));
  if(showTitle)card.append(el('h3',recovery.title));
  const facts=el('ul');
  if(recovery.unconfirmedTasks)facts.append(el('li',`${recovery.unconfirmedTasks} worker ${recovery.unconfirmedTasks===1?'identity is':'identities are'} not confirmed. The phase cannot close its checkpoint while this ownership is unresolved.`));
  if(recovery.uncertainMerges)facts.append(el('li','A merge outcome is unresolved. Inspect the existing PR; do not resend the merge.'));
  if(recovery.supervisionRequired)facts.append(el('li','The brain released its controller with unsettled tasks. Their current activity needs checking; it is not proof that they stopped.'));
  const explained=new Set(['native_identity','unresolved_merge','supervision_required','token_budget','usage_gap']);
  for(const item of recovery.issues||[])if(!explained.has(item.code))facts.append(el('li',item.label));
  if(!recovery.issues?.length&&!recovery.reconciliationRequired)facts.append(el('li',recovery.explanation));
  if(recovery.budgetBoundaryReached)facts.append(el('li',`Token boundary reached: at least ${num(recovery.knownUsageLowerBound)} recorded against the ${num(recovery.budget)} phase budget. New work needs a separately reviewed plan; usage is not reset.`));
  if(recovery.gapCount)facts.append(el('li','Usage coverage is incomplete. Remaining measured budget is unknown.'));
  card.append(facts,el('p',recovery.nextStep,'recovery-next'));
  const details=el('details');details.append(el('summary',`Details · ${recovery.issueCount} recorded conditions and safety boundary`));
  const measurements=el('ul');
  measurements.append(el('li',`${recovery.registeredTasks} of ${recovery.maxTasks??'unknown'} allowed tasks registered · ${recovery.maxParallelTasks??'unknown'} parallel maximum · phase expires ${when(recovery.expiresAt)}`));
  if(recovery.usageRelevant){
    measurements.append(el('li',`${recovery.observedTotal===null?'Observed usage unknown':num(recovery.observedTotal)+' observed tokens'} · ${num(recovery.budget)} reviewed phase limit · ${num(recovery.checkpointReserve)} checkpoint reserve`));
    if(recovery.knownUsageLowerBound!==null&&(recovery.observedTotal===null||recovery.knownUsageLowerBound>recovery.observedTotal))
      measurements.append(el('li',`At least ${num(recovery.knownUsageLowerBound)} tokens were retained in the usage high-water mark; a later partial sample cannot reduce that amount.`));
    if(recovery.observedTotal!==null)measurements.append(el('li',`${num(recovery.cachedInput)} cached input · ${num(recovery.uncachedInput)} uncached input · ${num(recovery.output)} output. Cached input is included in the total; this is not a bill.`));
    measurements.append(el('li',`Measured balance ${recovery.remainingMeasured===null?'unknown':num(recovery.remainingMeasured)} · observed ${when(recovery.observedAt)}`));
  }
  details.append(measurements);
  if(recovery.issues?.length){const list=el('ul');for(const item of recovery.issues)list.append(el('li',`${item.label} · ${item.source.replaceAll('_',' ')} · ${item.nextStep}`));details.append(list);}
  if(recovery.issuesTruncated)details.append(el('p','Additional recorded conditions omitted from this bounded summary; inspect project controls.'));
  if(recovery.gapLabels.length){const list=el('ul');for(const label of recovery.gapLabels)list.append(el('li',label));details.append(list);}
  details.append(el('p',recovery.boundary));card.append(details);root.append(card);
}
function narrativeHighlights(value){
  const text=String(value||'');
  const sentences=text.split(/\n+|(?<=[.!?])\s+(?=[A-Z])/).map(s=>s.trim()).filter(Boolean);
  // Whole sentences only. Never cut off a qualification or a negative clause.
  const eligible=sentences.filter(s=>s.length<=240&&!/[a-f0-9]{32,}|https?:\/\/|\/Users\//i.test(s));
  const change=eligible.find(s=>/\b(added|changed|implemented|corrected|fixed|completed|retained)\b/i.test(s));
  const boundary=eligible.find(s=>/\b(not|no|unverified|unknown|blocked|untested|requires|pending|only)\b/i.test(s));
  const next=sentences.find(s=>s.length<=600&&/^(next(?: exact owner)? (?:action|step)|next:)/i.test(s));
  return [...new Set([change,boundary,next,...eligible].filter(Boolean))].slice(0,3);
}
function latestBrainReply(snapshot){
  return [...(snapshot.commands||[])].filter(c=>c.kind==='reconcile'&&c.conversationReply)
    .sort((a,b)=>b.conversationReply.at-a.conversationReply.at)[0];
}
function priorPhaseUsageWarning(snapshot){
  const run=snapshot.standard?.run,spec=snapshot.mission?.document?.spec;
  if(!run||!['completed','blocked'].includes(run.status)||!spec||spec.phase.id===run.phaseId||!run.usageReport?.gaps?.length)return '';
  return 'Before Play: the previous phase stopped with incomplete usage evidence. Its recorded usage and gaps remain preserved. The new phase needs a fresh, complete measurement before any worker can start; reviewing this plan does not clear that requirement.';
}
function narrative(value,label='Report',facts=[]){
  const text=String(value||'');
  if(text.length<=280&&!facts.length)return el('p',text,'narrative-short');
  const root=el('div',null,'narrative');
  root.append(el('p',label+(facts.length?' · recorded':' · selected excerpts'),'narrative-label'));
  const bullets=facts.length?facts.slice(0,3):narrativeHighlights(text);
  if(bullets.length){const list=el('ul',null,'narrative-highlights');bullets.forEach(s=>list.append(el('li',s)));root.append(list);}
  else root.append(el('p','The full report is available below.','muted'));
  root.append(el('p',(label.startsWith('AI ')?'AI-generated, not verified. ':'Recorded information, not live verification. ')+'Full context and limitations in Details.','narrative-boundary'));
  const details=el('details',null,'narrative-details');
  // Scope preferences by project, label AND exact report; never carry a stale open state to new evidence.
  const project=typeof workspaceId==='undefined'?'legacy':workspaceId||'legacy';
  const key=JSON.stringify([project,label,text]);
  details.open=narrativeDisclosures.has(key);
  details.append(el('summary','Details · '+label),el('p',text,'narrative-full'));
  details.addEventListener('toggle',()=>{
    if(!details.isConnected)return;
    if(details.open){narrativeDisclosures.set(key,true);if(narrativeDisclosures.size>100)narrativeDisclosures.delete(narrativeDisclosures.keys().next().value);}
    else narrativeDisclosures.delete(key);
  });root.append(details);return root;
}
function phaseNarrative(text,tasks=[]){
  const completed=tasks.filter(t=>['complete','completed'].includes(t.status));
  const facts=completed.filter(t=>typeof t.title==='string'&&t.title.length<=200).slice(0,2).map(t=>'Completed task: '+t.title);
  if(tasks.length)facts.push(`${completed.length} of ${tasks.length} tasks recorded complete. Completion does not establish merge or rollout.`);
  return narrative(text,'Phase outcome',facts);
}
