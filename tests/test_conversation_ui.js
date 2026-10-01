"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag,text=''){this.tag=tag;this.text=text;this.children=[];this.disabled=false;this.isConnected=true;}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(name,value){this[name]=value;}
  addEventListener(name,fn){this[name]=fn;}
  scrollIntoView(options){this.scrolled=options;}
  focus(options){this.focused=options;}
}
let fail=false,pending=0,navigation=null,messages=[];const sent=[];
const box={Map,titles:{},workspaceId:'alpha',busy:false,connected:true,csrf:'fixture',crypto:{randomUUID:()=>String(sent.length)},
  state:{meta:{brainId:'brain-a',revision:1},workspace:{name:'Alpha'},repositories:[]},
  el:(tag,text)=>new Element(tag,text),button:(text,callback)=>Object.assign(new Element('button',text),{click:callback}),
  section:text=>new Element('h2',text),empty:(a,b)=>new Element('p',a+b),callout:(a,b)=>new Element('p',a+b),badge:text=>new Element('span',text),when:String,
  render(){},navigateView(view){navigation=view;},missionDocument(root,hash,label){root.append(new Element('details',label));},refresh:async()=>{assert.equal(box.busy,false);},showNotice(){},updateWorkspaceSelector(){},
  api:async(path,options)=>{if(!options)return {pending,total:messages.length,messages,hasOlder:false};sent.push(JSON.parse(options.body));if(fail)throw Error('Uncertain network result');return {};}};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/summaries.js','utf8'),box);vm.runInContext(fs.readFileSync('web/conversation.js','utf8'),box);
