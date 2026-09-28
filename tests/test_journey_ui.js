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
const box={workspaceId:'alpha',busy:false,connected:true,missionDrafts:new Map(),brainDrafts:drafts,standardPreviews:new Map(),standardCatalogInFlight:new Set(),
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
s.standard.catalogRequired=false;assert.equal(model(s).action,'runReadiness');
s=base();s.standard.run=run('running');assert.equal(model(s).action,'overview');assert.equal(model(s).canPause,true);
s.workflow={openDecisions:2};assert.equal(model(s).action,'decisions');assert.equal(model(s).canPause,true);
s.standard.blockers=['Missing usage'];assert.equal(model(s).action,'pause');
s.recovery={reconciliationRequired:true};s.meta={controller:null};
assert.equal(model(s).action,'reconcile','An open stranded run needs reconciliation, not another Play');
assert.match(box.projectPhaseStatus(s),/RECOVERY REQUIRED/);
s.meta.brainControl={desired:'stopped'};
assert.equal(model(s).action,'operations','A stopped brain needs explicit recovery, not a refused ordinary message');
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
