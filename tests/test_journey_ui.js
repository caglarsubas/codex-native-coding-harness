"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag,text='',className=''){Object.assign(this,{tag,text,className,children:[],events:{},dataset:{},isConnected:true});}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=items;}
  prepend(...items){this.children.unshift(...items);}
  setAttribute(name,value){this[name]=value;}
  addEventListener(name,fn){this.events[name]=fn;}
  get lastChild(){return this.children.at(-1);}
}
const calls=[],notices=[],drafts=new Map();
const box={workspaceId:'alpha',busy:false,connected:true,missionDrafts:new Map(),brainDrafts:drafts,brainPages:new Map(),brainRequestFocus:new Map(),standardPreviews:new Map(),standardCatalogInFlight:new Set(),
  document:{getElementById:()=>null},el:(...args)=>new Element(...args),button:(text,click)=>Object.assign(new Element('button',text),{click}),
  num:String,when:String,navigateView:view=>calls.push(['navigate',view]),showNotice:text=>notices.push(text),
  reviewStandardControl:(s,op)=>calls.push(['review',op]),requestCatalogForPlay:()=>calls.push(['catalog']),refresh:()=>calls.push(['refresh']),
  focusAssistantConversation:()=>calls.push(['focus','assistant']),developmentHelpUpdate:()=>calls.push(['help','current']),assistantRequestStep:key=>calls.push(['preview',key]),
  commandPresentation:()=>({label:'Delivery unconfirmed',detail:'Do not resend'}),catalogStatus:()=>({title:'Delivery unconfirmed',detail:'Do not resend'}),scheduleCatalogFollowup:()=>{},standardConfirmation:()=>calls.push(['confirmation'])};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/summaries.js','utf8'),box);vm.runInContext(fs.readFileSync('web/journey.js','utf8'),box);
const base=()=>({workspace:{id:'alpha',name:'Sample project'},repositories:[{policyProfile:'standard'}],commands:[],
  standard:{available:true,contextHash:'hash',run:null},mission:{effectiveStatus:'reviewed',bindingIssues:[],document:{spec:{
    phase:{id:'phase-1',title:'First phase',checkpoint:'Review independent test results'},authority:{approvalMode:'phase_delegated',tokenBudget:300000,maxParallelTasks:2}}}}});
