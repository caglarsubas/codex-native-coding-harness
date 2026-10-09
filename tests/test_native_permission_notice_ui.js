'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag,text){this.tag=tag;this.text=text;this.children=[];this.isConnected=true;}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(key,value){this[key]=value;}
}
const all=root=>[root,...root.children.flatMap(child=>child instanceof Element?all(child):[])];
let response={status:'pending',pending:{commandId:'control-a',requestHash:'a'.repeat(64),
  request:{command:'PRIVATE exact command'},item:{type:'PRIVATE item'}}},navigation=null,resolve;
const calls=[],timers=[];
const box={Map,Date,titles:{},workspaceId:'alpha',workspaceGeneration:1,
  el:(tag,text)=>new Element(tag,text),button:(text,click)=>Object.assign(new Element('button',text),{click}),
  navigateView:view=>{navigation=view;},window:{setTimeout:fn=>timers.push(fn)},
  api:async(path,options)=>{calls.push([path,options]);return response;}};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/conversation.js','utf8'),box);
const tick=async()=>{await Promise.resolve();await Promise.resolve();await Promise.resolve();};
(async()=>{
  const notice=new Element('section'),mirror=new Element('section');
  notice.parentElement={querySelector:selector=>selector==='.session-inspector-permission'?mirror:null};
  box.nativePermissionNotice(notice);await tick();
  assert.equal(notice.hidden,false);assert.equal(mirror.hidden,false);
  assert.equal(notice['aria-live'],'polite');
  assert(all(notice).some(n=>n.text==='The brain needs a permission decision'));
  assert(!JSON.stringify(notice._permissionSummary).includes('PRIVATE'),'The shell retains no raw prompt');
  assert(!all(notice).some(n=>n.tag==='pre'||n.tag==='input'),'The notice is not an approval control');
  all(notice).find(n=>n.text==='Review native permission').click();
  assert.equal(navigation,'conversation','Any section opens the same brain inspector');
  assert.equal(calls.length,1,'Navigation never creates or confirms a preview');
  response={status:'response_claimed',commandId:'control-a',delivery:'uncertain',detail:'Do not retry.'};
  await timers.shift()();await tick();
  assert(all(notice).some(n=>n.text==='This native request needs attention'));
  assert(all(mirror).some(n=>n.text==='Do not retry.'));
  response={status:'unavailable'};await timers.shift()();await tick();
  assert.equal(notice.hidden,true);assert.equal(mirror.hidden,true);
  assert(calls.every(([path,options])=>path==='/api/native-permission'&&!options),'Polling is GET-only');
  box.api=()=>new Promise(r=>{resolve=r;});
  const old=new Element('section');box.nativePermissionNotice(old);
  box.workspaceId='beta';box.workspaceGeneration++;
  resolve({status:'pending',pending:{commandId:'old-project',requestHash:'old'}});await tick();
  assert.equal(old.hidden,true,'Late responses never expose another project request');
  const count=timers.length;old.isConnected=false;await tick();
  assert.equal(timers.length,count,'Detached or superseded notices stop polling');
  const css=fs.readFileSync('web/one-page.css','utf8'),map=fs.readFileSync('web/session-map.js','utf8');
  assert(css.includes('.session-home:has(.session-inspector.is-open)>.session-native-notice{display:none}'));
  assert(css.includes('.session-inspector-permission:not([hidden]){display:flex'),'Mobile notice is inside the modal focus boundary');
  assert(map.includes('nativePermissionNotice(permissionNotice)'),'The notice is mounted on the persistent shell, not one tab');
  console.log('Native permission notice: read-only polling, cross-section visibility, mobile modal mirror, no raw prompt and project isolation passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
