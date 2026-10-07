const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag,text='',className=''){Object.assign(this,{tag,text,className,children:[],dataset:{},value:''});}
  append(...items){this.children.push(...items);} replaceChildren(...items){this.children=items;}
  setAttribute(k,v){this[k]=v;}
}
const input=new Element('textarea'),nextStep=new Element('section'),notices=[],turns=[];
const box={workspaceId:'alpha',state:{meta:{brainId:'brain',revision:2},mission:{revision:1,documentHash:'hash'},commands:[]},
  el:(...a)=>new Element(...a),$:id=>id==='assistant-next-step'?nextStep:input,assistantActions:new Map(),assistantStatus:(...a)=>notices.push(a),
  chatTurn:(...a)=>turns.push(a),commandPresentation:c=>({label:c.status,detail:'Retained receipt'}),num:String,when:String,Date};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/summaries.js','utf8'),box);vm.runInContext(fs.readFileSync('web/assistant-workflow.js','utf8'),box);
const run=code=>vm.runInContext(code,box);
run(`var sent=0; var a={workspace:'alpha',submit:()=>sent++,proposal:{document:{workflow:'phase_review',id:'p',brainId:'brain',expiresAt:Date.now()/1000+300,request:{expectedRevision:1,documentHash:'hash'}}}}; assistantActions.set('p',a);`);
assert.equal(run('assistantWorkflowState(a).locked'),false);
assert.equal(box.assistantTypedConfirmation('yes'),false,'Vague consent is never execution');
assert.equal(box.assistantTypedConfirmation('confirm review'),true);assert.equal(run('sent'),1);
run('state.mission.revision=2');box.assistantTypedConfirmation('confirm review');assert.equal(run('sent'),1,'Changed draft cannot be confirmed');
run('state.mission.revision=1; workspaceId="beta"');box.assistantTypedConfirmation('confirm review');assert.equal(run('sent'),1,'Foreign project cannot be confirmed');
run('workspaceId="alpha"; a.proposal.document.expiresAt=0');box.assistantTypedConfirmation('confirm review');assert.equal(run('sent'),1,'Expired preview cannot be confirmed');
run('a.receipt={message:"Saved",result:{id:"p",kind:"reconcile",status:"completed"}}');assert.equal(run('assistantWorkflowState(a).label'),'completed');
run('a.receipt=null; a.uncertain=true');assert.equal(run('assistantWorkflowState(a).locked'),false,'Same receipt can be recovered after expiry');
run('a.uncertain=false; a.proposal.document.expiresAt=Date.now()/1000+300; assistantActions.set("q",{...a});');box.assistantTypedConfirmation('confirm review');assert.equal(run('sent'),1,'Ambiguous confirmation must not choose a target');
assert(!fs.readFileSync('web/assistant-workflow.js','utf8').includes('innerHTML'));
assert.match(fs.readFileSync('web/one-page.css','utf8'),/\.assistant-body:has\(\.chat-action\) \.assistant-composer\{position:static\}/,'Control reviews must not be obscured by the composer');
const inspector={scrollTop:40,getBoundingClientRect:()=>({top:100})};
box.assistantRevealControl({closest:()=>inspector,getBoundingClientRect:()=>({top:300}),scrollIntoView:()=>assert.fail('Do not pan the workspace')});
assert.equal(inspector.scrollTop,224,'Reveal the control within its inspector, keeping the graph position');
assert.match(box.assistantUsageSummary({records:[],tokens:{total_tokens:0,cached_input_tokens:0},gaps:['missing'],collectedAt:1}),/No usage samples.*unknown/);
assert.match(box.assistantUsageSummary({records:[{}],tokens:{total_tokens:12,cached_input_tokens:3},gaps:['partial'],collectedAt:1}),/At least 12 observed tokens/);
box.state.workspace={id:'alpha'};box.state.standard={run:{status:'blocked'},blockers:[]};box.state.recovery={
  title:'Usage evidence is incomplete',explanation:'Remaining measured budget is unknown.',phaseStatus:'blocked',
  issues:[{code:'usage_gap',label:'Usage coverage incomplete',source:'platform',nextStep:'Reconcile evidence.'}],
  issueCount:1,issuesTruncated:false,usageRelevant:true,maxTasks:2,maxParallelTasks:1,expiresAt:12345,
  observedTotal:954236,knownUsageLowerBound:954236,budget:300000,checkpointReserve:75000,
  cachedInput:778368,uncachedInput:174574,output:1294,registeredTasks:0,remainingMeasured:null,
  observedAt:12345,gapCount:1,gapLabels:['A token record could not be validated.'],reasonLabels:[],
  nextStep:'Ask for a new phase.',boundary:'No automatic replay.'};