const model=(s,connected=true)=>box.roadmapJourneyState(s,connected,1000);
const run=(status)=>({id:'run',status,phaseId:'phase-1',expiresAt:2000,limits:{tokenBudget:300000,maxParallelTasks:2},tasks:[],checkpoint:{summary:'The phase result is retained.'}});
const all=root=>[root,...root.children.flatMap(all)],text=root=>all(root).map(n=>n.text).join('\n');
const render=()=>{const root=new Element('main');box.roadmapJourney(root);return root;};
let s=base();assert.equal(model(s).action,'play');assert.equal(model(s,false).action,'refresh');
for(const repos of [[],undefined,[{policyProfile:'harness'}],[{policyProfile:'standard'},{policyProfile:'harness'}]]){
  assert.equal(model({...s,repositories:repos}).action,'queue');
}
assert.equal(model({...s,workspace:null}).action,'queue');
s.mission=null;assert.equal(model(s).action,'prepare');
s=base();s.mission.effectiveStatus='draft';assert.equal(model(s).action,'mission');
s=base();s.mission.bindingIssues=['Repository changed'];assert.equal(model(s).action,'mission');
s=base();s.mission.document.spec.authority.approvalMode='exact_owner';assert.equal(model(s).action,'mission');
s=base();s.standard.available=false;s.standard.catalogRequired=true;assert.equal(model(s).action,'catalog');
s.standard.catalogRefresh={status:'queued'};assert.equal(model(s).action,'request');
s.standard.catalogRefresh.status='failed';assert.equal(model(s).label,'Retry Codex readiness');
for(const error of [{code:'native_task_schema_unavailable',retryable:true},{code:'schema_unavailable',retryable:true},
  {code:'unsupported_destination',retryable:false}]){
  s.standard.catalogRefresh.catalogError=error;
  const unavailable=model(s);
  assert.equal(unavailable.action,'request','A setup failure opens inspection, not another native check');
  assert.equal(unavailable.label,'Inspect Codex readiness');
  assert.equal(unavailable.requiresSetupChange,true);
  assert.match(unavailable.detail,/Play has not started/);
}
delete s.standard.catalogRefresh.catalogError;
assert.match(box.catalogReadinessIssue({status:'failed',catalogError:{code:'schema_unavailable',retryable:true}}).detail,/could not observe/,'An unavailable observation does not prove tool absence');
s.standard.catalogRequired=false;assert.equal(model(s).action,'runReadiness');
s=base();s.standard.run=run('running');assert.equal(model(s).action,'overview');assert.equal(model(s).canPause,true);
s.workflow={openDecisions:2};assert.equal(model(s).action,'decisions');assert.equal(model(s).canPause,true);
s.standard.blockers=['Missing usage'];assert.equal(model(s).action,'pause');
s.recovery={reconciliationRequired:true};s.meta={controller:null};
assert.equal(model(s).action,'reconcile','An open stranded run needs reconciliation, not another Play');
assert.match(box.projectPhaseStatus(s),/RECOVERY REQUIRED/);
s.meta.brainControl={desired:'stopped'};
assert.equal(model(s).action,'operations','A stopped brain needs explicit recovery, not a refused ordinary message');
s.meta.brainControl={desired:'stopped',phase:'checkpointing',protocol:'workspace_pause_v1'};
s.workspacePause={status:'pausing',blockers:[{code:'inventory_missing'}]};
assert.equal(model(s).action,'operations');assert.equal(model(s).stage,3);
assert.match(model(s).title,/Native checkpoint evidence is missing/);
assert.match(model(s).detail,/another Help, Play or message cannot clear it/);
const savedRecovery=s.recovery;s.recovery=null;box.state=s;
let checkpointView=render();all(checkpointView).find(n=>n.text==='Inspect checkpoint blockers').click();
assert.deepEqual(calls.at(-1),['navigate','operations'],'No preparation confirmation is opened for an incomplete native inventory');
s.recovery=savedRecovery;
delete s.workspacePause;
s.meta.brainControl={desired:'listening'};
s.commands=[{kind:'reconcile',payload:{message:'Inspect existing work'},status:'completed'}];
assert.equal(model(s).action,'conversation','A received message without its retained reply still prevents a duplicate');
s.commands=[];
s.meta.controller={owner:'brain'};assert.equal(model(s).action,'pause','An owned cycle retains safe Pause');
s.recovery=null;
s.standard.run=run('paused');assert.equal(model(s).action,'recover');
box.state=s;let recoveryView=render();all(recoveryView).find(n=>n.text==='Review recovery preparation').click();
assert.deepEqual(calls.slice(-2),[['focus','assistant'],['help','current']],'Checkpoint CTA focuses the one existing signed guided preview');
s.commands=[{kind:'reconcile',payload:{message:'Held instruction'},status:'queued',notification:{status:'uncertain'}}];
assert.equal(model(s).action,'conversation','Uncertain earlier delivery is never woken again');s.commands=[];
s.standard.blockers=[];assert.equal(model(s).action,'resume');
s.standard.run.expiresAt=500;assert.equal(model(s).action,'recover');
s.standard.run.recovery={id:'recovery-1',status:'queued'};assert.equal(model(s).action,'recover_follow');
s.standard.run.recovery={id:'recovery-1',status:'replied'};assert.match(model(s).title,/Review the recovery result/);
s.standard.blockers=[];s.standard.run.expiresAt=2000;s.standard.run.recovery.status='processing';assert.equal(model(s).action,'recover_follow','A pending recovery reply remains the next action even if blockers clear');
s.standard.run.recovery.status='replied';assert.equal(model(s).action,'resume','A replied recovery does not block a separately reviewed eligible Resume');
s.standard.run.recovery=null;
s.standard.run=run('stopping');assert.equal(model(s).action,'overview');assert.equal(model(s).canPause,undefined);
s.standard.run=run('unrecognized');assert.equal(model(s).action,'conversation');
for(const status of ['completed','blocked']){s.standard.run=run(status);assert.equal(model(s).action,'prepare');assert.equal(model(s).stage,3);}
assert.equal(model(s).label,'Prepare recovery proposal');
s.mission.document.spec.phase.id='phase-2';assert.equal(model(s).action,'play');
for(const status of ['prepared','candidate','received']){s.brainHandoff={handoff:{status}};assert.equal(model(s).action,'handoff');}
s.brainHandoff={handoff:{status:'complete'}};assert.equal(model(s).action,'play');
for(const kind of ['standard_play','standard_pause','standard_resume']){s.commands=[{kind,status:'queued',payload:{runId:'run'}}];assert.equal(model(s).action,'request');}
s.commands=[{kind:'standard_play',status:'queued',payload:{runId:'old-run'}}];assert.equal(model(s).action,'play','Old phase requests cannot hide the current next step');
s.standard.run=run('running');s.commands=[{kind:'standard_play',status:'queued',payload:{runId:'run'}}];assert.equal(model(s).canPause,true,'Pause stays available before brain receipt');s.standard.run=run('completed');
for(const status of ['queued','completed']){
  const lost=base();lost.standard.run=run('running');lost.commands=[{kind:'standard_play',status,payload:{runId:'run'},notification:{status:'accepted',nativeTurnStatus:'connection_lost'}}];
  assert.match(model(lost).title,/Connection lost/);
  assert.equal(model(lost).action,'request');assert.equal(model(lost).canPause,true);
  assert.match(model(lost).detail,/do not repeat Play/);
  assert.match(box.projectPhaseStatus(lost),/CONNECTION UNRESOLVED.*recorded running/);
  lost.standard.run.status='stopping';assert.equal(model(lost).title,'Pause requested','Pause priority is unchanged');
}
s.commands=[{kind:'standard_play',status:'completed'}];assert.equal(model(s).action,'play');
box.state=base();let root=render();assert.equal(all(root).filter(n=>n['aria-current']==='step').length,1);
all(root).find(n=>n.text==='Review Play').click();assert.deepEqual(calls.at(-1),['review','play']);
assert(!text(root).includes('Brain handoff'),'Optional recovery is not part of normal Play');
box.state.standard.run=run('completed');box.state.mission.document.spec.phase.id='phase-2';root=render();
assert.match(text(root),/Previous phase phase-1/);assert.match(text(root),/Measured remaining tokens: unknown/);
assert.match(text(root),/Review independent test results/,'New plan displays its own checkpoint, not the old result fallback');
box.state.mission.document.version=11;box.state.mission.effectiveStatus='draft';
assert.match(box.projectPhaseStatus(box.state),/Plan v11 awaits review.*Previous phase completed/);
box.state.standard.run.usageReport={gaps:['invalid_token_record']};
assert.match(text(render()),/Before Play: the previous phase stopped with incomplete usage evidence/);
box.state.commands=[{kind:'reconcile',status:'completed',conversationReply:{at:100,message:'Draft saved. No Play occurred. Next exact owner action: review Mission v11.'}}];
assert.match(text(render()),/Next exact owner action: review Mission v11/);
box.missionDrafts.set('alpha',{});box.state=base();assert.match(text(render()),/Your phase draft is open/);
box.state.standard.run=run('running');assert(!text(render()).includes('Your phase draft is open'),'Drafts cannot hide an active phase');
box.state.standard.run=run('completed');assert.match(text(render()),/Continue phase draft/,'A next-phase draft remains reachable after completion');
box.missionDrafts.clear();box.state.recovery={title:'Usage evidence is incomplete',explanation:'Remaining measured budget is unknown.',
  issues:[{code:'usage_gap',label:'Usage coverage incomplete',source:'platform',nextStep:'Reconcile evidence.'}],
  issueCount:1,issuesTruncated:false,usageRelevant:true,maxTasks:2,maxParallelTasks:1,expiresAt:2000,
  observedTotal:954236,budget:300000,checkpointReserve:75000,cachedInput:778368,uncachedInput:174574,
  output:1294,registeredTasks:0,remainingMeasured:null,observedAt:12345,gapCount:1,
  gapLabels:['A Codex token record could not be validated.'],nextStep:'Review a new phase.',boundary:'No automatic replay.'};