const all=root=>[root,...root.children.flatMap(x=>x instanceof Element?all(x):[])];
async function render(){const root=new Element('root');box.conversationView(root);await Promise.resolve();return all(root);}
(async()=>{
  const activity={boundary:'Recorded, not live',issues:[],phases:[{id:'run-a',phaseId:'phase-a',status:'completed',at:42,checkpoint:'Review before next phase',tasks:[{title:'Feature',repository:'repo',status:'completed',result:'a'.repeat(64),evidence:{summary:'Tests passed <script>',source:'source',tests:'1631 passed',preservation:'retained'},pullRequests:[{url:'https://github.com/example/product/pull/71',state:'open',observedAt:41},{url:'javascript:alert(1)',state:'open'}]}]}]};
  let root=new Element('root');box.conversationActivity(root,activity);
  let activityNodes=all(root);assert(activityNodes.some(n=>n.text==='Open PR #71'));
  assert.equal(activityNodes.filter(n=>n.tag==='a').length,1);
  assert(activityNodes.some(n=>n.text==='Next: review the PR and merge manually when ready.'));
  activityNodes.find(n=>n.text==='Git & delivery · refresh PR status').click();assert.equal(navigation,'gitStatus');
  activity.phases[0].tasks[0].pullRequests[0].state='merged';
  root=new Element('root');box.conversationActivity(root,activity);activityNodes=all(root);
  assert(activityNodes.some(n=>n.text?.includes('merged does not mean deployed')));
  assert(!activityNodes.some(n=>n.text==='Next: review the PR and merge manually when ready.'));
  activity.phases[0].tasks[0].pullRequests[0].state='unknown';
  root=new Element('root');box.conversationActivity(root,activity);
  assert(all(root).some(n=>n.text?.includes('check the PR state')));
  assert.equal(box.brainMessageState({}).label,'Saved · not notified');
  box.state.standard={run:{status:'paused'}};
  assert.equal(box.brainMessageState({}).label,'Held at checkpoint');
  assert.match(box.brainMessageState({}).detail,/recovery-only preparation wake/);
  box.state.standard=null;
  assert.equal(box.brainMessageState({notification:{status:'accepted'}}).label,'Sent to Codex');
  assert.equal(box.brainMessageState({notification:{status:'accepted',nativeDelivery:'owned_turn_start',nativeTurnStatus:'completed'}}).label,'Native turn ended · receipt missing');
  assert.equal(box.brainMessageState({notification:{status:'uncertain'}}).label,'Delivery unconfirmed');
  assert.equal(box.brainMessageState({receivedAt:1}).label,'Received · reply pending');
  for(const nativeTurnStatus of ['completed','failed','interrupted']){
    const delivery=box.brainMessageState({receivedAt:1,notification:{status:'accepted',nativeTurnStatus}});
    assert.equal(delivery.label,'Native turn ended · reply missing');
    assert.match(delivery.detail,/do not send a duplicate/);
  }
  assert.equal(box.brainMessageState({receivedAt:1,notification:{nativeTurnStatus:'native_attention_required'}}).label,'Received · native attention reported');
  assert.equal(box.brainMessageState({receivedAt:1,notification:{nativeTurnStatus:'interrupted'},reply:{message:'Done'}}).label,'Replied','A retained reply remains distinct from native turn completion');
  assert.equal(box.brainMessageState({reply:{message:'Done'}}).label,'Replied');
  let nodes=await render(),input=nodes.find(n=>n.tag==='textarea'),check=nodes.find(n=>n.type==='checkbox'),send=nodes.find(n=>n.type==='submit');
  assert.equal(send.disabled,true);assert.equal(check.checked,false);
  input.value='Keep this alpha draft <script>';input.oninput();check.checked=true;check.onchange();assert.equal(send.disabled,false);
  box.workspaceId='beta';nodes=await render();assert.equal(nodes.find(n=>n.tag==='textarea').value,'');
  box.workspaceId='alpha';nodes=await render();assert.equal(nodes.find(n=>n.tag==='textarea').value,input.value);
  fail=true;await nodes.find(n=>n.tag==='form').onsubmit({preventDefault(){}});
  const first=JSON.stringify(sent[0]);nodes=await render();assert.equal(nodes.find(n=>n.tag==='textarea').disabled,true);
  fail=false;await nodes.find(n=>n.tag==='form').onsubmit({preventDefault(){}});assert.equal(JSON.stringify(sent[1]),first);
  assert.equal(sent[1].payload.brainId,'brain-a');assert.equal(sent[1].kind,'reconcile');
  pending=1;nodes=await render();assert.equal(nodes.find(n=>n.type==='submit').disabled,true);
  messages=[{id:'exact-request',message:'Existing bounded instruction',createdAt:1,receivedAt:2}];
  vm.runInContext("brainRequestFocus.set('alpha','exact-request');brainRequestFocus.set('beta','other-request')",box);
  const beforeFocus=sent.length;nodes=await render();
  const target=nodes.find(n=>n['data-focus']==='saved-request:exact-request');
  assert.equal(target.tabindex,'-1');assert.equal(target.scrolled.block,'nearest');assert.equal(target.focused.preventScroll,true);
  assert.equal(sent.length,beforeFocus,'Inspecting a request never posts or notifies');
  assert.equal(vm.runInContext("brainRequestFocus.has('alpha')",box),false,'The focus request is consumed once');
  assert.equal(vm.runInContext("brainRequestFocus.get('beta')",box),'other-request','Other project focus remains isolated');
  messages=[];
  let nativePending=true;const nativeCalls=[];
  const native={status:'pending',pending:{commandId:'cmd-1',brainId:'brain-a',turnId:'turn-1',itemId:'item-1',requestId:4,
    method:'item/commandExecution/requestApproval',requestHash:'a'.repeat(64),observedAt:1,expiresAt:9999999999,
    canAccept:false,allowedDecisions:['accept','decline','cancel'],request:{command:'do-not-run <script>',cwd:'/fixture'},item:null}};
  box.api=async(path,options)=>{
    if(path==='/api/native-permission')return nativePending?native:{status:'unavailable'};
    if(path==='/api/native-permission/preview'){
      const body=JSON.parse(options.body);nativeCalls.push(['preview',body]);
      return {document:{...native.pending,decision:body.decision,boundary:'Permission only'},signature:'signed'};
    }
    if(path==='/api/native-permission/confirm'){
      nativeCalls.push(['confirm',JSON.parse(options.body)]);nativePending=false;
      return {status:'queued',detail:'One response queued'};
    }
    return {pending:0,total:0,messages:[],hasOlder:false};
  };
  root=new Element('root');box.nativePermissionPanel(root);await Promise.resolve();await Promise.resolve();
  nodes=all(root);assert(nodes.some(n=>n.tag==='pre'&&n.text.includes('do-not-run <script>')));
  assert(!nodes.some(n=>n.text==='Approve this request once'));
  await nodes.find(n=>n.text==='Decline').click();
  nodes=all(root);assert.equal(nativeCalls[0][0],'preview');
  const nativeCheck=nodes.find(n=>n.type==='checkbox'),nativeConfirm=nodes.find(n=>n.text==='Confirm decline');
  assert.equal(nativeConfirm.disabled,true);nativeCheck.checked=true;nativeCheck.onchange();
  await nativeConfirm.click();assert.equal(nativeCalls[1][0],'confirm');
  assert.equal(nativeCalls[1][1].confirmed,true);
  const source=fs.readFileSync('web/conversation.js','utf8');assert(!source.includes('innerHTML'));
  assert(source.includes("navigateView('artifacts',id)"));assert(source.includes("navigateView('decisions',id)"));
  console.log('Conversation UI: project drafts, explicit confirmation, immutable retry, receipt labels and pending guard passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
