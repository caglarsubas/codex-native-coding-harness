"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const box={Map,Date,encodeURIComponent};vm.createContext(box);
const source=fs.readFileSync('web/rereview.js','utf8');vm.runInContext(source,box);
for(const forbidden of ['innerHTML','localStorage','sessionStorage','/api/commands','/api/play','/api/release'])assert(!source.includes(forbidden));
class Element{
  constructor(tag,text,cls){this.tag=tag;this.text=text||'';this.className=cls;this.children=[];}
  append(...nodes){this.children.push(...nodes)} reportValidity(){return true} focus(){this.focused=true}
  get textContent(){return this.text+this.children.map(n=>typeof n==='string'?n:n.textContent).join(' ')}
}
box.el=(...args)=>new Element(...args);box.callout=box.section=(a,b)=>new Element('section',a+' '+b);
box.button=(text,action)=>Object.assign(new Element('button',text),{action});box.when=String;
box.table=(headers,rows)=>new Element('table',headers.join(' ')+rows.map(r=>r.join(' ')).join(' '));
vm.runInContext("let workspaceId='alpha',workspaceGeneration=1,connected=true,view='workers',busy=false,selected=null,csrf='fixture';let state={workspace:{name:'Alpha'},meta:{revision:1},workers:[{id:'worker-one',packetId:'TASK-001',repository:'repo',status:'blocked',dispatchAdmission:{}}]};let notices=[];function render(){}function showNotice(s){notices.push(s)}function updateWorkspaceSelector(){}async function refresh(){}",box);
const run=s=>vm.runInContext(s,box),walk=root=>[root,...root.children.flatMap(n=>typeof n==='string'?[]:walk(n))];
function rendered(){const root=new Element('main');box.rereviewPanel(root);return {root,nodes:walk(root)}}
let calls=0;box.api=()=>{calls++;throw new Error('Rendering must not inspect')};
let result=rendered();assert.equal(result.nodes.find(n=>n.tag==='select').value,'');assert(result.nodes.find(n=>n.text==='Inspect result & permission').disabled);assert.equal(calls,0);
let picker=result.nodes.find(n=>n.tag==='select');picker.value='worker-one';picker.onchange();assert.match(rendered().root.textContent,/Inspect this task/);
const now=Date.now()/1000,commit='a'.repeat(40),task={packetId:'TASK-001',repository:'repo',settledAt:now,commit,baseSHA:'b'.repeat(40),allowedPaths:['src/'],acceptance:['local tests']},
  candidate={phaseId:'phase-two',generation:2,expiresAt:now+3600,goal:'Fixture only',scope:['src/']},
  report={workspaceId:'alpha',workspaceRevision:1,workerId:'worker-one',inspectedAt:now,status:'recorded',task,candidate,canAuthorize:true,canRevoke:false,contextHash:'c'.repeat(64),authority:null,permissions:[],reviews:[{outcome:'changes_required',at:now,commit,reviewHash:'d'.repeat(64),reviewArtifactId:'proof-one',axes:{source:'verified'}}]};
