"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const box={Map,Date};vm.createContext(box);
const source=fs.readFileSync('web/observer-controls.js','utf8');vm.runInContext(source,box);
for(const forbidden of ['innerHTML','localStorage','sessionStorage','/api/commands','/api/play','/collect','/connect'])assert(!source.includes(forbidden));
class Element{constructor(tag,text,cls){this.tag=tag;this.text=text||'';this.className=cls;this.children=[];}append(...nodes){this.children.push(...nodes)}reportValidity(){return true}get textContent(){return this.text+this.children.map(n=>typeof n==='string'?n:n.textContent).join(' ')}}
box.el=(...args)=>new Element(...args);box.callout=box.section=(a,b)=>new Element('section',a+' '+(b||''));
box.button=(text,action)=>Object.assign(new Element('button',text),{action});box.when=String;box.num=String;
vm.runInContext("let workspaceId='alpha',workspaceGeneration=1,connected=true,view='runReadiness',busy=false,selected=null,csrf='fixture';let state={workspace:{name:'Alpha'},meta:{revision:1}};let notices=[];function render(){}function showNotice(s){notices.push(s)}function updateWorkspaceSelector(){}async function refresh(){}",box);
const run=s=>vm.runInContext(s,box),walk=root=>[root,...root.children.flatMap(n=>typeof n==='string'?[]:walk(n))];
function panel(){const root=new Element('main');box.observerControlPanel(root);return root;}
function click(root,label){const node=walk(root).find(n=>n.tag==='button'&&n.text===label);assert(node,label);node.action();}
let calls=0;box.api=()=>{calls++;throw new Error('Render cannot inspect')};assert.match(panel().textContent,/No observer inspection/);assert.equal(calls,0);
const now=Date.now()/1000,endpoint={executable:'/fixture/codex',socket:'/fixture/socket',serverIdentityHash:'a'.repeat(64),sha256:'b'.repeat(64)};
const report={workspaceId:'alpha',workspaceRevision:1,inspectedAt:now,status:'recorded',contextHash:'c'.repeat(64),canReview:true,canRevoke:true,
  endpoint:{version:1,at:now,endpoint,endpointHash:'e'.repeat(64),revoked:false},history:[],omittedHistory:0,allocations:[{allocationId:'phase-a',repositories:['repo-a']},{allocationId:'phase-b',repositories:['repo-b']}],
  reportsStatus:'recorded',reports:[{reportHash:'r'.repeat(64),allocationId:'phase-a',version:1,finishedAt:now,sampleCount:1,activityCounts:{running:0,idle:1,unknown:0},trackedTerminalCount:0,endpointCurrent:true,stale:false}],omittedReports:0,
  gaps:{tree:'Complete task tree unavailable',tokens:'Lifetime counters unavailable',cleanup:'OS cleanup not verified',settings:'No per-turn settings telemetry'}};
