"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const box={titles:{},Map,Date,window:{addEventListener(){}}};vm.createContext(box);
for(const name of ['routing.js','run-readiness.js'])vm.runInContext(fs.readFileSync('web/'+name,'utf8'),box);
assert.equal(box.dashboardRoute('#/w/alpha/runReadiness').view,'runReadiness');
assert.equal(box.runInspectionState(null,{meta:{}},100).label,'Not inspected');
const report={workspaceRevision:1,generatedAt:90},state={meta:{revision:1}};
assert.equal(box.runInspectionState(report,state,100).stale,false);
assert.equal(box.runInspectionState(report,{meta:{revision:2}},100).stale,true);
assert.equal(box.runInspectionState(report,state,151).stale,true);
assert.equal(box.runInspectionState(report,state,89).stale,true);
const code=fs.readFileSync('web/run-readiness.js','utf8');
assert(!code.includes('innerHTML'));assert(!code.includes('localStorage'));assert(!code.includes('sessionStorage'));
assert(!code.includes('/api/commands'));assert(!code.includes("method:'POST'"));
// Export the captured report, never the currently selected workspace or a new scan.
let exported,clicked=false,removed=false,attached=false,revoked=false;
const anchor={click(){assert(attached);clicked=true},remove(){removed=true}};
box.Blob=class{constructor(parts,options){exported={text:parts.join(''),type:options.type}}};
box.URL={createObjectURL(){return 'blob:fixture'},revokeObjectURL(url){assert.equal(url,'blob:fixture');revoked=true}};
box.document={createElement(tag){assert.equal(tag,'a');return anchor},body:{append(node){assert.equal(node,anchor);attached=true}}};
box.setTimeout=fn=>fn();
box.downloadRunInspection({...report,workspaceId:'alpha',executionAuthorized:false});
assert.equal(JSON.parse(exported.text).workspaceId,'alpha');assert.equal(exported.type,'application/json');
assert.equal(anchor.download,'run-readiness-alpha.json');assert(clicked&&removed&&revoked);
// Late results must not leak to a new workspace or overwrite the current view.
vm.runInContext("let workspaceId='alpha',workspaceGeneration=1,connected=true,view='runReadiness';let renders=0;function render(){renders++}function showNotice(){}",box);
let resolve;box.api=()=>new Promise(r=>{resolve=r});
const waiting=box.inspectRunReadiness();
vm.runInContext("workspaceId='beta';workspaceGeneration++",box);
resolve({workspaceId:'alpha',workspaceRevision:1,generatedAt:90});
waiting.then(()=>{
  assert.equal(vm.runInContext('runInspections.size',box),0);
  assert.equal(vm.runInContext('runInspectionPending.size',box),0);
  assert.equal(vm.runInContext('renders',box),1);
  console.log('Run inspection scope, staleness, no mutation and late-response checks passed');
}).catch(e=>{console.error(e);process.exitCode=1;});
