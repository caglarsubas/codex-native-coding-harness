"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const box={Map,Date};vm.createContext(box);
const source=fs.readFileSync('web/model-controls.js','utf8');vm.runInContext(source,box);
for(const forbidden of ['innerHTML','localStorage','sessionStorage','/api/commands','/api/play','/api/model-select'])assert(!source.includes(forbidden));
class Element{
  constructor(tag,text,cls){this.tag=tag;this.text=text||'';this.className=cls;this.children=[];}
  append(...nodes){this.children.push(...nodes)}
  reportValidity(){return true}
  get textContent(){return this.text+this.children.map(n=>typeof n==='string'?n:n.textContent).join(' ')}
}
box.el=(...args)=>new Element(...args);box.callout=box.section=(a,b)=>new Element('section',a+' '+(b||''));
box.button=(text,action)=>Object.assign(new Element('button',text),{action});box.when=String;box.num=String;
box.table=(headers,rows)=>new Element('table',headers.join(' ')+rows.map(r=>r.join(' ')).join(' '));
vm.runInContext("let workspaceId='alpha',workspaceGeneration=1,connected=true,view='mission',busy=false,selected=null,csrf='fixture';let state={workspace:{name:'Alpha'},meta:{revision:1}};let notices=[];function render(){}function showNotice(s){notices.push(s)}function updateWorkspaceSelector(){}async function refresh(){}",box);
const run=s=>vm.runInContext(s,box),walk=root=>[root,...root.children.flatMap(n=>typeof n==='string'?[]:walk(n))];
function panel(){const root=new Element('main');box.modelControlPanel(root);return root;}
function field(root,label){const node=walk(root).find(n=>n.tag==='label'&&n.text===label);assert(node,label);return node.children[0];}
function click(root,label){const node=walk(root).find(n=>n.tag==='button'&&n.text===label);assert(node,label);node.action();}
let calls=0;box.api=()=>{calls++;throw new Error('Render must not inspect')};
assert.match(panel().textContent,/No policy inspection/);assert.equal(calls,0);
const now=Date.now()/1000,profile={id:'reasoner',settings:{model:'fixture-reasoner',effort:'high',speed:null},quality:4,minimumWorkTokens:12000};
const report={workspaceId:'alpha',workspaceRevision:1,inspectedAt:now,status:'recorded',contextHash:'c'.repeat(64),canReview:true,canRevoke:true,
  capabilityStatus:'fresh_recorded',capability:{observedAt:now,catalog:{models:[{model:'fixture-reasoner',efforts:['high','ultra']},{model:'fixture-economy',efforts:['medium']}] }},
  candidate:{missionHash:'m'.repeat(64),phaseId:'fixture-phase'},policy:{policyHash:'p'.repeat(64),profiles:[profile],qualityFloors:{routine:1,standard:2,complex:3,critical:4},maxEscalations:1,revoked:false},history:[]};