box.connected=true;box.assistantPending=false;box.roadmapJourneyState=()=>({title:'Phase stopped',action:'prepare',label:'Prepare recovery proposal'});
box.button=(text)=>new Element('button',text);
box.assistantNextStep();
const rendered=(root)=>[root,...root.children.flatMap(rendered)];
assert(rendered(nextStep).some(e=>e.text==='Usage evidence is incomplete'));
assert(rendered(nextStep).some(e=>e.text==='Prepare recovery proposal'));
console.log('Assistant workflow: exact typed consent, stale/foreign previews, receipt recovery and ambiguity passed');
const steps=[];box.assistantRequestStep=key=>steps.push(key);
box.state.repositories=[{policyProfile:'standard'}];
box.state.standard.available=false; // A draft is precisely when preparation is needed.
box.state.commands=[];
assert.equal(box.assistantLocalWorkflow('Help me continue development'),true);
assert.deepEqual(steps,['phase_prepare'],'Exact starter prepares a preview without a model call');
assert.equal(box.assistantLocalWorkflow('Pause the project safely'),true);
assert.equal(steps.at(-1),'phase_pause');
assert.equal(box.assistantLocalWorkflow('What changed in the last phase?'),false,'Questions are not controls');
assert.equal(box.assistantLocalWorkflow('yes'),false,'No inferred confirmation');
box.state.commands=[{status:'queued'}];
const count=steps.length;box.assistantLocalWorkflow('Help me continue development');
assert.equal(steps.length,count,'Do not duplicate a pending request');
box.state.repositories=[{policyProfile:'harness'}];
assert.equal(box.assistantLocalWorkflow('Help me continue development'),false,'Strict Harness never enters the standard shortcut');
box.state.repositories=[{policyProfile:'standard'}];box.state.commands=[];
box.roadmapJourneyState=()=>({title:'Recovery required',action:'reconcile',label:'Reconcile this phase'});
box.state.recovery.reconciliationRequired=true;box.state.recovery.budgetBoundaryReached=true;
box.state.standard.run.status='running';box.state.standard.blockers=['Usage observation expired'];
box.assistantNextStep();
assert(rendered(nextStep).some(e=>e.text==='Reconcile this phase'),'Refreshing usage must not hide unresolved native effects');
assert(!rendered(nextStep).some(e=>e.text==='Review usage check'));
box.assistantLocalWorkflow('Help me continue development');assert.equal(steps.at(-1),'phase_reconcile');
box.state.commands=[{id:'recovery',kind:'reconcile',payload:{message:'Retained recovery request'},status:'processing'}];
box.assistantNextStep();assert(rendered(nextStep).some(e=>e.text==='Usage evidence is incomplete'),'Pending reply must not hide the safety warning');
assert(!rendered(nextStep).some(e=>e.text==='Reconcile this phase'),'No duplicate recovery button while waiting');

