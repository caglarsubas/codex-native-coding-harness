"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag,text=''){this.tag=tag;this.text=text;this.children=[];this.disabled=false;}
  append(...children){this.children.push(...children);}
  setAttribute(name,value){this[name]=value;}
  addEventListener(name,callback){this['on'+name]=callback;}
}
const messages=[],sent=[],routes=[];
const box={Map,Set,JSON,Math,String,crypto:{randomUUID:()=>`request-${sent.length}`},setTimeout:()=>1,workspaceId:'alpha',busy:false,connected:true,csrf:'fixture',selected:null,
  document:{getElementById:()=>null},
  state:{standard:{available:true,contextHash:'h',boundary:'Partial observations',catalog:{models:[{model:'native',efforts:['low']}]},run:null},mission:null},
  el:(tag,text)=>new Element(tag,text),button:(text,callback)=>Object.assign(new Element('button',text),{click:callback}),
  section:(text)=>new Element('h2',text),table:(heads,rows)=>new Element('table',JSON.stringify(rows)),
  callout:(a,b)=>new Element('p',a+' '+b),num:String,when:String,textCell:(a,b)=>a+' '+b,
  missionDocument(){},render(){},updateWorkspaceSelector(){},refresh:async()=>{},showNotice:(message)=>messages.push(message),navigateView:(route)=>routes.push(route),
  api:async(path,opts)=>{sent.push({path,body:JSON.parse(opts.body)});if(path.endsWith('preview'))return {preview:{operation:'play',contextHash:'h',brainAllowance:1,durationHours:8,expiresAt:Date.now()/1000+300},signature:'signed'};return {result:'Recorded'};}};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/journey.js','utf8'),box);vm.runInContext(fs.readFileSync('web/summaries.js','utf8'),box);vm.runInContext(fs.readFileSync('web/standard.js','utf8'),box);