root=render();assert.match(text(root),/Usage evidence is incomplete/);assert.match(text(root),/954236 observed tokens/);
box.state.recovery.observedTotal=100;box.state.recovery.knownUsageLowerBound=954236;
assert.match(text(render()),/At least 954236 tokens were retained in the usage high-water mark/);
box.state.recovery.observedTotal=954236;
box.state.standard.run=run('blocked');box.state.recovery.phaseStatus='blocked';
all(render()).find(n=>n.text==='Prepare recovery proposal').click();
assert.deepEqual(calls.slice(-2),[['focus','assistant'],['preview','phase_prepare']]);
box.state.recovery=null;
box.state.repositories=[{policyProfile:'harness'}];assert.match(text(render()),/Review approved queue/);assert(!text(render()).includes('Continue phase draft'));box.missionDrafts.clear();
box.state=base();box.state.mission=null;root=render();const before=calls.length;
all(root).find(n=>n.text==='Prepare next phase').click();
assert.equal(drafts.get('alpha').confirmed,false);assert.equal(drafts.get('alpha').request,null);
assert.match(drafts.get('alpha').text,/Do not start Play/);assert.deepEqual(calls.slice(before),[['navigate','conversation']],'Preparing a message never sends it');
drafts.set('alpha',{text:'My unfinished message',confirmed:true,request:{id:'old'}});box.prepareRoadmapPhase();
assert.equal(drafts.get('alpha').text,'My unfinished message');assert.match(notices.at(-1),/existing message is preserved/);
box.workspaceId='beta';box.prepareRoadmapPhase();assert(drafts.has('beta'));assert.equal(drafts.get('alpha').text,'My unfinished message');
box.busy=true;box.state=base();root=render();assert.equal(all(root).find(n=>n.text==='Review Play').disabled,true);assert.match(text(root),/Finishing your current request/);
box.busy=false;box.connected=false;assert.match(text(render()),/Reconnect/);
const disclosure=box.journeyDisclosure('fixture','Details',()=>{});disclosure.open=true;disclosure.events.toggle();
assert.equal(box.journeyDisclosure('fixture','Details',()=>{}).open,true);box.workspaceId='alpha';assert.equal(box.journeyDisclosure('fixture','Details',()=>{}).open,false);
disclosure.isConnected=false;disclosure.open=false;disclosure.events.toggle();box.workspaceId='beta';assert.equal(box.journeyDisclosure('fixture','Details',()=>{}).open,true,'Detached toggle cannot erase a remembered choice');
console.log('Roadmap journey: state guidance, no implied approval, retained drafts, unknown usage and disclosure isolation passed');

