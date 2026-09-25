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
assert.match(box.assistantUsageSummary({records:[],tokens:{total_tokens:0,cached_input_tokens:0},gaps:['missing'],collectedAt:1}),/No usage samples.*unknown/);
assert.match(box.assistantUsageSummary({records:[{}],tokens:{total_tokens:12,cached_input_tokens:3},gaps:['partial'],collectedAt:1}),/At least 12 observed tokens/);
box.state.workspace={id:'alpha'};box.state.standard={run:{status:'blocked'},blockers:[]};box.state.recovery={
  title:'Usage evidence is incomplete',explanation:'Remaining measured budget is unknown.',phaseStatus:'blocked',
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
