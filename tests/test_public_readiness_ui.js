'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag,text=''){Object.assign(this,{tag,text,children:[],dataset:{},isConnected:true});}
  append(...items){this.children.push(...items);}
  addEventListener(){}
}
const calls=[];
const box={workspaceId:'v3',busy:false,connected:true,standardCatalogInFlight:new Set(),
  state:{standard:{contextHash:'current'},brainNotification:{publicReadinessSourceAvailable:true}},
  el:(tag,text)=>new Element(tag,text),button:(text,click)=>Object.assign(new Element('button',text),{click}),
  when:String,requestCatalogForPlay:s=>calls.push(s)};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/journey.js','utf8'),box);
const refresh={id:'failed-original',status:'failed',result:'Native schema unavailable',catalogError:{code:'native_schema_unavailable',retryable:false},
  notification:{preplayCatalog:{version:1},nativeTaskContract:{protocol:'public_app_server_tasks_v1'}}};
box.state.standard.catalogRefresh=refresh;
const all=root=>[root,...root.children.flatMap(all)];
const root=new Element('main');box.catalogReadinessDetails(root,refresh);
const next=all(root).find(e=>e.tag==='button'&&e.text==='Request a new public-host readiness check');
assert.ok(next);assert.equal(calls.length,0,'Rendering only exposes a choice, never sends');
assert.ok(!all(root).some(e=>e.text==='Check again after host repair'),'Do not expose competing legacy retry');
next.click();assert.equal(calls.length,1,'One explicit click uses the existing new-request control');
assert.equal(refresh.status,'failed');assert.equal(refresh.catalogError.retryable,false,'Old error is never reclassified');
box.state.standard.contextHash='changed';next.click();assert.equal(calls.length,1,'Stale source UI cannot submit');
box.state.standard.contextHash='current';box.state.brainNotification.publicReadinessSourceAvailable=false;
next.click();assert.equal(calls.length,1,'Source availability is rechecked');
const old=new Element('main');box.catalogReadinessDetails(old,refresh);
assert.ok(!all(old).some(e=>e.text==='Request a new public-host readiness check'));
box.state.brainNotification.publicReadinessSourceAvailable=true;
box.state.brainNotification.readinessOwnedSourceAvailable=true;
box.assistantRequestStep=key=>calls.push(key);
const owned=new Element('main');box.catalogReadinessDetails(owned,refresh);
assert.ok(!all(owned).some(e=>e.text==='Request a new public-host readiness check'));
const review=all(owned).find(e=>e.tag==='button'&&e.text==='Review readiness-owned startup');
const before=calls.length;assert.ok(review);assert.equal(calls.length,before);
review.click();assert.equal(calls.at(-1),'codex_readiness_start');
console.log('Public readiness UI: explicit distinct source path, retained old error, no automatic request');
