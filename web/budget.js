"use strict";
const budgetReports=new Map(),budgetPending=new Map(),budgetDetails=new Map();
const budgetIssues={phase_binding_unavailable:'Phase binding is unavailable',usage_evidence_incomplete:'Some session evidence is incomplete',membership_changed:'Task membership changed after the sample',usage_account_changed:'Usage account binding changed',phase_journal_not_observed:'No complete phase-usage journal is recorded',usage_coverage_incomplete:'Brain, worker or review coverage is incomplete',usage_not_observed:'Usage has not been observed',usage_stale_or_future:'The oldest usage sample is stale or future-dated'};
function budgetFreshness(report,snapshot,now=Date.now()/1000){
  if(!report)return {stale:true,label:'Not inspected in this tab'};
  if(report.workspaceRevision!==snapshot.meta.revision)return {stale:true,label:'Project changed since inspection · inspect again'};
  if(now<report.inspectedAt||now-report.inspectedAt>60)return {stale:true,label:'Earlier accounting snapshot · inspect again'};
  return {stale:false,label:'Saved accounting at inspection · shared state has not been rechecked'};
}
function budgetBalance(row,report,snapshot,now=Date.now()/1000){
  return budgetFreshness(report,snapshot,now).stale||!row.expiresAt||now>row.expiresAt||now<row.observedAt?null:row.recordedBalance;
}
function budgetSummary(root){
  if(!state.workspace)return;
  const cached=state.budgetInspection,body=el('section',null,'mission-summary');
  body.append(el('h2','Phase budget & reservations'),el('p',cached&&cached.status!=='not_inspected'?
    `Last explicit inspection: ${when(cached.inspectedAt)}. ${cached.expired||cached.workspaceChanged?'Earlier snapshot; inspect again.':'Recorded accounting only; shared state is not polled.'}`:
    'Inspect the phase allowance, reserved estimates and charges awaiting reconciliation. Missing usage is not zero.','muted'),button('Inspect budgets in Token usage',()=>navigateView('usage')));root.append(body);
}
function budgetView(root){
  if(!state.workspace)return;
  const report=budgetReports.get(workspaceId),pending=budgetPending.has(workspaceId);
  const panel=el('section',null,'budget-view');panel.setAttribute('aria-label','Phase budget and shared account inspection');
  const intro=el('div',null,'section-heading'),heading=el('div');heading.append(el('p','SELECTED PROJECT · READ ONLY','eyebrow'),el('h2','Phase budget & reservations'));
  const load=button(pending?'Reading saved accounting…':report?'Inspect accounting again':'Inspect saved accounting',()=>inspectBudget(),'primary');load.disabled=pending||!connected;
  intro.append(heading,load);panel.append(intro,el('p','Read the existing shared ledger for this project. This does not collect native token samples, initialize a budget or start work.','muted'));
  root.append(panel);
  if(!report){panel.append(empty('Budget accounting has not been inspected','Open this view safely without starting a scan. Use Inspect saved accounting to read the current retained records.'));return;}
  panel.append(el('p',budgetFreshness(report,state).label+' · '+when(report.inspectedAt),'metric-note'));
  if(report.status==='not_initialized'){panel.append(empty('Shared accounting is not initialized','No admission ledger exists here. A reviewed mission budget is configuration, not a reservation or measured balance. Setup requires the separate owner-reviewed onboarding procedure.'));return;}
  if(report.status==='unavailable'){panel.append(callout('Accounting is unavailable',report.detail||'No trustworthy balance is shown. Ask the brain/operator to reconcile the saved accounting.'));return;}
  panel.append(el('p',report.boundary,'muted'));
  if(!report.allocations.length)panel.append(empty('No phase allocation for this project','No phase allowance is inferred from configuration. Other projects’ allocations are not shown or borrowed.'));
  report.allocations.forEach((row,index)=>{
    const group=el('section',null,'budget-phase'),balance=budgetBalance(row,report,state);
    group.append(el('h3',row.phaseId||'Unbound phase allocation'),el('p',`${row.closed?'Closed allocation':'Recorded allocation'} · ${row.heldClaims} held / ${row.recordedClaims} task attempts · oldest sample: ${when(row.observedAt)}`,'muted'));
    if(row.issues.length)group.append(el('p','Needs evidence: '+row.issues.map(i=>budgetIssues[i]||'Accounting needs reconciliation').join('; '),'budget-warning'));
    group.append(table(['Accounting component','Tokens','Meaning'],[
      ['Phase allowance',num(row.limits.tokenBudget),'Recorded limit; not an account wallet'],
      ['Observed cumulative usage',row.observedTokens===null?'Unknown':num(row.observedTokens),'Recorded brain, worker and review charges; coverage may be incomplete'],
      ['Held task estimates',num(row.heldTokens),'Reserved for owned work; may overlap observed partial usage'],
      ['Settled, not yet incorporated',num(row.unincorporatedSettledTokens),'Actual charges retained until a complete sample includes the settlement'],
      ['Checkpoint reserve',num(row.checkpointReserveTokens),'Allowance kept for review and safe handoff'],
      ['Balance after recorded charges',balance===null?'Unknown':num(balance),balance===null?'Incomplete, stale or changed evidence; do not infer available tokens':balance<0?'Recorded charges exceed the allowance; not permission to continue':'Historical arithmetic only; effect context and authority are not checked']
    ]));
    const details=el('details',null,'budget-details'),key=workspaceId+':'+row.allocationId;details.open=budgetDetails.get(key)||false;
    details.append(el('summary','Accounting limits and interpretation'),el('p',`Recorded limits: ${row.limits.maxParallelTasks} parallel tasks; ${row.limits.maxTasks} total attempts. Closed attempts remain counted. Cached input and reasoning are subsets, not extra token charges.`),el('p','Formula: phase allowance − observed usage − held estimates − unincorporated settlement charges − checkpoint reserve. Unknown coverage suppresses the balance. Separate phases are not summed into a spendable total.'),el('p','A new generation does not reset same-phase accounting. To resolve gaps, ask the designated brain to obtain complete usage evidence and reconcile the existing allocation. This view cannot raise a budget or release ownership.'));
    details.addEventListener('toggle',()=>budgetDetails.set(key,details.open));group.append(details);panel.append(group);
  });
  const account=report.account;
  if(account){
    panel.append(section('Shared Codex account windows','Account-wide percentages, not phase tokens or subscription charges.'));
    const stale=budgetFreshness(report,state).stale||!account.expiresAt||Date.now()/1000>account.expiresAt;
    panel.append(el('p',`${stale?'Earlier evidence · inspect again':account.status==='headroom_observed'?'Headroom was recorded':'Account evidence needs attention'} · observed ${when(account.observedAt)}`,'muted'));
    panel.append(table(['Account window','Remaining at observation','Reset recorded'],['short','long'].map(name=>{const row=account.windows?.[name];return [name==='short'?'Five-hour window':'Weekly window',row?num(row.remainingPercent)+'%':'Unknown',row?when(row.resetsAt):'Unknown'];})));
    if(account.issues.length)panel.append(el('p','Account issues: '+account.issues.map(i=>i.replaceAll('_',' ')).join('; '),'budget-warning'));
  }
  if(report.sharedCapacity)panel.append(el('p',`Shared managed capacity: ${report.sharedCapacity.recordedHeldClaims} held claims / ${report.sharedCapacity.maximumParallelTasks} configured parallel limit. Recorded counts only; excludes quarantined legacy owners and unmanaged activity. This is not free capacity.`,'metric-note'));
  panel.append(button('Download this accounting snapshot',()=>downloadBudget(report)));
}
async function inspectBudget(){
  const wid=workspaceId,generation=workspaceGeneration;
  if(!wid||budgetPending.has(wid)||!connected)return;
  const identity={};budgetPending.set(wid,identity);render();
  try{
    const result=await api('/api/budget');
    if(workspaceId!==wid||workspaceGeneration!==generation||result.workspaceId!==wid)return;
    budgetReports.set(wid,result);
  }catch(error){if(!error.workspaceChanged&&workspaceId===wid&&workspaceGeneration===generation){budgetReports.delete(wid);showNotice('Accounting read failed. No balance was refreshed and no state was changed. '+error.message,true);}}
  finally{if(budgetPending.get(wid)===identity)budgetPending.delete(wid);if(workspaceId===wid&&workspaceGeneration===generation&&view==='usage')render();}
}
function downloadBudget(report){
  const blob=new Blob([JSON.stringify(report,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');
  a.href=url;a.download='budget-'+report.workspaceId+'.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
