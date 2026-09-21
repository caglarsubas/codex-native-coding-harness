"use strict";
Object.assign(titles,{phaseCheckpoints:['Phase checkpoints','Inspect what was saved before deciding what comes next.']});
const checkpointHistory=new Map(),checkpointReports=new Map(),checkpointPending=new Map(),checkpointDetails=new Map();
const checkpointContext={matches_recorded_checkpoint:'Matches the recorded parked checkpoint',workspace_changed:'Workspace evidence changed · prepare a new report',superseded:'Earlier report · no longer the latest',checkpoint_unavailable:'Current parked checkpoint cannot be verified',not_checked:'Evidence could not be inspected'};
function checkpointFreshness(result,snapshot,now=Date.now()/1000){
  if(!result)return 'Not inspected in this tab';
  if(result.workspaceRevision!==snapshot.meta.revision)return 'Workspace changed since inspection · inspect again';
  if(now<result.inspectedAt||now-result.inspectedAt>60)return 'Earlier inspection · inspect again';
  return 'Inspection of saved local evidence · not live activity';
}
function checkpointSummary(root){
  if(!state.workspace)return;
  const panel=el('section',null,'mission-summary');
  panel.append(el('h2','Phase checkpoints'),el('p','Read saved outcomes, remaining work and evidence gaps. Viewing a report does not approve the next phase.','muted'),button('Open phase checkpoints',()=>navigateView('phaseCheckpoints')));root.append(panel);
}
function checkpointDisclosure(parent,key,label,body){
  const details=el('details'),id=workspaceId+':'+key;details.open=checkpointDetails.get(id)||false;
  details.append(el('summary',label),body);details.addEventListener('toggle',()=>checkpointDetails.set(id,details.open));parent.append(details);
}
function phaseCheckpointsView(root){
  if(!state.workspace){root.append(empty('Select a registered workspace','Checkpoint reports belong to one workspace.'));return;}
  const body=el('div',null,'phase-checkpoint-view');root.append(body);root=body;
  const history=checkpointHistory.get(workspaceId),result=checkpointReports.get(workspaceId),pending=checkpointPending.has(workspaceId);
  const intro=el('section',null,'run-inspection');intro.setAttribute('aria-label','Saved phase checkpoint inspection');
  intro.append(el('p',state.workspace.name+' · READ ONLY','eyebrow'),el('h2','What was preserved at the checkpoint?'),el('p','Load the saved versions, then inspect a report and its retained evidence. This does not observe native activity, measure usage, prepare a report or continue development.'));
  const load=button(pending?'Reading saved evidence…':history?'Reload report history':'Load report history',()=>loadPhaseCheckpoints(),'primary');load.disabled=pending||!connected;intro.append(load);root.append(intro);
  if(!history){root.append(empty('No report history loaded','Opening this page does not inspect or change the workspace. Load history when you want to review its saved phase reports.'));return;}
  root.append(el('p',checkpointFreshness(history,state)+' · '+when(history.inspectedAt),'muted'));
  if(history.status==='history_limit'){root.append(callout('History exceeds the inspection limit',`${history.total} reports are retained; the inspection limit is ${history.limit}. No partial history is shown. Ask the operator for a bounded history migration; no records were removed.`));return;}
  if(history.unavailable)root.append(callout('Some report metadata is unavailable',`${history.unavailable} of ${history.total} records have missing or invalid metadata. Their creation order cannot be established. Ask the brain/operator to restore the retained evidence; reloading cannot repair it.`));
  if(history.total&&!history.latestAvailable)root.append(callout('Latest report is unavailable','The latest report pointer does not identify a readable entry in this workspace. Earlier reports cannot stand in for it.'));
  if(!history.total){root.append(empty('No saved phase reports','A parked brain checkpoint is not yet a phase report. The designated brain must prepare the report from an exact parked run checkpoint. This page cannot create it or resume work.'));return;}
  root.append(section('Saved versions','Oldest first by report save time. Versions are per run; every row is historical until explicitly inspected.'));
  const versions=el('ol',null,'checkpoint-history');
  for(const row of history.reports){
    const isLatest=history.latest?.reportHash===row.reportHash&&history.latest?.artifactId===row.artifactId;
    const entry=el('li'),info=el('div'),control=el('div',null,'checkpoint-version-action');
    const inspect=button('Inspect report · v'+row.version,()=>loadPhaseCheckpoints(row));inspect.disabled=pending||!connected;
    info.append(el('h3',row.phaseTitle),el('p',`${row.phaseId} · generation ${row.generation}`,'muted'),el('p','Report saved: '+when(row.retainedAt),'subline'),el('p','Checkpoint: '+when(row.checkpointAt),'subline'));
    control.append(el('span',isLatest?'Latest saved report':'Earlier saved report','subline'),inspect);
    entry.append(info,control);versions.append(entry);
  }root.append(versions);
  if(result)checkpointReportView(root,result);
}
function checkpointReportView(root,result){
  root.append(section('Inspected report',when(result.inspectedAt)),el('p',checkpointFreshness(result,state),'muted'));
  if(result.status!=='intact'){root.append(callout('Report evidence unavailable',result.detail));return;}
  const r=result.report,s=r.summary;
  root.append(el('h3',r.phase.title+' · generation '+r.generation+' · v'+result.version),el('p','At inspection: '+checkpointContext[result.contextStatus],'checkpoint'),el('p',result.boundary,'muted'));
  root.append(table(['Recorded outcome','Count / state'],[['Declared tasks',num(s.declaredTasks)],['Unfinished declared tasks',num(s.unfinishedDeclaredTasks)],['Accepted worker results',num(s.recordedAcceptedResults)],['Results needing changes',num(s.recordedChangesRequired)],['Workers without result review',num(s.unreviewedWorkers)],['Other retained workers outside this phase report',num(s.otherRetainedWorkers)],['Pending controls at checkpoint',num(s.pendingControlCount)],['Phase acceptance','Not established'],['Measured phase tokens','Unknown · shared phase usage must be checked separately']]));
  root.append(el('p',`Checkpoint saved: ${when(r.checkpointAt)}. Report saved: ${when(r.retainedAt)}. Inspecting does not refresh either timestamp.`,'muted'));
  const criteria=el('div');criteria.append(el('p',r.phase.objective),el('h3','Required owner checkpoint'),el('p',r.phase.checkpoint),el('h3','Recorded stop reasons'),el('p',r.stopReasons.length?r.stopReasons.join(' · '):'No specific stop reason recorded. This is not phase completion.'),el('h3','Brain report note'),el('p',r.note));
  checkpointDisclosure(root,result.reportHash+':scope','Phase outcome, checkpoint and saved note',criteria);
  const limits=el('div');limits.append(el('p','Configured limits are not measured consumption, reserved capacity or subscription charges.','muted'),table(['Configured limit','Value'],[['Parallel tasks',num(r.limits.maxParallelTasks)],['Phase tasks',num(r.limits.maxTasks)],['Phase tokens',num(r.limits.tokenBudget)],['Included checkpoint reserve',num(r.limits.checkpointReserveTokens)]]),button('Review token usage',()=>navigateView('usage')));
  checkpointDisclosure(root,result.reportHash+':limits','Limits and usage boundary',limits);
  const tasks=el('div');
  if(!r.tasks.length)tasks.append(el('p','No phase-declared tasks in this saved report. This does not establish that native tasks are idle.'));
  for(const task of r.tasks){
    tasks.append(el('h3',task.queueId),el('p',`${task.repository} · recorded queue status: ${task.status}${task.held?' · held':''}`));
    if(!task.workers.length)tasks.append(el('p','No phase-owned worker result retained for this task.','muted'));
    for(const worker of task.workers){
      tasks.append(el('p',`Worker ${worker.id} · ${worker.status} · ${worker.review?worker.review.outcome:'No result review'}`));
      if(worker.review){const review=worker.review;tasks.append(el('p','Review recorded: '+when(review.recordedAt)+' · Commit: '+review.commit,'mono'),table(['Evidence axis','Recorded result'],Object.entries(review.axes)),el('p','Criterion results (contract order): '+review.criteria.join(' · ')),el('p','Preservation: '+review.preservation));}
    }
  }
  checkpointDisclosure(root,result.reportHash+':tasks','Task results and separate evidence axes',tasks);
  const proof=el('div');proof.append(el('p','Report SHA-256: '+result.reportHash,'mono'),el('p','Run SHA-256: '+r.runHash,'mono'),el('p','Checkpoint SHA-256: '+r.checkpointHash,'mono'),el('pre',JSON.stringify(r,null,2)));
  checkpointDisclosure(root,result.reportHash+':bindings','Exact saved report and bindings',proof);
  const artifactKnown=state.observations?.artifacts.some(a=>a.id===result.artifactId);
  const actions=el('div',null,'inline-actions');
  if(artifactKnown)actions.append(button('Read retained report artifact · v'+result.version,()=>navigateView('artifacts',result.artifactId)));
  else root.append(el('p','Report artifact is outside the current library snapshot. Reload dashboard state before navigating to it.','muted'));
  const again=button('Inspect this report again',()=>loadPhaseCheckpoints(result));again.disabled=checkpointPending.has(workspaceId)||!connected;actions.append(again);root.append(actions);
  root.append(el('p','To continue: inspect remaining work and evidence with the designated brain. Next-phase review, release and autonomous Play are not available from this view.','muted'));
}
async function loadPhaseCheckpoints(row=null){
  const wid=workspaceId,generation=workspaceGeneration;
  if(!wid||checkpointPending.has(wid)||!connected)return;
  const identity={};checkpointPending.set(wid,identity);render();
  try{
    const query=row?'?'+new URLSearchParams({reportHash:row.reportHash,artifactId:row.artifactId}):'';
    const result=await api('/api/phase-checkpoints'+query);
    if(workspaceId!==wid||workspaceGeneration!==generation||result.workspaceId!==wid)return;
    if(row)checkpointReports.set(wid,result);
    else{checkpointHistory.set(wid,result);checkpointReports.delete(wid);}
  }catch(error){if(!error.workspaceChanged&&workspaceId===wid&&workspaceGeneration===generation){if(row)checkpointReports.delete(wid);showNotice('Checkpoint read failed. No state was changed. '+error.message,true);}}
  finally{if(checkpointPending.get(wid)===identity)checkpointPending.delete(wid);if(workspaceId===wid&&workspaceGeneration===generation&&view==='phaseCheckpoints')render();}
}
