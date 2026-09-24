"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag,text=''){this.tag=tag;this.text=text;this.children=[];this.disabled=false;}
  append(...children){this.children.push(...children);}
}
const messages=[],sent=[];
const box={Map,Set,JSON,Math,String,crypto:{randomUUID:()=>`request-${sent.length}`},setTimeout:()=>1,workspaceId:'alpha',busy:false,connected:true,csrf:'fixture',selected:null,
  state:{standard:{available:true,contextHash:'h',boundary:'Partial observations',catalog:{models:[{model:'native',efforts:['low']}]},run:null},mission:null},
  el:(tag,text)=>new Element(tag,text),button:(text,callback)=>Object.assign(new Element('button',text),{click:callback}),
  section:(text)=>new Element('h2',text),table:(heads,rows)=>new Element('table',JSON.stringify(rows)),
  callout:(a,b)=>new Element('p',a+' '+b),num:String,when:String,textCell:(a,b)=>a+' '+b,
  missionDocument(){},render(){},updateWorkspaceSelector(){},refresh:async()=>{},showNotice:(message)=>messages.push(message),
  api:async(path,opts)=>{sent.push({path,body:JSON.parse(opts.body)});if(path.endsWith('preview'))return {preview:{operation:'play',brainAllowance:1,durationHours:8,expiresAt:1},signature:'signed'};return {result:'Recorded'};}};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/standard.js','utf8'),box);
