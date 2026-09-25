"use strict";
// Presentation only: never rewrite retained evidence or infer a successful outcome.
const narrativeDisclosures=new Map();
function recoverySummary(root,recovery){
  if(!recovery)return;
  const card=el('section',null,'recovery-summary');card.setAttribute('role','status');
  card.append(el('p','RECORDED SAFETY STOP','eyebrow'),el('h3',recovery.title),el('p',recovery.explanation));
  const facts=el('ul');
  facts.append(el('li',`${recovery.registeredTasks} of ${recovery.maxTasks??'unknown'} allowed tasks registered · ${recovery.maxParallelTasks??'unknown'} parallel maximum · phase expires ${when(recovery.expiresAt)}`));
  if(recovery.usageRelevant){
    facts.append(el('li',`${recovery.observedTotal===null?'Observed usage unknown':num(recovery.observedTotal)+' observed tokens'} · ${num(recovery.budget)} reviewed phase limit · ${num(recovery.checkpointReserve)} checkpoint reserve`));
    if(recovery.knownUsageLowerBound!==null&&(recovery.observedTotal===null||recovery.knownUsageLowerBound>recovery.observedTotal))
      facts.append(el('li',`At least ${num(recovery.knownUsageLowerBound)} tokens were retained in the usage high-water mark; a later partial sample cannot reduce that amount.`));
    if(recovery.observedTotal!==null)facts.append(el('li',`${num(recovery.cachedInput)} cached input · ${num(recovery.uncachedInput)} uncached input · ${num(recovery.output)} output. Cached input is included in the total; this is not a bill.`));
    facts.append(el('li',`Measured balance ${recovery.remainingMeasured===null?'unknown':num(recovery.remainingMeasured)} · observed ${when(recovery.observedAt)}`));
  }
  card.append(facts,el('p',recovery.nextStep,'recovery-next'));
  const details=el('details');details.append(el('summary',`Details · ${recovery.issueCount} recorded conditions and safety boundary`));
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
  return [...new Set([change,boundary,...eligible].filter(Boolean))].slice(0,3);
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
