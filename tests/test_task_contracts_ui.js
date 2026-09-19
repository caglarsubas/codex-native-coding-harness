"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function node(tag,text,cls){return {tag,text,cls,children:[],append(...nodes){this.children.push(...nodes)},replaceChildren(...nodes){this.children=nodes}};}
const box={Object,encodeURIComponent,el:node,badge:text=>node('badge',text),num:String,when:String,table:(head,rows)=>({head,rows})};vm.createContext(box);
const code=fs.readFileSync('web/task-contracts.js','utf8');vm.runInContext(code,box);
assert(box.canLegacyApprove({status:'proposed'}));assert(!box.canLegacyApprove({status:'approved'}));
for(const taskContract of [null,{},false,{hash:'x'}])assert(!box.canLegacyApprove({status:'proposed',taskContract}));
const root=node('root');box.taskContractSummary(root,{status:'bound',operations:['edit','test'],estimatedTokens:100,
  settings:{requested:{model:'fixture-model',effort:null,speed:null}}});
const text=JSON.stringify(root);assert(text.includes('Bound · not activated'));assert(text.includes('Not applied / unknown'));
assert(text.includes('Use native default'));assert(text.includes('fixture-model'));assert(text.includes('estimate only'));
assert(!code.includes('innerHTML'));assert(!code.includes("method:'POST'"));assert(!code.includes('localStorage'));
// Ignore a late response from another workspace, even if a stub API returns it.
vm.runInContext("let workspaceId='a',workspaceGeneration=1;",box);
let resolve;box.api=url=>{assert.equal(url,'/api/task-contract?queueId=a%3ATEST-001');return new Promise(r=>resolve=r)};
const panel=node('root');box.taskContractPanel(panel,{id:'a:TEST-001',taskContract:{hash:'fixture'}});
vm.runInContext("workspaceId='b';workspaceGeneration++",box);
resolve({status:'bound',document:{version:1,spec:{rationale:'foreign workspace text'}}});
Promise.resolve().then(()=>{assert(!JSON.stringify(panel).includes('foreign workspace text'));console.log('Task contract presentation, legacy approval fence and stale-response checks passed');}).catch(e=>{console.error(e);process.exitCode=1});
