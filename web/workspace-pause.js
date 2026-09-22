"use strict";
let dispatchDetailsOpen=false;
function workspacePausePresentation(snapshot, now=Date.now()/1000) {
  const pause=snapshot.workspacePause||{}, control=snapshot.meta.brainControl||{}, activity=snapshot.brainActivity||{};
  const stopped=control.desired==='stopped', saved=pause.status==='checkpoint_saved';
  const legacySaved=stopped&&control.phase==='parked'&&control.protocol!=='workspace_pause_v1';
  const observed=!!(saved && !pause.blockers?.length && now<=pause.validUntil && !snapshot.meta.controller
    && activity.fresh && activity.status==='idle' && activity.observedAt>=pause.checkpointAt
    && activity.observedAt<=now && now-activity.observedAt<=120);
  const pending=control.phase==='resume_requested';
  return {label:observed?'Paused at checkpoint':saved?'Checkpoint saved · activity not confirmed':legacySaved?'Earlier brain checkpoint saved':stopped?'Pausing safely':pending?'Brain resume requested':'Project control',
    button:stopped?(saved||legacySaved?'Resume brain from checkpoint':'Pausing safely…'):'Pause project',
    kind:stopped?'brain_resume':'brain_stop', disabled:!snapshot.meta.brainId || (stopped&&!saved&&!legacySaved),
    observedPaused:observed,
    detail:observed?'Workers have checkpoint evidence and the brain was observed idle. Ownership is retained.'
      :saved?'The safe checkpoint is retained. Current native inactivity is not fully confirmed; saved evidence does not become fresh on refresh.'
      :legacySaved?'This earlier brain checkpoint predates project-wide descendant checks. Resume remains explicit; no project-wide inactivity is inferred.'
      :stopped?'New work is fenced. The brain continues safety-only coordination until tasks, runner and schedule reach a safe checkpoint.'
      :pending?'The existing brain will recover its checkpoint. Worker dispatch remains unchanged; this is not autonomous Play.'
      :'Pause the brain and its tasks at safe checkpoints. Running tools finish their bounded step; no process is killed.'};
}
function workspacePausePanel(root) {
  if(!state.workspace)return;
  const presentation=workspacePausePresentation(state), pause=state.workspacePause||{};
  const panel=el('section',null,'workspace-pause');panel.setAttribute('aria-label','Project pause progress');
  panel.append(el('p',state.workspace.name,'eyebrow'),el('h2',presentation.label),el('p',presentation.detail));
  if(state.meta.brainControl?.desired!=='stopped') {
    const wake=button('Wake brain now',()=>command('brain_resume'));
    wake.disabled=!connected||busy||!state.meta.brainId||state.meta.brainControl?.phase==='resume_requested';panel.append(wake);
  }
  if(pause.requestedAt) {
    const inventory=pause.observedTasks==null?'Native task inventory not yet observed':`${num(pause.observedTasks)} observed task${pause.observedTasks===1?'':'s'} including descendants`;
    panel.append(el('p',`Requested ${when(pause.requestedAt)} · ${num(pause.retainedWorkers)} retained worker${pause.retainedWorkers===1?'':'s'} · ${inventory}`,'muted'));
    const blockers=pause.blockers||[];
    if(blockers.length) {
      const list=el('ul',null,'pause-blockers');
      for(const item of blockers.slice(0,12)) {
        const row=el('li');row.append(el('span',item.detail));
        if(item.threadId)row.append(el('span','Task '+item.threadId,'subline'));
        if(item.workerId)row.append(el('span','Worker '+item.workerId,'subline'));
        list.append(row);
      }
      panel.append(list);
      if(blockers.length>12)panel.append(el('p',`${blockers.length-12} further checks are listed in the brain inbox.`,'muted'));
    } else if(pause.readyToPark)panel.append(el('p','Worker and schedule checks are satisfied. The brain still needs to retain the combined checkpoint and finish its turn.'));
    panel.append(button('Inspect workers & evidence',()=>navigateView('workers')));
    const checkpoint=state.meta.brainControl?.checkpoint;
    if(checkpoint) {
      panel.append(el('p',checkpoint.at<pause.requestedAt?'Previous checkpoint · does not complete this Pause':'Retained checkpoint artifacts','muted'));
      decisionArtifacts(panel,checkpoint.artifactIds);
    }
  }
  const advanced=el('details',null,'coverage-details');advanced.open=dispatchDetailsOpen;
  advanced.addEventListener('toggle',()=>{dispatchDetailsOpen=advanced.open;});
  advanced.append(el('summary','Advanced: worker dispatch only'),el('p','Holding dispatch prevents new workers, but does not stop the brain or checkpoint existing tasks. Resume brain and autonomous Play are separate.'));
  const dispatch=dispatchPresentation(state.meta,state.commands), hold=button(dispatch.button,()=>command(state.meta.paused?'resume':'pause'));
  hold.disabled=!connected||busy||dispatch.disabled||(!state.meta.paused?false:!!state.admission?.dispatchBlocked);
  advanced.append(hold);
  if(state.admission?.dispatchBlocked)advanced.append(el('p',state.admission.reason,'muted'));
  panel.append(advanced);root.append(panel);
}