box.report=report;run('modelReports.set(workspaceId,report)');
// Revocation-only drafts must not break later profile editing.
let root=panel();assert.equal(run('modelDrafts.get(workspaceId).reason'),'');click(root,'Configure profiles');root=panel();
assert.equal(run('modelDrafts.get(workspaceId).profiles.length'),0);assert.equal(calls,0);
assert(walk(root).filter(n=>n.tag==='select').every(n=>n.value===''));
click(root,'Add profile');root=panel();assert.equal(field(root,'Profile 1 model').value,'');
let input=field(root,'Profile 1 model');input.value='fixture-reasoner';input.onchange();root=panel();
assert.equal(field(root,'Profile 1 effort').value,'');assert(!field(root,'Profile 1 effort').children.some(n=>n.value==='ultra'));
input=field(root,'Profile 1 effort');input.value='high';input.onchange();
input=field(root,'Profile 1 minimum work tokens');input.value='12000';input.oninput();assert.equal(run('modelDrafts.get(workspaceId).profiles[0].minimumWorkTokens'),12000);
input=field(root,'Profile 1 model');input.value='fixture-economy';input.onchange();assert.equal(run('modelDrafts.get(workspaceId).profiles[0].settings.effort'),'');
click(panel(),'Copy recorded policy into draft');root=panel();assert.equal(field(root,'Profile 1 model').value,'fixture-reasoner');
report.capability.catalog.models.reverse();assert.equal(field(panel(),'Profile 1 model').value,'fixture-reasoner');
const catalog=report.capability.catalog.models;report.capability.catalog.models=[];assert.equal(field(panel(),'Profile 1 model').value,'');report.capability.catalog.models=catalog;
report.candidate.missionHash='n'.repeat(64);root=panel();assert.match(root.textContent,/earlier mission/);assert(walk(root).find(n=>n.text==='Preview model policy').disabled);
click(root,'Use draft for this mission');assert.equal(run('modelDrafts.get(workspaceId).missionHash'),report.candidate.missionHash);
assert(box.modelStale({...report,workspaceRevision:2}));assert(box.modelStale({...report,inspectedAt:now-61}));
report.canReview=false;report.reviewBlocker='Catalog stale';root=panel();assert.match(root.textContent,/Catalog stale/);assert(!walk(root).some(n=>n.text==='Preview model policy'));assert(walk(root).some(n=>n.text==='Preview model policy revocation'));report.canReview=true;
report.status='unavailable';assert.equal(walk(panel()).filter(n=>n.tag==='form').length,0);report.status='recorded';
const proposal={document:{workspaceId:'alpha',operation:'review',request:{id:'same-request',...report.policy},scope:{mission:report.candidate,capability:report.capability},expiresAt:now+300},signature:'fixture'};
box.proposal=proposal;run('modelPreviews.set(workspaceId,{proposal,generation:workspaceGeneration,uncertain:false})');
let controls=walk(panel()),check=controls.find(n=>n.type==='checkbox'),approve=controls.find(n=>n.text==='Record model policy review');
assert.equal(check.checked,false);assert(approve.disabled);check.checked=true;check.onchange();assert.equal(approve.disabled,false);
assert.equal(walk(panel()).find(n=>n.type==='checkbox').checked,false);
run('workspaceGeneration++');panel();assert.equal(run('modelPreviews.size'),0);
run("workspaceId='beta';workspaceGeneration++");assert.match(panel().textContent,/No policy inspection/);assert.equal(run('modelDrafts.has(workspaceId)'),false);
run("workspaceId='alpha';workspaceGeneration++");
async function test(){
  let resolve;box.api=()=>new Promise(r=>{resolve=r});let wait=box.inspectModelControls();run("workspaceId='beta';workspaceGeneration++");resolve(report);await wait;
  assert.equal(run('modelReports.has("beta")'),false);assert.equal(run('modelPending.size'),0);
  run("workspaceId='alpha';workspaceGeneration++");let reject;box.api=()=>new Promise((r,j)=>{reject=j});wait=box.inspectModelControls();run('workspaceGeneration+=2');reject(new Error('late'));await wait;assert.equal(run('notices.length'),0);
  box.api=async()=>report;await box.inspectModelControls();
  box.api=()=>new Promise(r=>{resolve=r});wait=box.previewModelControls({operation:'review'});run('workspaceGeneration++');resolve(proposal);await wait;assert.equal(run('modelPreviews.size'),0);
  box.api=async()=>proposal;await box.previewModelControls({operation:'review'});const entry=run('modelPreviews.get(workspaceId)');
  const sent=[];box.api=async(path,options)=>{sent.push(JSON.parse(options.body));throw new Error('Network response lost')};
  await box.confirmModelControls(entry);assert(entry.uncertain);assert.equal(sent[0].proposal.document.request.id,'same-request');
  controls=walk(panel());assert(controls.some(n=>n.text==='Retry the same policy confirmation'));assert.equal(controls.find(n=>n.type==='checkbox').checked,false);
  await box.confirmModelControls(entry);assert.deepEqual(sent[1],sent[0]);assert.equal(run('modelDrafts.get(workspaceId).profiles[0].settings.model'),'fixture-reasoner');
  let saved=0;box.api=async(path)=>{if(path.endsWith('/confirm')){saved++;return {replayed:true}}return report};
  await box.confirmModelControls(entry);assert.equal(saved,1);assert.equal(run('modelPreviews.size'),0);assert.match(run('notices.at(-1)'),/no authority was reapplied/);
  await box.confirmModelControls(entry);assert.equal(saved,1);
  const revoke={...proposal,document:{...proposal.document,operation:'revoke',request:{policyHash:report.policy.policyHash,reason:'<script>literal reason</script>'}}};box.revoke=revoke;
  run('modelPreviews.set(workspaceId,{proposal:revoke,generation:workspaceGeneration})');root=panel();assert.match(root.textContent,/<script>literal reason<\/script>/);controls=walk(root);assert.equal(controls.filter(n=>n.type==='checkbox').length,1);assert(controls.some(n=>n.text==='Revoke model policy'));
  const missionSource=fs.readFileSync('web/missions.js','utf8');assert(missionSource.includes('modelControlPanel(root)'));
  console.log('Model policy UI: explicit catalog choices, retained drafts, unchecked confirmation, scoped races and immutable retries passed');
}
test().catch(error=>{console.error(error);process.exitCode=1});
