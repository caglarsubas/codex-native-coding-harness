"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag,text=''){this.tag=tag;this.text=text;this.children=[];this.hidden=false;this.value='';}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(name,value){this[name]=value;}
  querySelectorAll(){return [];}
}
const nodes=new Map(),requests=[];let reloads=0,locked=false;
const box={console,URLSearchParams,Number,String,Map,clearInterval(){},setInterval(){return 1;},
  document:{addEventListener(){},activeElement:null,visibilityState:'visible'},
  $:id=>{if(!nodes.has(id))nodes.set(id,new Element('div'));return nodes.get(id);},
  el:(tag,text)=>new Element(tag,text),button:(text,callback)=>Object.assign(new Element('button',text),{click:callback}),
  empty:(a,b)=>new Element('p',a+b),when:String,showNotice(){},workspaceLocked:()=>locked,
  assistantConnectionChanged(){},connected:true,state:{},csrf:'workspace-token',workspaceGeneration:0,
  api:async(path,options)=>{requests.push({path,options});return {csrf:'global-token',remembered:false,rememberDays:0,expiresAt:999};},
  location:{hash:'#/w/harness/conversation',pathname:'/',search:'',reload(){reloads++;}},
  history:{replaceState(){}},initializeWorkspaces:async()=>{},refresh:async()=>{},applyDashboardRoute(){},busy:false,selected:null};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/auth.js','utf8'),box);
const run=code=>vm.runInContext(code,box),all=root=>[root,...root.children.flatMap(x=>x instanceof Element?all(x):[])];
(async()=>{
  await run('start()');
  assert.equal(requests[0].path,'/api/session');assert.equal(requests[0].options.global,true);
  assert.equal(box.location.hash,'#/w/harness/conversation','Bookmark route must survive sign-in');
  let panel=all(nodes.get('browser-access-panel'));
  assert.equal(panel.find(n=>n.tag==='select').value,'30');
  assert.equal(panel.find(n=>n.type==='checkbox').checked,false);
  const revoke=panel.find(n=>n.text==='Sign out all browsers');assert.equal(revoke.disabled,true);
  // Revoke cannot submit through a programmatic click without confirmation.
  revoke.click();assert.equal(requests.length,1);
  const form=panel.find(n=>n.tag==='form');
  form.onsubmit({preventDefault(){}});await new Promise(resolve=>setImmediate(resolve));
  const remember=requests.find(r=>r.path==='/api/session/remember');
  assert.equal(remember.options.global,true);
  assert.equal(remember.options.headers['X-CSRF-Token'],'global-token');
  assert.deepEqual(JSON.parse(remember.options.body),{rememberDays:30});assert.equal(reloads,1);
  locked=true;const before=requests.length;await run("changeBrowserAccess('/api/logout',{})");assert.equal(requests.length,before);
  run('browserSignedOut()');assert.equal(box.state,null);assert.equal(box.connected,false);
  assert.equal(nodes.get('browser-access').hidden,true);assert.equal(nodes.get('pause').disabled,true);
  const source=fs.readFileSync('web/auth.js','utf8');
  for(const forbidden of ['localStorage','sessionStorage','innerHTML'])assert(!source.includes(forbidden));
  console.log('Browser access UI: opt-in, global CSRF, revocation confirmation, bookmark preservation and sign-out passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