const render=()=>{const root=new Element('root');box.standardPanel(root);return root;};
function all(root){return [root,...root.children.flatMap(x=>x instanceof Element?all(x):[])];}
(async()=>{
  let nodes=all(render());await nodes.find(n=>n.text==='Review Play').click();
  nodes=all(render());let confirm=nodes.find(n=>n.text==='Confirm play');assert.equal(confirm.disabled,true);
  let check=nodes.find(n=>n.type==='checkbox');check.checked=true;check.onchange();assert.equal(confirm.disabled,false);
  box.workspaceId='beta';assert.ok(!all(render()).some(n=>n.text==='Confirm play'),'Project preview isolation');
  box.workspaceId='alpha';await confirm.click();assert.equal(sent.filter(s=>s.path.endsWith('confirm')).length,1);
  box.state.standard.run={id:'run',status:'running',phaseId:'p',tasks:[],limits:{maxTasks:2,checkpointReserveTokens:10},brainUsageCoverage:'not_observed'};
  box.state.standard.observedTokens=null;nodes=all(render());assert.ok(nodes.some(n=>String(n.text).includes('Not observed')));
  assert.ok(nodes.some(n=>n.text==='Pause at safe checkpoint'));
  assert.ok(nodes.some(n=>String(n.text).includes('manual (default)')));
  box.state.standard.run.limits.mergeMode='brain_exact_pr_v1';
  for(const status of ['prepared','issued','uncertain','merged','not-merged']){
    box.state.standard.run.merges=[{requestId:'m',status,prUrl:'https://github.com/fixture/project/pull/7',headSHA:'a'.repeat(40),bindingHash:'b'.repeat(64)}];
    nodes=all(render());assert.ok(nodes.some(n=>String(n.text).includes(status)));
    assert.ok(nodes.some(n=>String(n.text).includes('requires independent checks')));
    assert.ok(!nodes.some(n=>n.tag==='button'&&String(n.text).includes('Merge')),'Dashboard cannot send a merge');
  }
  box.state.standard.run.status='stopping';assert.equal(all(render()).find(n=>n.text==='Pause at safe checkpoint').disabled,true);
  box.state.standard.run.status='paused';assert.ok(all(render()).some(n=>n.text==='Review Resume'));
  box.state.standard.run.usageGuardVersion=1;
  box.state.standard.measuredUsage={tokens:{input_tokens:100,cached_input_tokens:50,output_tokens:20,reasoning_output_tokens:5,total_tokens:120},
    collectedAt:1,coverage:'gapped',gaps:['missing_prefix'],remainingMeasured:null};
  assert.ok(all(render()).some(n=>n.tag==='table'&&n.text.includes('Measured remaining')&&n.text.includes('Unknown')));
  box.state.brainHandoff={handoff:null,readiness:{canPrepare:true,canFinalize:false,blockers:[]}};
  const priorApi=box.api;
  box.api=async(path,opts)=>{
    if(path.endsWith('/brain-handoff/preview')){sent.push({path,body:JSON.parse(opts.body)});return {preview:{expiresAt:100},package:{kind:'fixture'},signature:'signed'};}
    if(path.endsWith('/brain-handoff/confirm')){sent.push({path,body:JSON.parse(opts.body)});return {result:'Prepared'};}
    return priorApi(path,opts);};
  await all(render()).find(n=>n.text==='Review brain handoff').click();
  nodes=all(render());const handoffConfirm=nodes.find(n=>n.text==='Confirm handoff preparation');
  assert.equal(handoffConfirm.disabled,true);
  const handoffBox=nodes.filter(n=>n.type==='checkbox').at(-1);handoffBox.checked=true;handoffBox.onchange();
  assert.equal(handoffConfirm.disabled,false);await handoffConfirm.click();
  assert.ok(sent.some(s=>s.path.endsWith('/brain-handoff/confirm')));
  box.state.brainHandoff={readiness:{canPrepare:false,canFinalize:false,blockers:['Fresh native task-list project membership required before rebinding']},handoff:{status:'received',packageHash:'hash',oldBrainId:'old',
    candidate:{taskId:'new',projectId:'native-a',observation:'Owner observed native project'},
    receipt:{summary:'Exact package reviewed'},receiptEvidence:{source:'local_native_final_reply',observedAt:1}}};
  nodes=all(render());
  assert.ok(nodes.some(n=>String(n.text).includes('Native final reply observed')));
  assert.ok(nodes.some(n=>String(n.text).includes('separate Codex task-list observation')));
  assert.ok(!nodes.some(n=>n.text==='Review replacement receipt'));
  assert.ok(nodes.some(n=>String(n.text).includes('Fresh native task-list project membership required')));
  box.state.brainHandoff.handoff.nativeMembership={projectId:'native-a',hostId:'local',status:'active',observedAt:Date.now()/1000};
  assert.ok(!all(render()).some(n=>n.text==='Review replacement receipt'));
  box.state.brainHandoff.handoff.nativeMembership.status='idle';
  box.state.brainHandoff.readiness={canPrepare:false,canFinalize:true,blockers:[]};
  nodes=all(render());
  assert.ok(nodes.some(n=>String(n.text).includes('Codex task list: native-a')));
  assert.ok(nodes.some(n=>n.text==='Review replacement receipt'));
  box.state.brainHandoff.handoff.nativeMembership.observedAt-=7200;
  assert.ok(!all(render()).some(n=>n.text==='Review replacement receipt'),'Expired browser observation cannot show a review action');
  box.state.standard={available:false,catalogRequired:true,contextHash:'missing',boundary:'Partial observations',catalog:null,run:null,
    blocker:'Brain must record the available native model/effort catalog (valid for 24 hours)',catalogRefresh:null};
  nodes=all(render());const prepare=nodes.find(n=>n.text==='Review Play');assert.equal(prepare.disabled,false);
  await prepare.click();assert.equal(sent.filter(s=>s.path.endsWith('catalog-refresh')).length,1);
  assert.equal(sent.filter(s=>s.path==='/api/standard/preview').length,1,'Capability collection does not bypass the separate Play preview');
  box.state.standard.catalogRefresh={id:'request',status:'queued',createdAt:Date.now()/1000,result:'Waiting',notification:{status:'accepted'},deliveryAttempts:1,maxDeliveryAttempts:3};
  nodes=all(render());assert.equal(nodes.find(n=>n.textContent==='Waiting for native capabilities').disabled,true);
  assert.ok(nodes.some(n=>String(n.text).includes('Waiting for the designated brain')));
  console.log('Standard UI: explicit confirmation, project separation, unknown usage and checkpoint controls passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