const historyState=box.state;
box.state={commands:[{id:'saved-pause',kind:'standard_pause',status:'queued',createdAt:123,
  notification:{status:'unavailable',nativeFailure:{version:1,stage:'thread_resume',reason:'rpc_error',
    rpcCode:-32602,resumeAttempted:true,turnStartAttempted:false}}}]};
const diagnosticRoot=new Element('main'),diagnosticCalls=calls.length;
box.controlRequestHistory(diagnosticRoot);
assert.match(text(diagnosticRoot),/Details · Failed delivery step/);
assert.match(text(diagnosticRoot),/Load brain with reviewed settings/);
assert.match(text(diagnosticRoot),/Brain turn start was not attempted/);
assert.equal(calls.length,diagnosticCalls,'Reading delivery details never starts a turn or submits a control');
box.state=historyState;

// A no-run pilot and completed phases must follow their unfinished request,
// rather than offering another preparation prompt. A receipt is not a reply.
box.busy=false;box.connected=true;box.workspaceId='alpha';box.state=base();box.state.mission=null;
const pendingMessage={id:'saved-pilot',kind:'reconcile',status:'processing',createdAt:1,
  payload:{message:'Existing bounded instruction'},conversationReceivedAt:900,notification:{status:'accepted'}};
box.state.commands=[pendingMessage];
assert.equal(model(box.state).title,'Waiting for the brain’s saved reply');
assert.equal(model(box.state).action,'conversation');
assert.equal(model(box.state).request.id,'saved-pilot');
assert.equal(model(box.state).canPause,false);
box.missionDrafts.set('alpha',{});root=render();
assert.match(text(root),/Waiting for the brain’s saved reply/);
assert(!all(root).some(n=>n.tag==='button'&&['Prepare next phase','Continue phase draft','Review Play'].includes(n.text)));
const requestCalls=calls.length;all(root).find(n=>n.text==='Inspect saved request').click();
assert.deepEqual(calls.slice(requestCalls),[['navigate','conversation']],'Following a pending reply only opens the inspector');
drafts.clear();box.prepareRoadmapPhase();
assert.equal(drafts.size,0,'Even direct preparation preserves the existing request without creating a duplicate draft');
assert.match(notices.at(-1),/saved request is still awaiting a reply/);
box.missionDrafts.clear();
for(const status of ['completed','failed','interrupted']){
  pendingMessage.notification.nativeTurnStatus=status;
  assert.match(model(box.state).title,/turn ended without a saved reply/);
}
pendingMessage.notification.nativeTurnStatus='native_attention_required';
assert.match(model(box.state).detail,/only a current prompt can be answered/);
delete pendingMessage.conversationReceivedAt;delete pendingMessage.notification.nativeTurnStatus;
for(const status of ['sending','uncertain']){
  pendingMessage.notification.status=status;
  assert.match(model(box.state).title,/delivery needs reconciliation/);
  assert.match(model(box.state).detail,/do not resend/);
}
pendingMessage.notification.status='unavailable';
assert.match(model(box.state).title,/could not reach Codex/);
assert.match(model(box.state).detail,/new message will not repair the connection/);
pendingMessage.notification={status:'accepted',nativeTurnStatus:'interrupted'};
assert.match(model(box.state).title,/without a brain receipt/);
pendingMessage.notification={status:'accepted'};
assert.match(model(box.state).title,/Waiting for the brain’s receipt/);
delete pendingMessage.notification;assert.match(model(box.state).title,/waiting for delivery/);
box.state.standard.run=run('completed');assert.equal(model(box.state).action,'conversation');
box.state.standard.run=run('running');assert.equal(model(box.state).canPause,true,'Safe Pause remains available while a reply is pending');
box.state.standard.blockers=['Missing usage'];
assert.equal(model(box.state).action,'pause','A safety checkpoint takes priority over an ordinary pending reply');
box.state.standard.blockers=[];
box.state.standard.run=run('stopping');assert.equal(model(box.state).title,'Pause requested','Pause priority is unchanged');
box.state.standard.run=run('paused');box.state.standard.blockers=['Missing usage'];
assert.equal(model(box.state).action,'recover','A held message retains the separately signed recovery path');
box.state.standard.run=null;pendingMessage.conversationReply={at:950,message:'Retained reply'};
assert.equal(model(box.state).action,'prepare','Only a retained reply clears conversation guidance');
delete pendingMessage.conversationReply;
box.state.commands.push({...pendingMessage,id:'newer',conversationReceivedAt:999});
assert.equal(model(box.state).request.id,'newer','The newest unresolved request is followed');
assert.equal(model({...box.state,commands:[]}).action,'prepare','Project snapshots do not share pending request state');
box.state.commands=[pendingMessage,...Array.from({length:64},(_,index)=>({
  ...pendingMessage,id:'history-'+index,createdAt:2+index,conversationReply:{at:950+index,message:'Retained historical reply'}}))];
