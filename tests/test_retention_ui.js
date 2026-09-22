"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const box={Map,Date,titles:{}};vm.createContext(box);
const source=fs.readFileSync('web/retention.js','utf8');vm.runInContext(source,box);
for(const forbidden of ['innerHTML','localStorage','sessionStorage','/api/commands','/api/play','/api/archive'])assert(!source.includes(forbidden));
class Element{
  constructor(tag,text,cls){this.tag=tag;this.text=text||'';this.className=cls;this.children=[];}
  append(...nodes){this.children.push(...nodes)}
  reportValidity(){return true}
  get textContent(){return this.text+this.children.map(n=>typeof n==='string'?n:n.textContent).join(' ')}
}
box.el=(...args)=>new Element(...args);box.empty=(a,b)=>new Element('section',a+' '+b);box.callout=box.empty;box.section=box.empty;
box.button=(text,action)=>Object.assign(new Element('button',text),{action});box.when=String;box.num=String;
box.table=(headers,rows)=>new Element('table',headers.join(' ')+rows.map(r=>r.join(' ')).join(' '));
vm.runInContext("let workspaceId='alpha',workspaceGeneration=1,connected=true,view='retention',busy=false,selected=null,csrf='fixture';let state={workspace:{name:'Alpha'},meta:{revision:1}};let renders=0,notices=[];function render(){renders++}function showNotice(s){notices.push(s)}function updateWorkspaceSelector(){}async function refresh(){}",box);
const run=s=>vm.runInContext(s,box),walk=root=>[root,...root.children.flatMap(n=>typeof n==='string'?[]:walk(n))];
let calls=0;box.api=()=>{calls++;throw new Error('Render must not inspect')};
let root=new Element('main');box.retentionView(root);assert.match(root.textContent,/No policy inspection/);assert.equal(calls,0);
const now=Date.now()/1000,report={workspaceId:'alpha',workspaceRevision:1,inspectedAt:now,status:'recorded',contextHash:'c'.repeat(64),canReview:true,canRevoke:true,
  currentRun:{phaseId:'phase-fixture',generation:1,expiresAt:now+3600,maxArchives:3,runHash:'r'.repeat(64)},history:[],omittedHistory:0,
  policy:{phaseId:'phase-fixture',version:1,generation:1,maxArchives:2,minimumRetentionSeconds:0,at:now,expiresAt:now+3600,recordedAttempts:1,revoked:false,matchesCurrentRun:true,policyHash:'p'.repeat(64)}};