box.commandPresentation=()=>({label:'Connection lost · request unresolved',detail:'Do not repeat Play.'});
const render=(mode)=>{const root=new Element('root');box.standardPanel(root,mode);return root;};
function all(root){return [root,...root.children.flatMap(x=>x instanceof Element?all(x):[])];}
(async()=>{
  let nodes=all(render());await nodes.find(n=>n.text==='Review Play').click();
  assert.equal(routes.at(-1),'roadmap','A signed Play preview opens its visible inspector section');
  assert.equal(sent[0].body.durationHours,24,'New Play suggests a 24-hour window');
  assert.equal(sent[0].body.brainAllowance,1,'A missing reviewed budget never fabricates a large allowance');
  box.state.mission={document:{spec:{phase:{durationHours:4},authority:{tokenBudget:100000}}}};
  await box.reviewStandardControl(box.state.standard,'play',null);
  assert.equal(sent.at(-1).body.durationHours,4,'Legacy/embed Play also uses the exact reviewed phase duration');
  box.state.mission=null;
  sent.pop(); // The additional duration regression is independent of later call-count assertions.
  nodes=all(render());let confirm=nodes.find(n=>n.text==='Confirm play');assert.equal(confirm.disabled,true);
  let check=nodes.find(n=>n.type==='checkbox');check.checked=true;check.onchange();assert.equal(confirm.disabled,false);
  box.workspaceId='beta';assert.ok(!all(render()).some(n=>n.text==='Confirm play'),'Project preview isolation');
  await confirm.click();assert.equal(sent.filter(s=>s.path.endsWith('confirm')).length,0,'Detached project control cannot submit');
  box.workspaceId='alpha';box.connected=false;assert.ok(all(render()).some(n=>n.text==='Review needs refreshing'));await confirm.click();assert.equal(sent.filter(s=>s.path.endsWith('confirm')).length,0);
  box.connected=true;box.state.standard.contextHash='changed';assert.ok(all(render()).some(n=>n.text==='Review needs refreshing'));await confirm.click();assert.equal(sent.filter(s=>s.path.endsWith('confirm')).length,0);box.state.standard.contextHash='h';
  box.workspaceId='alpha';await confirm.click();assert.equal(sent.filter(s=>s.path.endsWith('confirm')).length,1);
  box.state.standard.run={id:'run',status:'running',phaseId:'p',tasks:[],limits:{maxTasks:2,checkpointReserveTokens:10},brainUsageCoverage:'not_observed'};
  box.state.commands=[{id:'original-play',kind:'standard_play',createdAt:1,status:'queued',payload:{runId:'run'},notification:{nativeTurnStatus:'connection_lost'}}];
  const beforeLossInspection=sent.length;
  box.journeyAction('request');nodes=all(render('operations'));
  assert.ok(nodes.some(n=>n.id==='control-request-history'&&n.open),'Inspection opens the actual saved request history');
  assert.ok(nodes.some(n=>String(n.text).includes('original-play'))&&nodes.some(n=>n.text==='Connection lost · request unresolved'),'The original request ID and loss state are visible');
  assert.ok(nodes.some(n=>n.tag==='h2'&&n.text.includes('recorded running · connection unresolved')));
  assert.equal(sent.length,beforeLossInspection,'Inspection neither reconnects nor submits anything');
  box.workspaceId='other';assert.equal(all(render('operations')).find(n=>n.id==='control-request-history').open,false,'History disclosure is project isolated');box.workspaceId='alpha';
  box.state.commands=[];
  const activeRun=box.state.standard.run;box.state.standard.run=null;
  assert.ok(all(render('operations')).some(n=>n.id==='control-request-history'),'Pre-phase requests also have a real inspection target');
  box.state.standard.run=activeRun;
  box.state.standard.observedTokens=null;nodes=all(render());assert.ok(nodes.some(n=>String(n.text).includes('Not observed')));
  assert.ok(nodes.some(n=>n.text==='Pause at safe checkpoint'));
  assert.ok(nodes.some(n=>String(n.text).includes('manual (default)')));
  box.state.standard.run.limits.mergeMode='brain_exact_pr_v1';
  for(const status of ['prepared','issued','uncertain','merged','not-merged']){
    box.state.standard.run.merges=[{requestId:'m',status,prUrl:'https://github.com/fixture/project/pull/7',headSHA:'a'.repeat(40),bindingHash:'b'.repeat(64)}];
    nodes=all(render());assert.ok(nodes.some(n=>String(n.text).includes(status)));
    assert.ok(nodes.some(n=>String(n.text).includes('requires independent checks')));
    assert.ok(!nodes.some(n=>n.tag==='button'&&String(n.text).includes('Merge')),'Dashboard cannot send a merge');
  }
  box.state.standard.run.status='stopping';assert.equal(all(render()).find(n=>n.text==='Pause at safe checkpoint').disabled,true);
  box.state.standard.run.status='paused';assert.ok(all(render()).some(n=>n.text==='Review Resume'));
  box.state.standard.run.usageGuardVersion=1;
  box.state.standard.measuredUsage={tokens:{input_tokens:100,cached_input_tokens:50,output_tokens:20,reasoning_output_tokens:5,total_tokens:120},
    collectedAt:1,coverage:'gapped',gaps:['missing_prefix'],remainingMeasured:null};
  assert.ok(all(render()).some(n=>n.tag==='table'&&n.text.includes('Measured remaining')&&n.text.includes('Unknown')));
  const usageOnly=all(render('usage')),tasksOnly=all(render('tasks'));
  assert.ok(usageOnly.some(n=>n.tag==='table'&&n.text.includes('Measured remaining')));
  assert.ok(!usageOnly.some(n=>n.text==='Review Resume'||n.text==='Review brain handoff'));
  assert.ok(!tasksOnly.some(n=>n.tag==='table'&&n.text.includes('Measured remaining')));
  assert.ok(!tasksOnly.some(n=>n.text==='Review Resume'||n.text==='Review brain handoff'));
  box.state.standard.nativeObservation={reportHash:'h',observedAt:1,issues:[],samples:[
    {taskId:'pending',nativeStatus:'unknown',trackedTerminals:'unknown',trackedTerminalCount:null,issues:['native_identity_unconfirmed']}]};
  const nativeNodes=all(render('tasks'));
  assert.ok(nativeNodes.some(n=>n.tag==='summary'&&n.text==='Details · Registered native task check'));
  assert.ok(nativeNodes.some(n=>String(n.text).includes('historical')&&String(n.text).includes('evidence gaps remain')));
  assert.ok(nativeNodes.some(n=>n.tag==='table'&&n.text.includes('Unknown')),'Missing terminal measurements are not zero');
  assert.ok(nativeNodes.some(n=>String(n.text).includes('not complete descendant coverage')));
  assert.ok(!nativeNodes.some(n=>n.tag==='button'&&String(n.text).includes('native task check')),'Rendering never collects native evidence');
  const nativeDetails=nativeNodes.find(n=>n.tag==='details'&&n.children.some(c=>c.text==='Details · Registered native task check'));
  assert.equal(nativeDetails.open,false,'Native details start collapsed');
  nativeDetails.isConnected=true;nativeDetails.open=true;nativeDetails.ontoggle();
  assert.equal(all(render('tasks')).find(n=>n.tag==='details'&&n.children.some(c=>c.text==='Details · Registered native task check')).open,true,'Details remain open across refresh');
  box.workspaceId='another-project';
  assert.equal(all(render('tasks')).find(n=>n.tag==='details'&&n.children.some(c=>c.text==='Details · Registered native task check')).open,false,'Disclosure state is project isolated');
  box.workspaceId='alpha';
  box.state.brainHandoff={handoff:null,readiness:{canPrepare:true,canFinalize:false,blockers:[]}};
  const priorApi=box.api;
  box.api=async(path,opts)=>{
    if(path.endsWith('/brain-handoff/preview')){sent.push({path,body:JSON.parse(opts.body)});return {preview:{expiresAt:100},package:{kind:'fixture'},signature:'signed'};}
    if(path.endsWith('/brain-handoff/confirm')){sent.push({path,body:JSON.parse(opts.body)});return {result:'Prepared'};}
    return priorApi(path,opts);};
  await all(render()).find(n=>n.text==='Review brain handoff').click();
  nodes=all(render());const handoffConfirm=nodes.find(n=>n.text==='Confirm handoff preparation');
  assert.equal(handoffConfirm.disabled,true);
  const handoffBox=nodes.filter(n=>n.type==='checkbox').at(-1);handoffBox.checked=true;handoffBox.onchange();
  assert.equal(handoffConfirm.disabled,false);await handoffConfirm.click();
  assert.ok(sent.some(s=>s.path.endsWith('/brain-handoff/confirm')));
  box.state.brainNotification={status:'disabled'};
  box.state.brainHandoff={readiness:{canPrepare:false,canFinalize:false,blockers:[]},handoff:{status:'prepared',packageHash:'hash',oldBrainId:'old'}};
  nodes=all(render());
  assert.ok(nodes.some(n=>String(n.text).includes('notification is off')));
  assert.ok(nodes.some(n=>String(n.text).includes('do not confirm preparation again or use Resume')));
  box.state.brainHandoff={readiness:{canPrepare:false,canFinalize:false,blockers:['Fresh native task-list project membership required before rebinding']},handoff:{status:'received',packageHash:'hash',oldBrainId:'old',
    candidate:{taskId:'new',projectId:'native-a',hostId:'local',observation:'Owner observed native project'},
    receipt:{summary:'Exact package reviewed'},receiptEvidence:{source:'local_native_final_reply',observedAt:1}}};
  nodes=all(render());
  assert.ok(nodes.some(n=>String(n.text).includes('Native final reply observed')));
  assert.equal(nodes.find(n=>n.text==='Open replacement task in Codex').href,'codex://threads/new');
  assert.ok(nodes.some(n=>String(n.text).includes('separate exact native observation')));
  assert.ok(nodes.some(n=>String(n.text).includes('omission proves neither absence nor project membership')));
  assert.ok(nodes.some(n=>String(n.text).includes('one-shot: do not retry or create another candidate')));
  assert.ok(nodes.some(n=>String(n.text).includes('Refresh, Resume, or pinning/unpinning cannot supply')));
  assert.ok(!nodes.some(n=>n.text==='Review replacement receipt'));
  assert.ok(nodes.some(n=>String(n.text).includes('Fresh native task-list project membership required')));
  const handoff=box.state.brainHandoff.handoff;
  box.state.brainHandoff.readiness={canPrepare:false,canFinalize:true,blockers:[]};
  assert.ok(!all(render()).some(n=>n.text==='Review replacement receipt'),'Missing membership stays blocked even with optimistic readiness');
  handoff.nativeMembership={source:'codex.list_threads',taskId:'new',projectId:'native-a',hostId:'local',status:'idle',observedAt:Date.now()/1000};
  for(const change of [{status:'active'},{status:'unknown'},{taskId:'another'},{projectId:'other'},{hostId:'other'},{source:'candidate-claim'}]){
    const original={...handoff.nativeMembership};Object.assign(handoff.nativeMembership,change);
    assert.ok(!all(render()).some(n=>n.text==='Review replacement receipt'),`Membership ${JSON.stringify(change)} stays blocked`);
    handoff.nativeMembership=original;
  }
  const savedCandidate=handoff.candidate;handoff.candidate=null;
  assert.ok(!all(render()).some(n=>n.text==='Review replacement receipt'),'Missing candidate identity stays blocked');
  handoff.candidate=savedCandidate;
  handoff.nativeMembership.status='active';
  assert.ok(!all(render()).some(n=>n.text==='Review replacement receipt'));
  handoff.nativeMembership.status='idle';
  nodes=all(render());
  assert.ok(nodes.some(n=>String(n.text).includes('Codex task list: Codex project native-a')));
  assert.ok(nodes.some(n=>n.text==='Review replacement receipt'));
  box.state.brainHandoff.handoff.nativeMembership.observedAt-=7200;
  assert.ok(!all(render()).some(n=>n.text==='Review replacement receipt'),'Expired browser observation cannot show a review action');
  handoff.receiptEvidence.observedAt=Date.now()/1000-100;
  handoff.nativeMembership.observedAt=handoff.receiptEvidence.observedAt-1;
  assert.ok(!all(render()).some(n=>n.text==='Review replacement receipt'),'Pre-reply membership cannot show a review action');
  handoff.nativeMembership={source:'owned_app_server.thread_read',taskId:'new',projectId:'native-a',nativeProjectId:'app-server-a',
    hostId:'local',status:'idle',observedAt:Date.now()/1000};
  nodes=all(render());
  assert.ok(nodes.some(n=>String(n.text).includes('Owned-host exact task read: Codex project native-a · app-server project app-server-a')));
  assert.ok(nodes.some(n=>String(n.text).includes('not complete task inventory or host attestation')));
  assert.ok(nodes.some(n=>n.text==='Review replacement receipt'),'Fresh exact owned-host read permits review');
  await nodes.find(n=>n.text==='Review replacement receipt').click();
  nodes=all(render());
  assert.equal(nodes.find(n=>n.text==='Confirm replacement brain').disabled,true,'Exact read opens review, not automatic rebinding');
  nodes.find(n=>n.text==='Cancel review').click();
  handoff.nativeMembership.status='notLoaded';
  assert.ok(all(render()).some(n=>n.text==='Review replacement receipt'),'Unloaded exact candidate may be reviewed');
  for(const change of [{status:'active'},{status:'unknown'},{taskId:'another'},{projectId:'other'},
    {hostId:'other'},{source:'candidate-claim'},{observedAt:Date.now()/1000-7200},
    {observedAt:handoff.receiptEvidence.observedAt-1}]){
    const original={...handoff.nativeMembership};Object.assign(handoff.nativeMembership,change);
    assert.ok(!all(render()).some(n=>n.text==='Review replacement receipt'),`Exact read ${JSON.stringify(change)} stays blocked`);
    handoff.nativeMembership=original;
  }
  handoff.nativeMembership.source='codex.list_threads';
  assert.ok(!all(render()).some(n=>n.text==='Review replacement receipt'),'Task-list notLoaded is not qualified');
  box.state.standard={available:false,catalogRequired:true,contextHash:'missing',boundary:'Partial observations',catalog:null,run:null,
    blocker:'Brain must record the available native model/effort catalog (valid for 24 hours)',catalogRefresh:null};
  nodes=all(render());const prepare=nodes.find(n=>n.text==='Review Play');assert.equal(prepare.disabled,false);
  await prepare.click();assert.equal(sent.filter(s=>s.path.endsWith('catalog-refresh')).length,1);
  assert.equal(sent.filter(s=>s.path==='/api/standard/preview').length,1,'Capability collection does not bypass the separate Play preview');
  box.state.standard.catalogRefresh={id:'request',status:'queued',createdAt:Date.now()/1000,result:'Waiting',notification:{status:'accepted'},deliveryAttempts:1,maxDeliveryAttempts:3};
  nodes=all(render());assert.equal(nodes.find(n=>n.textContent==='Waiting for native capabilities').disabled,true);
  assert.ok(nodes.some(n=>String(n.text).includes('Waiting for the designated brain')));
  const fullDiagnostic='Private fixture diagnostic: no native task creation or message schema is exposed.';
  box.state.standard.catalogRefresh={id:'failed-request',status:'failed',completedAt:10,result:fullDiagnostic,
    catalogError:{code:'native_task_schema_unavailable',retryable:true},notification:{status:'accepted',nativeDelivery:'owned_turn_start'}};
  const beforeInspection=sent.length;
  nodes=all(render());
  assert.ok(nodes.some(n=>String(n.text).includes('Codex task tools are unavailable')));
  assert.ok(!nodes.some(n=>n.tag==='button'&&String(n.text).includes('Retry')));
  assert.ok(!box.catalogStatus(box.state.standard.catalogRefresh).detail.includes(fullDiagnostic),'The notice is concise, not raw diagnostic prose');
  const failureDetails=nodes.find(n=>n.tag==='details'&&n.children.some(c=>c.text==='Details · Codex readiness diagnostic'));
  assert.equal(failureDetails.open,false);
  assert.ok(all(failureDetails).some(n=>n.text===fullDiagnostic),'The exact diagnostic remains available in Details');
  assert.ok(all(render('operations')).some(n=>n.text===fullDiagnostic),'Inspect request delivery can reach the diagnostic');
  await nodes.find(n=>n.textContent==='Inspect Codex readiness').click();
  assert.equal(sent.length,beforeInspection,'Inspecting a setup failure does not send another capability request');
  assert.equal(routes.at(-1),'operations');
  box.scheduleCatalogFollowup(box.state.standard);
  assert.equal(sent.length,beforeInspection,'Failed capability checks are not scheduled for retry');
  const afterRepair=nodes.find(n=>n.text==='Check again after host repair');
  box.workspaceId='other-project';await afterRepair.click();assert.equal(sent.length,beforeInspection,'Detached project actions cannot submit');
  box.workspaceId='alpha';box.state.standard.catalogRefresh.id='replacement';await afterRepair.click();
  assert.equal(sent.length,beforeInspection,'An obsolete diagnostic cannot create a new request');
  box.state.standard.catalogRefresh.id='failed-request';box.connected=false;await afterRepair.click();
  assert.equal(sent.length,beforeInspection,'Disconnected rechecks cannot submit');box.connected=true;
  box.state.standard.contextHash='changed';await afterRepair.click();
  assert.equal(sent.length,beforeInspection,'A changed context cannot submit from an old diagnostic');box.state.standard.contextHash='missing';
  const playPreviewsBeforeRecheck=sent.filter(s=>s.path==='/api/standard/preview').length;
  await afterRepair.click();
  assert.equal(sent.length,beforeInspection+1,'An explicit recheck uses the existing capability request once');
  assert.equal(sent.at(-1).path,'/api/standard/catalog-refresh');
  assert.equal(sent.filter(s=>s.path==='/api/standard/preview').length,playPreviewsBeforeRecheck,'A recheck does not prepare or confirm Play');
  box.state.standard.catalogRefresh.catalogError={code:'unsupported_destination',retryable:false};
  await afterRepair.click();assert.equal(sent.length,beforeInspection+1,'Changed retryability fences a previously rendered button');
  nodes=all(render());assert.ok(nodes.some(n=>String(n.text).includes('operator attention')));
  assert.ok(!nodes.some(n=>n.tag==='button'&&n.text==='Check again after host repair'),'Non-retryable errors do not offer a resend');
  const ownedOverdue=box.catalogStatus({status:'queued',createdAt:1,notification:{status:'accepted',nativeDelivery:'owned_turn_start'}});
  assert.match(ownedOverdue.detail,/bound Codex host started this turn/);
  assert.ok(!ownedOverdue.detail.includes('legacy desktop queue'),'Owned-host progress does not imply legacy delivery');
  const guidedSteps=[],guideOpens=[],beforeGuidedPlay=sent.length;
  box.assistantRequestStep=async key=>guidedSteps.push(key);
  box.sessionShowGuide=()=>guideOpens.push(true);
  await box.reviewStandardControl(box.state.standard,'play',null);
  assert.deepEqual(guidedSteps,['phase_play'],'The full app opens editable signed Play in its existing guide');
  assert.equal(guideOpens.length,1);
  assert.equal(sent.length,beforeGuidedPlay,'The direct Play control cannot bypass the signed guide');
  box.connected=false;await box.reviewStandardControl(box.state.standard,'play',null);box.connected=true;
  box.busy=true;await box.reviewStandardControl(box.state.standard,'play',null);box.busy=false;
  assert.equal(guidedSteps.length,1,'Disconnected or busy controls cannot prepare another Play preview');
  console.log('Standard UI: explicit confirmation, project separation, unknown usage and checkpoint controls passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