assert.equal(model(box.state).request.id,'saved-pilot','Paginated conversation history cannot hide an older unfinished request');
box.journeyAction('conversation');
assert.equal(box.brainPages.get('alpha'),2,'Inspection opens the page containing the exact request');
assert.equal(box.brainRequestFocus.get('alpha'),'saved-pilot');
assert.equal(box.brainPages.has('beta'),false,'Request navigation remains project-scoped');
box.state.commands=[{...pendingMessage,id:'Z-request'},...Array.from({length:29},(_,i)=>({
  ...pendingMessage,id:'a-history-'+i,conversationReply:{message:'Retained'}})),
  {...pendingMessage,id:'_-history',conversationReply:{message:'Retained'}}];
box.journeyAction('conversation');
assert.equal(box.brainPages.get('alpha'),1,'Equal-time IDs use server code-point order, not locale collation');

box.busy=false;box.connected=true;box.state=base();box.state.meta={controller:null};box.state.standard.run=run('running');
box.state.recovery={title:'Recovery required before continuing',explanation:'Two conditions.',reconciliationRequired:true,
  unconfirmedTasks:1,uncertainMerges:0,usageRelevant:true,budgetBoundaryReached:true,knownUsageLowerBound:18966347,
  observedTotal:18966347,budget:8000000,checkpointReserve:1000000,gapCount:1,gapLabels:[],issues:[],issueCount:2,
  nextStep:'Do not repeat Play. Reconcile the existing effect first.',remainingMeasured:null};