// The saved Review offers a fresh Play preview at the same scroll position;
// it never confirms Play or reuses the previous mission review as authority.
box.button=(text,onclick)=>Object.assign(new Element('button',text),{onclick});
box.roadmapJourneyState=()=>({title:'Ready to review Play',action:'play',label:'Review Play'});
const reviewed={receipt:{result:{}},element:new Element('section'),proposal:{document:{workflow:'phase_review'}}};
box.assistantWorkflowReceipt(reviewed,true);
const nextPlay=rendered(reviewed.element).find(e=>e.text==='Next: Review Play');
assert(nextPlay);assert.equal(nextPlay.disabled,false);
nextPlay.onclick();assert.equal(steps.at(-1),'phase_play');
assert.equal(run('sent'),1,'Next step prepares only; it never confirms the control');
box.assistantPending=true;box.assistantWorkflowReceipt(reviewed,true);
assert(rendered(reviewed.element).find(e=>e.text==='Next: Review Play').disabled);
box.assistantPending=false;box.roadmapJourneyState=()=>({title:'Evidence is missing',action:'usage',label:'Refresh usage'});
box.assistantWorkflowReceipt(reviewed,true);
assert(!rendered(reviewed.element).some(e=>e.text==='Next: Review Play'),'A changed gate removes the old next step');

// Closeout is its own exact owner action, not a recovery replay or Play.
run(`var closeSent=0; var closeAction={workspace:'alpha',submit:()=>closeSent++,proposal:{document:{workflow:'phase_close',id:'close-1',brainId:'brain',expiresAt:Date.now()/1000+300,request:{expectedRevision:state.meta.revision}}}}; assistantActions.set('close-1',closeAction);`);
assert.equal(box.assistantTypedConfirmation('confirm close stopped phase'),true);
assert.equal(run('closeSent'),1);
assert.equal(box.assistantTypedConfirmation('close it'),false,'No inferred closeout confirmation');
box.state.standard.run={status:'blocked',ownerCloseout:{requestId:'close-1'}};
box.state.commands=[];
let helpStarted=0;box.developmentHelpStart=()=>helpStarted++;
const closed={receipt:{result:{kind:'standard_closeout'}},element:new Element('section'),proposal:{document:{workflow:'phase_close',id:'close-1'}}};
box.assistantWorkflowReceipt(closed,closed.receipt.result);
const nextHelp=rendered(closed.element).find(e=>e.text==='Next: Help me continue development');
assert(nextHelp);nextHelp.onclick();assert.equal(helpStarted,1);assert.equal(run('closeSent'),1);
assert(rendered(closed.element).some(e=>e.text==='Details · reviewed closeout'),'Saved closeout details stay collapsed');
box.state.commands=[{status:'queued'}];box.assistantWorkflowReceipt(closed,true);
assert(!rendered(closed.localNext).some(e=>e.text==='Next: Help me continue development'),'A pending preparation replaces the old next button');
assert(rendered(closed.localNext).some(e=>/Follow the preparation progress/.test(e.text)));
box.state.commands=[];
box.state.standard.run={status:'paused'};box.assistantWorkflowReceipt(closed,true);
assert(!rendered(closed.element).some(e=>e.text==='Next: Help me continue development'),'Stale closeout cannot guide another run');

run(`assistantActions.clear(); state.meta.revision=2; var pauseRecovery={workspace:'alpha',submit:()=>sent++,proposal:{document:{workflow:'phase_pause_recovery',id:'pause-recovery',brainId:'brain',expiresAt:Date.now()/1000+300,request:{expectedRevision:2}}}}; assistantActions.set('pause-recovery',pauseRecovery);`);
const countBeforePause=run('sent');assert.equal(box.assistantTypedConfirmation('confirm pause recovery'),true);
assert.equal(run('sent'),countBeforePause+1,'Exact recovery phrase selects its own signed preview');
run('pauseRecovery.receipt={result:{id:"pause-recovery",kind:"standard_pause_recovery",status:"queued"},message:"Saved"}');
box.assistantTypedConfirmation('confirm pause recovery');assert.equal(run('sent'),countBeforePause+1,'Saved receipt cannot send again');