box.report=report;run('rereviewReports.set(rereviewKey(),report)');
result=rendered();assert.equal(calls,0);assert(result.nodes.find(n=>n.tag==='input').readOnly);assert.equal(result.nodes.find(n=>n.tag==='input').value,commit);
let reason=result.nodes.find(n=>n.tag==='textarea');reason.value='<script>literal reason</script>';reason.oninput();assert.equal(run('rereviewDrafts.get("alpha:worker-one:authorize").reason'),reason.value);
const history=result.nodes.find(n=>n.tag==='details'&&n.textContent.includes('Review versions'));history.open=true;history.ontoggle();assert(rendered().nodes.find(n=>n.tag==='details'&&n.textContent.includes('Review versions')).open);
task.commit=null;result=rendered();let input=result.nodes.find(n=>n.tag==='input');assert.equal(input.value,'');assert.equal(input.readOnly,false);input.value=commit;input.oninput();assert.equal(rendered().nodes.find(n=>n.tag==='input').value,commit);task.commit=commit;
assert(box.rereviewStale({...report,workspaceRevision:2}));assert(box.rereviewStale({...report,inspectedAt:now-61}));
const proposal={document:{workspaceId:'alpha',operation:'authorize',scope:{task,run:candidate},request:{id:'fixed-request',workerId:'worker-one',commit,reason:'<script>literal</script>'},expiresAt:now+300},signature:'fixture'};
box.proposal=proposal;run('rereviewPreviews.set(rereviewKey(),{proposal,generation:workspaceGeneration})');
result=rendered();let check=result.nodes.find(n=>n.type==='checkbox'),submit=result.nodes.find(n=>n.text==='Authorize this review');assert.equal(check.checked,false);assert(submit.disabled);check.checked=true;check.onchange();assert.equal(submit.disabled,false);assert.match(result.root.textContent,/<script>literal/);assert.equal(rendered().nodes.find(n=>n.type==='checkbox').checked,false);
run('workspaceGeneration++');rendered();assert.equal(run('rereviewPreviews.size'),0);
run("workspaceId='beta';workspaceGeneration++");result=rendered();assert.equal(result.nodes.find(n=>n.tag==='select').value,'');assert(!result.root.textContent.includes('literal reason'));assert.equal(run('rereviewDrafts.has("beta:worker-one:authorize")'),false);
run("workspaceId='alpha';workspaceGeneration++");report.canAuthorize=false;report.blocker='Accepted results cannot reopen';assert(!rendered().nodes.some(n=>n.tag==='form'));report.canAuthorize=true;
report.status='unavailable';assert(!rendered().nodes.some(n=>n.tag==='form'));report.status='recorded';
run('state.workspace=null');assert.equal(rendered().nodes.length,1);run("state.workspace={name:'Alpha'}");
async function test(){
  let resolve;box.api=()=>new Promise(r=>{resolve=r});const pending=box.inspectRereview();run("rereviewWorkers.set(workspaceId,'worker-two')");resolve(report);await pending;assert.equal(run('rereviewReports.has("alpha:worker-two")'),false);assert.equal(run('rereviewPending.size'),0);
  run("rereviewWorkers.set(workspaceId,'worker-one')");let reject;box.api=()=>new Promise((r,j)=>{reject=j});const old=box.inspectRereview();run('workspaceGeneration+=2');reject(new Error('late'));await old;assert.equal(run('notices.length'),0);
  box.api=async()=>report;await box.inspectRereview();assert.equal(run('rereviewReports.get(rereviewKey()).status'),'recorded');
  box.api=()=>new Promise(r=>{resolve=r});const wait=box.previewRereview({operation:'authorize'});run("workspaceId='beta';workspaceGeneration++");resolve(proposal);await wait;assert.equal(run('rereviewPreviews.size'),0);
  run("workspaceId='alpha';workspaceGeneration++");box.api=async()=>proposal;await box.previewRereview({operation:'authorize'});const entry=run('rereviewPreviews.get(rereviewKey())'),sent=[];
  box.api=async(path,options)=>{sent.push(JSON.parse(options.body));throw new Error('Response lost')};await box.confirmRereview(entry);assert(entry.uncertain);assert.equal(sent[0].proposal.document.request.id,'fixed-request');
  result=rendered();assert(result.nodes.some(n=>n.text==='Retry the same confirmation'));assert.equal(result.nodes.find(n=>n.type==='checkbox').checked,false);await box.confirmRereview(entry);assert.deepEqual(sent[0],sent[1]);
  let saves=0;box.api=async(path)=>{if(path.endsWith('/confirm')){saves++;return {replayed:true}}return report};await box.confirmRereview(entry);assert.equal(saves,1);assert.equal(run('rereviewPreviews.size'),0);assert.match(run('notices.at(-1)'),/permission was not reapplied/);await box.confirmRereview(entry);assert.equal(saves,1);
  const revoked={...proposal,document:{...proposal.document,operation:'revoke',request:{workerId:'worker-one',authorityHash:'e'.repeat(64),reason:'Owner withdraws'}}};box.revoked=revoked;run('rereviewPreviews.set(rereviewKey(),{proposal:revoked,generation:workspaceGeneration})');result=rendered();assert.equal(result.nodes.filter(n=>n.type==='checkbox').length,1);assert(result.nodes.some(n=>n.text==='Revoke review permission'));assert.match(result.root.textContent,/cannot undo acceptance/);
  const proofRoot=new Element('section');box.api=()=>new Promise(r=>{resolve=r});const proof=box.readRereviewProof('proof-one',proofRoot);run("rereviewWorkers.set(workspaceId,'worker-two')");resolve({text:'foreign proof'});await proof;assert.equal(proofRoot.children.length,0);
  run("rereviewWorkers.set(workspaceId,'worker-one')");box.api=async()=>({text:'<script>inert proof</script>'});await box.readRereviewProof('proof-one',proofRoot);assert.equal(proofRoot.children[0].tag,'pre');assert.equal(proofRoot.children[0].text,'<script>inert proof</script>');
  console.log('Result rereview UI: explicit inspection, exact commits, confirmation, isolated drafts, stale-response guards, inert proof reads and immutable retries passed');
}
test().catch(error=>{console.error(error);process.exitCode=1});