root=render();assert.match(text(root),/identity is not confirmed/);assert.match(text(root),/8000000 phase budget/);
const prior=calls.length;all(root).find(n=>n.text==='Reconcile this phase').click();
assert.deepEqual(calls.slice(prior),[['focus','assistant'],['preview','phase_reconcile']]);
assert(!all(root).some(n=>n.tag==='button'&&['Review Play','Review Resume'].includes(n.text)));
const sessionSource=fs.readFileSync('web/session-map.js','utf8');
vm.runInContext(sessionSource.slice(sessionSource.indexOf('function sessionPulse('),sessionSource.indexOf('function sessionResetFilters(')),box);
box.state.meta.checkpoint='Preserved checkpoint; do not retry.';
const recoveryRoot=new Element('section');box.sessionRecovery(recoveryRoot);
assert.match(text(recoveryRoot),/Safety stop · recorded reasons/);
assert.match(text(recoveryRoot),/Last saved brain checkpoint/);
assert(!all(recoveryRoot).some(n=>n.tag==='button'),'The graph header owns the one next action; recovery details do not duplicate it');
const unchanged=recoveryRoot.children[0];box.sessionRecovery(recoveryRoot);
assert.equal(recoveryRoot.children[0],unchanged,'Unchanged polling preserves focus and open details');
box.connected=false;box.sessionRecovery(recoveryRoot);
assert.match(text(recoveryRoot),/Safety stop/);assert(!all(recoveryRoot).some(n=>n.tag==='button'));
box.connected=true;box.state.recovery=null;box.sessionRecovery(recoveryRoot);
assert.equal(recoveryRoot.hidden,true,'Resolved or foreign project state clears the old warning');
box.state=base();box.state.meta={controller:null};box.state.standard.run=run('paused');
box.state.standard.run.recovery={status:'replied'};box.state.standard.blockers=['Duration expired'];
box.state.phaseCloseout={available:true};
assert.equal(model(box.state).action,'close','Completed recovery has an owner transition, not a dead-end controls page');
const beforeClose=calls.length;box.journeyAction('close');
assert.deepEqual(calls.slice(beforeClose),[['focus','assistant'],['preview','phase_close']]);
assert(!calls.slice(beforeClose).some(c=>c[0]==='review'),'Opening closeout does not Resume or Play');
box.state.phaseCloseout={available:false};assert.equal(model(box.state).action,'recover_follow');
box.state.standard.run.status='blocked';assert.equal(model(box.state).action,'prepare');

box.state=base();box.state.standard.run=run('stopping');box.state.standard.pauseRecovery={available:true,pauseId:'pause'};
assert.notEqual(model(box.state).action,'pause-recover','Saved eligibility without a bound owned host is not a usable recovery');
box.state.brainNotification={transport:'owned_app_server'};
assert.equal(model(box.state).action,'pause-recover');
const beforeRecovery=calls.length;box.journeyAction('pause-recover');
assert.deepEqual(calls.slice(beforeRecovery),[['focus','assistant'],['preview','phase_pause_recovery']],'Recovery click prepares its exact separate preview, never confirms');
box.state.standard.pauseRecovery.replacementOf='failed-recovery';
assert.match(model(box.state).title,/replacement checkpoint recovery/);
assert.match(model(box.state).detail,/no third attempt/);
const beforeReplacement=calls.length;box.journeyAction('pause-recover');
assert.deepEqual(calls.slice(beforeReplacement),[['focus','assistant'],['preview','phase_pause_recovery']],'Replacement prepares a separately reviewed preview, never confirms or retries');
box.state.standard.pauseRecovery.available=false;
box.state.standard.run.pauseRecovery={id:'recovery',status:'queued'};
box.state.commands=[{id:'recovery',kind:'standard_pause_recovery',status:'queued',payload:{runId:'run'}}];
assert.equal(model(box.state).request.id,'recovery','Follow recovery rather than original failed Pause');
assert.equal(model(box.state).action,'request');
assert.match(model(box.state).title,/Following Pause recovery/);
assert.equal(model(box.state,false).action,'refresh','Disconnected cached eligibility never offers a wake');