box.report=report;run('retentionReports.set(workspaceId,report)');
root=new Element('main');box.retentionView(root);assert.equal(calls,0);
const nodes=walk(root),inputs=nodes.filter(n=>n.tag==='input');assert.equal(inputs.length,2);assert(inputs.every(n=>n.value===''));
inputs[0].value='2';inputs[0].oninput();inputs[1].value='3600';inputs[1].oninput();assert.equal(run('retentionDrafts.get("alpha:review").maxArchives'),'2');
assert.match(root.textContent,/cancelled, rejected or uncertain/);assert.match(root.textContent,/cannot cancel a native call/);
assert(box.retentionStale({...report,workspaceRevision:2}));assert(box.retentionStale({...report,inspectedAt:now-61}));
const proposal={document:{workspaceId:'alpha',operation:'review',run:report.currentRun,request:{id:'same-request',maxArchives:2,minimumRetentionSeconds:3600},expiresAt:now+300},signature:'fixture'};
box.proposal=proposal;run('retentionPreviews.set(workspaceId,{proposal,generation:workspaceGeneration,uncertain:false})');
function confirmation(){const r=new Element('main');box.retentionView(r);return walk(r)}
let controls=confirmation(),checks=controls.filter(n=>n.type==='checkbox'),approve=controls.find(n=>n.text==='Approve retention for this run');
assert.equal(checks.length,2);assert(checks.every(n=>n.checked===false));assert(approve.disabled);
checks[0].checked=true;checks[0].onchange();assert(approve.disabled);checks[1].checked=true;checks[1].onchange();assert.equal(approve.disabled,false);
assert(confirmation().filter(n=>n.type==='checkbox').every(n=>n.checked===false));
run('workspaceGeneration++');confirmation();assert.equal(run('retentionPreviews.size'),0);
run("workspaceId='beta';workspaceGeneration++");root=new Element('main');box.retentionView(root);assert.match(root.textContent,/No policy inspection/);
assert.equal(run('retentionDrafts.has("beta:review")'),false);
run("workspaceId='alpha';workspaceGeneration++");report.status='unavailable';root=new Element('main');box.retentionView(root);assert.match(root.textContent,/Policy evidence unavailable/);assert.equal(walk(root).filter(n=>n.tag==='form').length,0);report.status='recorded';
async function test(){
  let resolve;box.api=()=>new Promise(r=>{resolve=r});const wait=box.inspectRetention();run("workspaceId='beta';workspaceGeneration++");resolve(report);await wait;
  assert.equal(run('retentionReports.has("beta")'),false);assert.equal(run('retentionPending.size'),0);
  run("workspaceId='alpha';workspaceGeneration++");
  let reject;box.api=()=>new Promise((r,j)=>{reject=j});const old=box.inspectRetention();run('workspaceGeneration+=2');reject(new Error('late'));await old;assert.equal(run('notices.length'),0);
  box.api=async()=>report;await box.inspectRetention();assert.equal(run('retentionReports.get(workspaceId).status'),'recorded');
  box.api=()=>new Promise(r=>{resolve=r});const preview=box.previewRetention({operation:'review'});run('workspaceGeneration++');resolve(proposal);await preview;assert.equal(run('retentionPreviews.size'),0);
  box.api=async()=>proposal;await box.previewRetention({operation:'review'});const entry=run('retentionPreviews.get(workspaceId)');
  const sent=[];box.api=async(path,options)=>{sent.push(JSON.parse(options.body));throw new Error('Network response lost')};
  await box.confirmRetention(entry,{confirmed:true,cleanupAcknowledged:true});assert(entry.uncertain);assert.equal(sent[0].proposal.document.request.id,'same-request');
  controls=confirmation();assert(controls.some(n=>n.text==='Retry the same confirmation'));assert(controls.filter(n=>n.type==='checkbox').every(n=>!n.checked));
  await box.confirmRetention(entry,{confirmed:true,cleanupAcknowledged:true});assert.deepEqual(sent[1],sent[0]);assert.equal(run('retentionDrafts.get("alpha:review").maxArchives'),'2');
  let saved=0;box.api=async(path,options)=>{if(path.endsWith('/confirm')){saved++;return {replayed:true}}return report};
  await box.confirmRetention(entry,{confirmed:true,cleanupAcknowledged:true});assert.equal(saved,1);assert.equal(run('retentionPreviews.size'),0);assert.match(run('notices.at(-1)'),/no policy was reapplied/);
  await box.confirmRetention(entry,{confirmed:true,cleanupAcknowledged:true});assert.equal(saved,1);
  // Revoke has one confirmation and never sends a cleanup acknowledgment.
  const revoke={...proposal,document:{...proposal.document,operation:'revoke',request:{policyHash:'p'.repeat(64),reason:'<script>literal reason</script>'}}};box.revoke=revoke;
  run('retentionPreviews.set(workspaceId,{proposal:revoke,generation:workspaceGeneration})');controls=confirmation();assert.equal(controls.filter(n=>n.type==='checkbox').length,1);assert(controls.some(n=>n.text==='Revoke delegation'));
  assert(controls.some(n=>n.textContent.includes('<script>literal reason</script>')));
  const routeBox={window:{addEventListener(){}}};vm.createContext(routeBox);vm.runInContext(fs.readFileSync('web/routing.js','utf8'),routeBox);
  assert.equal(routeBox.dashboardRoute('#/w/alpha/retention').view,'retention');assert.equal(routeBox.dashboardRoute('#/retention/'+ 'a'.repeat(64)),null);
  console.log('Retention UI: explicit reads, unchecked confirmations, project races, scoped drafts and immutable retries passed');
}
test().catch(error=>{console.error(error);process.exitCode=1});
