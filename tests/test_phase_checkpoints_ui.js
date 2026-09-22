"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const box={titles:{},Map,Date,URLSearchParams,window:{addEventListener(){}}};vm.createContext(box);
for(const file of ['routing.js','phase-checkpoints.js'])vm.runInContext(fs.readFileSync('web/'+file,'utf8'),box);
assert.equal(box.dashboardRoute('#/w/alpha/phaseCheckpoints').view,'phaseCheckpoints');
assert.equal(box.dashboardRoute('#/w/alpha/phaseCheckpoints/'+'a'.repeat(64)),null);
const result={workspaceRevision:1,inspectedAt:90},state={meta:{revision:1}};
assert.match(box.checkpointFreshness(null,state),/Not inspected/);
assert.match(box.checkpointFreshness(result,state,100),/not live activity/);
assert.match(box.checkpointFreshness(result,{meta:{revision:2}},100),/Project changed/);
assert.match(box.checkpointFreshness(result,state,151),/Earlier inspection/);
assert.match(box.checkpointFreshness(result,state,89),/Earlier inspection/);
const source=fs.readFileSync('web/phase-checkpoints.js','utf8');
for(const forbidden of ['innerHTML','localStorage','sessionStorage','/api/commands',"method:'POST'"])assert(!source.includes(forbidden));
// A tiny text-only DOM captures copy and semantic controls without browser dependencies.
class Element{
  constructor(tag,text,cls){this.tag=tag;this.text=text||'';this.className=cls;this.children=[];}
  append(...nodes){this.children.push(...nodes)}
  setAttribute(){} addEventListener(){}
  get textContent(){return this.text+this.children.map(n=>typeof n==='string'?n:n.textContent).join(' ')}
}
box.el=(...args)=>new Element(...args);box.empty=(a,b)=>new Element('section',a+' '+b);box.callout=box.empty;box.section=box.empty;
box.button=(text,action)=>Object.assign(new Element('button',text),{action});box.textCell=box.empty;box.when=String;box.num=String;
box.table=(headers,rows)=>new Element('table',headers.join(' ')+rows.map(r=>r.map(v=>v instanceof Element?v.textContent:v).join(' ')).join(' '));
vm.runInContext("let workspaceId='alpha',workspaceGeneration=1,connected=true,view='phaseCheckpoints';let state={workspace:{name:'Alpha'},meta:{revision:1},observations:{artifacts:[]}};let renders=0,notices=0;function render(){renders++}function showNotice(){notices++}",box);
let calls=0;box.api=()=>{calls++;throw new Error('View must not fetch')};
let root=new Element('main');box.phaseCheckpointsView(root);assert.match(root.textContent,/No report history loaded/);assert.equal(calls,0);
vm.runInContext("checkpointReports.set(workspaceId,{status:'unavailable',workspaceRevision:1,inspectedAt:90,detail:'Bound report fixture'})",box);
root=new Element('main');box.phaseCheckpointsView(root);assert.match(root.textContent,/Bound report fixture/);vm.runInContext('checkpointReports.clear()',box);
const history={workspaceId:'alpha',workspaceRevision:1,inspectedAt:90,kind:'history',status:'empty',total:0,reports:[]};
box.history=history;vm.runInContext('checkpointHistory.set(workspaceId,history)',box);
root=new Element('main');box.phaseCheckpointsView(root);assert.match(root.textContent,/No saved phase reports/);assert.equal(calls,0);
history.status='history_limit';history.total=129;history.limit=128;
root=new Element('main');box.phaseCheckpointsView(root);assert.match(root.textContent,/No partial history/);
root=new Element('main');box.checkpointReportView(root,{...result,status:'unavailable',detail:'Missing evidence'});assert.match(root.textContent,/Report evidence unavailable/);assert(!root.textContent.includes('Accepted worker'));
// Responses/errors after switching away and back are discarded, even for the same ID.
async function test(){
  let resolve;box.api=()=>new Promise(r=>{resolve=r});
  const wait=box.loadPhaseCheckpoints();
  vm.runInContext("workspaceId='beta';workspaceGeneration++",box);resolve(history);await wait;
  assert.equal(vm.runInContext('checkpointHistory.has("beta")',box),false);
  assert.equal(vm.runInContext('checkpointPending.size',box),0);
  assert.equal(vm.runInContext('renders',box),1);
  vm.runInContext("workspaceId='alpha';workspaceGeneration++",box);
  let reject;box.api=()=>new Promise((r,j)=>{reject=j});
  const old=box.loadPhaseCheckpoints({reportHash:'a'.repeat(64),artifactId:'b'.repeat(64)});
  vm.runInContext('workspaceGeneration+=2',box);reject(new Error('late'));await old;
  assert.equal(vm.runInContext('notices',box),0);
  box.api=async path=>{assert.match(path,/reportHash=a{64}&artifactId=b{64}$/);return {...result,workspaceId:'alpha',status:'unavailable'}};
  await box.loadPhaseCheckpoints({reportHash:'a'.repeat(64),artifactId:'b'.repeat(64)});
  assert.equal(vm.runInContext('checkpointReports.get("alpha").status',box),'unavailable');
  box.api=async()=>({...history,status:'empty',total:0});await box.loadPhaseCheckpoints();
  assert.equal(vm.runInContext('checkpointReports.has("alpha")',box),false);
  console.log('Checkpoint routing, copy, read-only rendering, freshness and project-race checks passed');
}
test().catch(error=>{console.error(error);process.exitCode=1});