box.report=report;run('observerReports.set(workspaceId,report)');let root=panel();assert.equal(calls,0);assert.match(root.textContent,/zero count is not OS cleanup proof/);assert.match(root.textContent,/effect context not revalidated/);
click(root,'Configure observation endpoint');root=panel();let nodes=walk(root),select=nodes.find(n=>n.tag==='select');assert.equal(select.value,'');assert(nodes.filter(n=>n.tag==='input').every(n=>n.value===''));
select.value='phase-a';select.onchange();let input=nodes.find(n=>n.tag==='input');input.value='/private/fixture/executable';input.oninput();assert.equal(run('observerDrafts.get(workspaceId).executable'),input.value);
report.allocations.reverse();assert.equal(walk(panel()).find(n=>n.tag==='select').value,'phase-a');report.allocations=report.allocations.filter(a=>a.allocationId!=='phase-a');assert.equal(walk(panel()).find(n=>n.tag==='select').value,'');
assert(box.observerStale({...report,workspaceRevision:2}));assert(box.observerStale({...report,inspectedAt:now-61}));
assert.equal(box.observerReportStale({startedAt:now,stale:false}),false);assert(box.observerReportStale({startedAt:now-61,stale:false}));assert(box.observerReportStale({startedAt:now+60,stale:false}));assert(box.observerReportStale({startedAt:now,stale:true}));
report.canReview=false;report.reviewBlocker='Allocation unavailable';root=panel();assert.match(root.textContent,/Allocation unavailable/);assert(!walk(root).some(n=>n.text==='Preview endpoint access'));assert(walk(root).some(n=>n.text==='Preview endpoint revocation'));report.canReview=true;
report.status='unavailable';assert.equal(walk(panel()).filter(n=>n.tag==='form').length,0);report.status='recorded';
const proposal={document:{workspaceId:'alpha',operation:'review',request:{id:'same-request',endpoint},allocation:{allocationId:'phase-a'},expiresAt:now+300},signature:'fixture'};
box.proposal=proposal;run('observerPreviews.set(workspaceId,{proposal,generation:workspaceGeneration,uncertain:false})');
let controls=walk(panel()),check=controls.find(n=>n.type==='checkbox'),confirm=controls.find(n=>n.text==='Record endpoint review');assert.equal(check.checked,false);assert(confirm.disabled);check.checked=true;check.onchange();assert.equal(confirm.disabled,false);assert.equal(walk(panel()).find(n=>n.type==='checkbox').checked,false);
run('workspaceGeneration++');panel();assert.equal(run('observerPreviews.size'),0);
run("workspaceId='beta';workspaceGeneration++");assert.match(panel().textContent,/No observer inspection/);assert.equal(run('observerDrafts.has(workspaceId)'),false);run("workspaceId='alpha';workspaceGeneration++");
async function test(){
  let resolve;box.api=()=>new Promise(r=>{resolve=r});let wait=box.inspectObserverControls();run("workspaceId='beta';workspaceGeneration++");resolve(report);await wait;assert.equal(run('observerReports.has("beta")'),false);assert.equal(run('observerPending.size'),0);
  run("workspaceId='alpha';workspaceGeneration++");let reject;box.api=()=>new Promise((r,j)=>{reject=j});wait=box.inspectObserverControls();run('workspaceGeneration+=2');reject(new Error('late'));await wait;assert.equal(run('notices.length'),0);
  box.api=async()=>report;await box.inspectObserverControls();box.api=()=>new Promise(r=>{resolve=r});wait=box.previewObserverControls({operation:'review'});run('workspaceGeneration++');resolve(proposal);await wait;assert.equal(run('observerPreviews.size'),0);
  box.api=async()=>proposal;await box.previewObserverControls({operation:'review'});const entry=run('observerPreviews.get(workspaceId)');const sent=[];box.api=async(path,options)=>{sent.push(JSON.parse(options.body));throw new Error('Lost response')};
  await box.confirmObserverControls(entry);assert(entry.uncertain);assert.equal(sent[0].proposal.document.request.id,'same-request');controls=walk(panel());assert(controls.some(n=>n.text==='Retry the same endpoint confirmation'));assert.equal(controls.find(n=>n.type==='checkbox').checked,false);
  await box.confirmObserverControls(entry);assert.deepEqual(sent[1],sent[0]);assert.equal(run('observerDrafts.get(workspaceId).executable'),'/private/fixture/executable');
  let saved=0;box.api=async(path)=>{if(path.endsWith('/confirm')){saved++;return {replayed:true}}return report};await box.confirmObserverControls(entry);assert.equal(saved,1);assert.equal(run('observerPreviews.size'),0);assert.match(run('notices.at(-1)'),/no access was reapplied/);await box.confirmObserverControls(entry);assert.equal(saved,1);
  const revoke={...proposal,document:{...proposal.document,operation:'revoke',request:{endpointHash:'e'.repeat(64)}}};box.revoke=revoke;run('observerPreviews.set(workspaceId,{proposal:revoke,generation:workspaceGeneration})');controls=walk(panel());assert.equal(controls.filter(n=>n.type==='checkbox').length,1);assert(controls.some(n=>n.text==='Revoke endpoint access'));
  assert(fs.readFileSync('web/run-readiness.js','utf8').includes('observerControlPanel(root)'));
  console.log('Observer UI: explicit reads and endpoint choices, historical reports, confirmation, scoped drafts, races and identical retry passed');
}
test().catch(error=>{console.error(error);process.exitCode=1});
