"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag,text=''){this.tag=tag;this.text=text;this.children=[];this.disabled=false;this.isConnected=true;}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(name,value){this[name]=value;}
}
let fail=false,pending=0;const sent=[];
const box={Map,titles:{},workspaceId:'alpha',busy:false,connected:true,csrf:'fixture',crypto:{randomUUID:()=>String(sent.length)},
  state:{meta:{brainId:'brain-a',revision:1},workspace:{name:'Alpha'},repositories:[]},
  el:(tag,text)=>new Element(tag,text),button:(text,callback)=>Object.assign(new Element('button',text),{click:callback}),
  section:text=>new Element('h2',text),empty:(a,b)=>new Element('p',a+b),callout:(a,b)=>new Element('p',a+b),badge:text=>new Element('span',text),when:String,
  render(){},navigateView(){},refresh:async()=>{assert.equal(box.busy,false);},showNotice(){},updateWorkspaceSelector(){},
  api:async(path,options)=>{if(!options)return {pending,total:0,messages:[],hasOlder:false};sent.push(JSON.parse(options.body));if(fail)throw Error('Uncertain network result');return {};}};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/conversation.js','utf8'),box);
const all=root=>[root,...root.children.flatMap(x=>x instanceof Element?all(x):[])];
async function render(){const root=new Element('root');box.conversationView(root);await Promise.resolve();return all(root);}
(async()=>{
  assert.equal(box.brainMessageState({}).label,'Saved · not notified');
  assert.equal(box.brainMessageState({notification:{status:'accepted'}}).label,'Sent to Codex');
  assert.equal(box.brainMessageState({notification:{status:'uncertain'}}).label,'Delivery unconfirmed');
  assert.equal(box.brainMessageState({receivedAt:1}).label,'Received · reply pending');
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
  const source=fs.readFileSync('web/conversation.js','utf8');assert(!source.includes('innerHTML'));
  assert(source.includes("navigateView('artifacts',id)"));assert(source.includes("navigateView('decisions',id)"));
  console.log('Conversation UI: workspace drafts, explicit confirmation, immutable retry, receipt labels and pending guard passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
