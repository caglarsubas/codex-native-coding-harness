"use strict";
Object.assign(titles,{runReadiness:['Run readiness','What is configured, what needs evidence, and what still needs implementation.']});
const runInspections=new Map(),runInspectionPending=new Map(),runInspectionDetails=new Map();
const runCheckTitles={mission_binding:'Current mission binding',owner_review:'Exact owner review',brain_identity:'Designated brain',execution_mode:'Development approval mode',project_mappings:'Native project mappings',pause_checkpoint:'Pause checkpoint',controller_idle:'Recorded controller ownership',platform_baseline:'Platform inventory & usage evidence',packet_coverage:'Packet inspection coverage',run_activation:'Run activation & recovery',phase_release:'Phase approval & release',native_admission:'Resource & token admission',task_policy:'Task operations & execution settings',native_pilot:'Supervised native acceptance',workspace_changed:'Concurrent project change'};
function runInspectionState(report,snapshot,now=Date.now()/1000){
  if(!report)return {label:'Not inspected',stale:false};
  const changed=report.workspaceRevision!==snapshot.meta.revision;
  return {label:changed?'Project changed · inspect again':now-report.generatedAt>60||now<report.generatedAt?'Earlier inspection · inspect again':'Recorded inspection · not clearance',stale:changed||now-report.generatedAt>60||now<report.generatedAt};
}
function runInspectionDisclosure(parent,key,label,content){
  const details=el('details'),id=workspaceId+':'+key;details.open=runInspectionDetails.get(id)||false;
  details.append(el('summary',label),content);details.addEventListener('toggle',()=>runInspectionDetails.set(id,details.open));parent.append(details);
}
function runReadinessView(root){
  if(!state.workspace){root.append(empty('Select a registered project','Run readiness belongs to one project and its current mission.'));return;}
  if(typeof observerControlPanel==='function')observerControlPanel(root);
  const report=runInspections.get(workspaceId),pending=runInspectionPending.has(workspaceId);
  const intro=el('section',null,'run-inspection');intro.setAttribute('aria-label','Run readiness inspection');
  intro.append(el('p',state.workspace.name+' · READ ONLY','eyebrow'),el('h2','Inspect before enabling Play'),
    el('p','Compare the reviewed mission, prepared packet paths and retained platform evidence. This does not start a run, collect fresh native state, reserve tokens or change approvals.'));
  const inspect=button(pending?'Inspecting recorded state…':report?'Inspect again':'Inspect run readiness',inspectRunReadiness,'primary');inspect.disabled=pending||!connected;
  intro.append(inspect);root.append(intro);
  if(!report){root.append(empty('No inspection in this tab','Inspect explicitly to see owner setup, evidence gaps and missing platform controls separately. Opening this view does not scan or change state.'));return;}
  const freshness=runInspectionState(report,state);
  root.append(el('p',freshness.label+' · '+when(report.generatedAt),'muted'));
  root.append(callout('Autonomous Play remains unavailable','A green individual check is not permission to run. Platform-development items below cannot be resolved by approving the mission again.'));
  const mission=report.mission;
  if(mission.phaseTitle){root.append(section(mission.phaseTitle,`Mission v${mission.version} · ${mission.status}`),el('p','Mandatory owner checkpoint: '+mission.checkpoint));}
  if(mission.limits){const a=mission.limits;root.append(table(['Proposed limit','Configured value'],[['Parallel tasks',num(a.maxParallelTasks)],['Total phase tasks',num(a.maxTasks)],['Phase tokens',num(a.tokenBudget)],['Included checkpoint reserve',num(a.checkpointReserveTokens)]]),el('p','Configuration only. These are not reserved tokens, provider limits or a spend estimate.','muted'));}
  for(const [group,title,description] of [['setup','Owner setup','Configuration you can review without starting work.'],['evidence','Evidence & coordination','The brain or operator must resolve these from actual observations.'],['implementation','Platform development remaining','Missing controls in the software, not another owner approval.']]){
    root.append(section(title,description));const list=el('div',null,'run-checks'),passed=el('div',null,'run-checks');
    const checks=report.checks.filter(c=>c.group===group);
    for(const check of checks){
      const row=el('section',null,'run-check');row.append(el('h3',runCheckTitles[check.code]||'Recorded check'),badge(check.status.replaceAll('_',' ')),el('p',check.detail));
      if(check.status!=='satisfied'){row.append(el('p',check.nextAction,'muted'));if(group!=='implementation'&&ROUTE_VIEWS.includes(check.view))row.append(button('Open '+(titles[check.view]?.[0]||'related view'),()=>navigateView(check.view)));}
      (check.status==='satisfied'?passed:list).append(row);
    }root.append(list);
    const count=checks.filter(c=>c.status==='satisfied').length;
    if(count)runInspectionDisclosure(root,'satisfied:'+group,`${count} recorded check${count===1?'':'s'} satisfied · inspect evidence`,passed);
  }
  root.append(section('Prepared packets','Path containment and legacy checks are separate from phase execution authority.'));
  root.append(el('p',`${report.coverage.inspectedPackets} inspected · ${report.coverage.omittedPackets} omitted. Completed/dispatched packets are not candidates.`,'muted'));
  if(!report.packets.length)root.append(el('p','No prepared candidates were recorded. An empty queue is not a readiness or native-idle claim.'));
  for(const packet of report.packets){
    const body=el('div');body.append(el('p',`Path scope: ${packet.pathScope.replaceAll('_',' ')} · Legacy eligibility: ${packet.legacyEligibility.replaceAll('_',' ')}`));
    taskContractSummary(body,packet.taskContract);
    const issues=el('ul');for(const issue of packet.issues)issues.append(el('li',issue.detail));body.append(issues,button('Review approved queue',()=>navigateView('queue')));
    runInspectionDisclosure(root,'packet:'+packet.id,packet.repository+' / '+packet.packetId,body);
  }
  const proof=el('div',null,'run-proof');proof.append(el('p','Diagnostic binding only. Neither hash is an activation token; platform state may change immediately.','muted'),
    el('p','Report SHA-256: '+report.reportHash,'mono'),el('p','Candidate binding: '+(report.candidateHash||'Not available until exact current mission review is valid.'),'mono'),
    el('pre',JSON.stringify(report,null,2)));
  runInspectionDisclosure(root,'report','Inspect exact JSON report and bindings',proof);
  root.append(button('Download this inspection',()=>downloadRunInspection(report)));
}
function downloadRunInspection(report){
  const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)+'\n'],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download='run-readiness-'+report.workspaceId+'.json';link.hidden=true;
  document.body.append(link);try{link.click();}finally{link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
}
async function inspectRunReadiness(){
  const wid=workspaceId,generation=workspaceGeneration;
  if(!wid||runInspectionPending.has(wid)||!connected)return;
  const identity={};runInspectionPending.set(wid,identity);render();
  try{
    const report=await api('/api/run-readiness');
    if(workspaceId===wid&&workspaceGeneration===generation&&report.workspaceId===wid)runInspections.set(wid,report);
  }catch(error){if(!error.workspaceChanged&&workspaceId===wid)showNotice('Inspection failed. No run or approval was created. '+error.message,true);}
  finally{if(runInspectionPending.get(wid)===identity)runInspectionPending.delete(wid);if(workspaceId===wid&&view==='runReadiness')render();}
}
