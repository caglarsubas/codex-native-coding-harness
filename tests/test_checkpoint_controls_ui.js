"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const box={Map,Date};vm.createContext(box);
const source=fs.readFileSync('web/checkpoint-controls.js','utf8');vm.runInContext(source,box);
for(const forbidden of ['innerHTML','localStorage','sessionStorage','/api/commands','/api/play','/api/release'])assert(!source.includes(forbidden));
class Element{
  constructor(tag,text,cls){this.tag=tag;this.text=text||'';this.className=cls;this.children=[];}
  append(...nodes){this.children.push(...nodes)} reportValidity(){return true}
  addEventListener(event,handler){this['on'+event]=handler}
  get textContent(){return this.text+this.children.map(n=>typeof n==='string'?n:n.textContent).join(' ')}
}
box.el=(...args)=>new Element(...args);box.empty=(a,b)=>new Element('section',a+' '+b);box.callout=box.empty;box.section=box.empty;
box.button=(text,action)=>Object.assign(new Element('button',text),{action});box.when=String;box.num=String;
box.table=(headers,rows)=>new Element('table',headers.join(' ')+rows.map(r=>r.join(' ')).join(' '));
vm.runInContext("let workspaceId='alpha',workspaceGeneration=1,connected=true,view='phaseCheckpoints',busy=false,selected=null,csrf='fixture';let state={workspace:{name:'Alpha'},meta:{revision:1}};let notices=[];function render(){}function showNotice(s){notices.push(s)}function updateWorkspaceSelector(){}async function refresh(){}function loadPhaseCheckpoints(){}",box);
const run=s=>vm.runInContext(s,box),walk=root=>[root,...root.children.flatMap(n=>typeof n==='string'?[]:walk(n))];
function rendered(){const root=new Element('main');box.checkpointDecisionView(root);return {root,nodes:walk(root)}}
let calls=0;box.api=()=>{calls++;throw new Error('Rendering must not inspect')};
assert.match(rendered().root.textContent,/No decision inspection/);assert.equal(calls,0);
const now=Date.now()/1000,candidate={reportHash:'r'.repeat(64),artifactId:'a'.repeat(64),missionHash:'m'.repeat(64),reviewReceiptHash:'h'.repeat(64),reportVersion:1,generation:1,reportAt:now,
  mission:{spec:{phase:{title:'Next phase',objective:'Fixture only',checkpoint:'Owner review'},authority:{approvalMode:'exact_owner',maxParallelTasks:2,maxTasks:4,tokenBudget:100000,checkpointReserveTokens:10000}}},settings:[{value:'native_defaults',label:'Native defaults'}]},
  oldReview={checkpointReviewHash:'q'.repeat(64),reportHash:candidate.reportHash,missionHash:candidate.missionHash,at:now,expiresAt:now+3600,withdrawn:false},
  report={workspaceId:'alpha',workspaceRevision:1,inspectedAt:now,status:'recorded',canReview:true,contextHash:'c'.repeat(64),candidate,reviews:[oldReview]};
