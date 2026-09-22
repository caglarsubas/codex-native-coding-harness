"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const box={Map,Date,Blob,setTimeout:fn=>fn(),URL:{createObjectURL(){return 'blob:fixture'},revokeObjectURL(){}}};vm.createContext(box);
const source=fs.readFileSync('web/budget.js','utf8');vm.runInContext(source,box);
for(const forbidden of ['innerHTML','localStorage','sessionStorage','/api/commands',"method:'POST'"])assert(!source.includes(forbidden));
class Element{
  constructor(tag,text,cls){this.tag=tag;this.text=text||'';this.className=cls;this.children=[];}
  append(...nodes){this.children.push(...nodes)}
  setAttribute(){} addEventListener(){} remove(){} click(){}
  get textContent(){return this.text+this.children.map(n=>typeof n==='string'?n:n.textContent).join(' ')}
}
box.el=(...args)=>new Element(...args);box.empty=(a,b)=>new Element('section',a+' '+b);box.callout=box.empty;box.section=box.empty;
box.button=(text,action)=>Object.assign(new Element('button',text),{action});box.when=String;box.num=String;
box.table=(headers,rows)=>new Element('table',headers.join(' ')+rows.map(r=>r.join(' ')).join(' '));
vm.runInContext("let workspaceId='alpha',workspaceGeneration=1,connected=true,view='usage';let state={workspace:{name:'Alpha'},meta:{revision:1}};let renders=0,notices=0;function render(){renders++}function showNotice(){notices++}",box);
let calls=0;box.api=()=>{calls++;throw new Error('Render must not inspect')};
let root=new Element('main');box.budgetView(root);assert.match(root.textContent,/has not been inspected/);assert.equal(calls,0);
const now=Date.now()/1000,report={workspaceId:'alpha',workspaceRevision:1,inspectedAt:now,status:'available',boundary:'Recorded, not permission',allocations:[
  {allocationId:'phase-fixture',phaseId:'<script>Literal title</script>',closed:false,observedAt:now,expiresAt:now+60,issues:[],limits:{tokenBudget:10000,maxTasks:3,maxParallelTasks:1},observedTokens:0,heldTokens:1000,unincorporatedSettledTokens:500,checkpointReserveTokens:1000,recordedBalance:7500,recordedClaims:2,heldClaims:1,settledClaims:1}],
  account:{status:'headroom_observed',observedAt:now,expiresAt:now+60,windows:{short:{remainingPercent:70,resetsAt:now+3600},long:null},issues:['long_window_missing']},
  sharedCapacity:{recordedHeldClaims:2,maximumParallelTasks:4}};
box.report=report;vm.runInContext('budgetReports.set(workspaceId,report)',box);
root=new Element('main');box.budgetView(root);assert.equal(calls,0);
for(const phrase of ['7500','Literal title','Held task estimates','Settled, not yet incorporated','Unknown','not free capacity','not an account wallet','70%'])assert(root.textContent.includes(phrase));
const state={meta:{revision:1}},row=report.allocations[0];
assert.equal(box.budgetBalance(row,report,state,now),7500);
assert.equal(box.budgetBalance({...row,recordedBalance:-500},report,state,now),-500);
assert.equal(box.budgetBalance({...row,recordedBalance:null},report,state,now),null);
assert.equal(box.budgetBalance(row,report,state,now+61),null);
assert.equal(box.budgetBalance(row,report,state,now-1),null);
assert.equal(box.budgetBalance(row,report,{meta:{revision:2}},now),null);
row.recordedBalance=null;row.observedTokens=null;row.issues=['usage_not_observed'];
root=new Element('main');box.budgetView(root);assert.match(root.textContent,/Observed cumulative usage Unknown/);assert.match(root.textContent,/Balance after recorded charges Unknown/);
report.status='not_initialized';root=new Element('main');box.budgetView(root);assert.match(root.textContent,/No admission ledger exists/);assert(!root.textContent.includes('7500'));
report.status='unavailable';root=new Element('main');box.budgetView(root);assert.match(root.textContent,/Accounting is unavailable/);
// Overview only links; it does not inspect automatically either.
box.navigateView=()=>{};root=new Element('main');box.budgetSummary(root);assert.match(root.textContent,/Inspect budgets in Token usage/);assert.equal(calls,0);
async function test(){
  let resolve;box.api=()=>new Promise(r=>{resolve=r});const wait=box.inspectBudget();
  vm.runInContext("workspaceId='beta';workspaceGeneration++",box);resolve(report);await wait;
  assert.equal(vm.runInContext('budgetReports.has("beta")',box),false);
  assert.equal(vm.runInContext('budgetPending.size',box),0);
  vm.runInContext("workspaceId='alpha';workspaceGeneration++",box);
  let reject;box.api=()=>new Promise((r,j)=>{reject=j});const old=box.inspectBudget();
  vm.runInContext('workspaceGeneration+=2',box);reject(new Error('late'));await old;
  assert.equal(vm.runInContext('notices',box),0);
  box.api=async path=>{assert.equal(path,'/api/budget');return {...report,status:'empty',allocations:[]}};
  await box.inspectBudget();assert.equal(vm.runInContext('budgetReports.get("alpha").status',box),'empty');
  box.api=async()=>{throw new Error('offline')};await box.inspectBudget();
  assert.equal(vm.runInContext('budgetReports.has("alpha")',box),false);assert.equal(vm.runInContext('notices',box),1);
  // Export uses the inspected workspace, not whichever workspace is now selected.
  let anchor;box.document={body:new Element('body'),createElement:tag=>(anchor=new Element(tag))};
  vm.runInContext("workspaceId='beta'",box);box.downloadBudget(report);assert.equal(anchor.download,'budget-alpha.json');
  console.log('Budget read-only rendering, unknown/zero/negative values, freshness, project races and scoped export checks passed');
}
test().catch(error=>{console.error(error);process.exitCode=1});
