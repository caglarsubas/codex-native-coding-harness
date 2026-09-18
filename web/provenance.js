"use strict";
let provenancePending=false;
const runtimeLabels={matching_snapshot:'Matching source snapshot',source_changed:'Runtime files changed',revision_changed:'Checkout revision changed',unverified_workspace:'Unverified working copy',unknown:'Runtime provenance unknown'};

function openRuntimeProvenance() {
 openReadiness();
 const target=document.getElementById('runtime-provenance');
 if(target){target.focus({preventScroll:true});target.scrollIntoView({block:'start'});}
}

function runtimeSummary(root) {
 const d=state.provenance;if(!d)return;
 const row=el('div',null,'observation-toolbar');
 row.append(el('span','Server-start checkout '+(d.startup.commit?.slice(0,12)||'unknown'),'metric-note'),badge(runtimeLabels[d.status]),button('Inspect runtime provenance',openRuntimeProvenance));root.append(row);
}

async function refreshProvenance(remote) {
 if(provenancePending||!connected)return;
 provenancePending=true;render();
 try{
  await api('/api/provenance',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({remote})});
  showNotice(remote?'Checking the configured GitHub default branch. No fetch, pull or restart.':'Inspecting local runtime source. No network or restart.');await refresh();
 }catch(error){showNotice(error.message,true);}
 finally{provenancePending=false;render();}
}

function runtimeProvenance(root) {
 const d=state.provenance;if(!d)return;
 const heading=section('Runtime provenance','A merged PR does not identify the code in a running process.');heading.id='runtime-provenance';heading.tabIndex=-1;root.append(heading);
 const controls=el('div',null,'observation-toolbar');
 const local=button('Inspect runtime locally',()=>refreshProvenance(false));
 const remote=button('Check GitHub revision',()=>refreshProvenance(true));
 local.disabled=remote.disabled=provenancePending||d.job?.status==='running';controls.append(local,remote);root.append(controls);
 root.append(el('p',runtimeLabels[d.status],'metric-note'));
 if(d.job?.status==='running')root.append(el('p','Inspection running…','metric-note'));
 if(d.job?.status==='complete')root.append(el('p','Inspection completed · '+when(d.job.finishedAt),'metric-note'));
 if(d.job?.status==='failed')root.append(callout('Inspection unavailable',d.job.error));
 const sourceLabel=s=>s.status!=='observed'?'Unavailable':s.dirty?'Dirty / unverified':'Clean at observation';
 root.append(table(['Evidence boundary','Revision / state','Observed'],[
  ['Server-start checkout',textCell(d.startup.commit?.slice(0,12)||'Unknown',sourceLabel(d.startup)),when(d.startedAt)],
  ['Checkout now',textCell(d.current.commit?.slice(0,12)||'Unknown',sourceLabel(d.current)),when(d.current.at)+(d.localFresh?'':' · stale')],
  ['GitHub default branch',textCell(d.remote.commit?.slice(0,12)||'Not observed',d.remote.branch?d.remote.repository+' · '+d.remote.branch:d.remote.status.replaceAll('_',' ')),when(d.remote.at)+(d.remoteFresh?'':' · not current')]
 ]));
 if(d.remote.reason)root.append(el('p',d.remote.reason,'metric-note'));
 if(d.remote.status==='observed'&&d.current.githubRepository!==d.remote.repository)root.append(el('p','The retained GitHub observation is for another origin. Check the current configured origin explicitly before comparing revisions.','metric-note'));
 const comparison=value=>value===true?'Same clean commit':value===false?'Different commit':'Unverified';
 root.append(el('p','Server start vs GitHub: '+comparison(d.startupMatchesRemote)+'. Checkout vs GitHub: '+comparison(d.checkoutMatchesRemote)+'.','metric-note'));
 if(d.restartRecommended)root.append(callout('Manual restart recommended','The current checkout differs from the server-start observation. Review and preserve local edits, then restart the dashboard and reload this page. Restarting rotates the private login link; it does not approve work or change dispatch.'));
 else if(d.status==='unverified_workspace')root.append(el('p','Uncommitted work was present at startup or inspection. A commit ID alone cannot identify that source. Preserve and review it before restarting from a clean revision.','metric-note'));
 if(!d.localFresh)root.append(el('p','Inspect locally again: checkout observations expire after 15 minutes. GitHub is checked only on explicit request.','metric-note'));
 root.append(el('p',d.limits,'metric-note'));
}