box.report=report;run('checkpointDecisions.set(workspaceId,report)');
let result=rendered();assert.equal(calls,0);assert.match(result.root.textContent,/A new review does not cancel earlier/);
const disclosure=result.nodes.find(n=>n.tag==='details'&&n.textContent.includes('Recorded owner reviews'));disclosure.open=true;disclosure.ontoggle();assert(rendered().nodes.find(n=>n.tag==='details'&&n.textContent.includes('Recorded owner reviews')).open);
let select=result.nodes.find(n=>n.tag==='select'),input=result.nodes.find(n=>n.type==='number');assert.equal(select.value,'');assert.equal(input.value,'');
select.value='0';select.onchange();input.value='60';input.oninput();assert.equal(run('checkpointDrafts.get("alpha:review").settings'),'"native_defaults"');
// Reordered or removed policy choices never reinterpret a saved option index.
candidate.settings.unshift({value:{mode:'adaptive',policyHash:'p'.repeat(64)},label:'Adaptive'});
assert.equal(rendered().nodes.find(n=>n.tag==='select').value,'1');candidate.settings.pop();assert.equal(rendered().nodes.find(n=>n.tag==='select').value,'');candidate.settings=[{value:'native_defaults',label:'Native defaults'}];
assert(box.checkpointDecisionStale({...report,workspaceRevision:2}));assert(box.checkpointDecisionStale({...report,inspectedAt:now-61}));
const proposal={document:{workspaceId:'alpha',operation:'review',scope:candidate,request:{id:'fixed-request',settingsPolicy:'native_defaults',expiresAt:now+3600},expiresAt:now+300},signature:'fixture'};
box.proposal=proposal;run('checkpointPreviews.set(workspaceId,{proposal,generation:workspaceGeneration})');
result=rendered();let check=result.nodes.find(n=>n.type==='checkbox'),submit=result.nodes.find(n=>n.text==='Record checkpoint review');
assert.equal(check.checked,false);assert(submit.disabled);check.checked=true;check.onchange();assert.equal(submit.disabled,false);
assert.equal(rendered().nodes.find(n=>n.type==='checkbox').checked,false);
run('workspaceGeneration++');rendered();assert.equal(run('checkpointPreviews.size'),0);
run("workspaceId='beta';workspaceGeneration++");assert.match(rendered().root.textContent,/No decision inspection/);assert.equal(run('checkpointDrafts.has("beta:review")'),false);
run("workspaceId='alpha';workspaceGeneration++");report.canReview=false;result=rendered();assert(!result.nodes.some(n=>n.tag==='select'));assert(result.nodes.some(n=>n.text==='Preview withdrawal'));report.canReview=true;
report.status='unavailable';result=rendered();assert.match(result.root.textContent,/Decision evidence unavailable/);assert(!result.nodes.some(n=>n.tag==='form'));report.status='recorded';
async function test(){
  let resolve;box.api=()=>new Promise(r=>{resolve=r});const wait=box.inspectCheckpointDecisions();run("workspaceId='beta';workspaceGeneration++");resolve(report);await wait;
  assert.equal(run('checkpointDecisions.has("beta")'),false);assert.equal(run('checkpointDecisionPending.size'),0);
  run("workspaceId='alpha';workspaceGeneration++");let reject;box.api=()=>new Promise((r,j)=>{reject=j});const old=box.inspectCheckpointDecisions();run('workspaceGeneration+=2');reject(new Error('late'));await old;assert.equal(run('notices.length'),0);
  box.api=async()=>report;await box.inspectCheckpointDecisions();assert.equal(run('checkpointDecisions.get(workspaceId).status'),'recorded');
  box.api=()=>new Promise(r=>{resolve=r});const pending=box.previewCheckpointDecision({operation:'review'});run('workspaceGeneration++');resolve(proposal);await pending;assert.equal(run('checkpointPreviews.size'),0);
  box.api=async()=>proposal;await box.previewCheckpointDecision({operation:'review'});const entry=run('checkpointPreviews.get(workspaceId)'),sent=[];
  box.api=async(path,options)=>{sent.push(JSON.parse(options.body));throw new Error('Response lost')};
  await box.confirmCheckpointDecision(entry);assert(entry.uncertain);assert.equal(sent[0].proposal.document.request.id,'fixed-request');
  result=rendered();assert(result.nodes.some(n=>n.text==='Retry the same confirmation'));assert.equal(result.nodes.find(n=>n.type==='checkbox').checked,false);
  await box.confirmCheckpointDecision(entry);assert.deepEqual(sent[0],sent[1]);assert.equal(run('checkpointDrafts.get("alpha:review").minutes'),'60');
  let saves=0;box.api=async(path)=>{if(path.endsWith('/confirm')){saves++;return {replayed:true}}return report};
  await box.confirmCheckpointDecision(entry);assert.equal(saves,1);assert.equal(run('checkpointPreviews.size'),0);assert.match(run('notices.at(-1)'),/no authority was reapplied/);
  await box.confirmCheckpointDecision(entry);assert.equal(saves,1);
  const withdrawal={...proposal,document:{...proposal.document,operation:'withdraw',scope:oldReview,request:{checkpointReviewHash:oldReview.checkpointReviewHash,reason:'<script>literal</script>'}}};box.withdrawal=withdrawal;
  run('checkpointPreviews.set(workspaceId,{proposal:withdrawal,generation:workspaceGeneration})');result=rendered();assert.equal(result.nodes.filter(n=>n.type==='checkbox').length,1);assert(result.nodes.some(n=>n.text==='Withdraw this review'));assert.match(result.root.textContent,/does not stop or revoke a run already authorized/);assert.match(result.root.textContent,/<script>literal/);
  console.log('Checkpoint owner UI: explicit choices, confirmation, project guards, stable settings and immutable retries passed');
}
test().catch(error=>{console.error(error);process.exitCode=1});
