'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const saved=new Map();
const storage={getItem:key=>saved.get(key)||null,setItem:(key,value)=>saved.set(key,String(value)),removeItem:key=>saved.delete(key)};
const box={Map,Set,Date,Number,sessionStorage:storage,titles:{},workspaceId:'alpha',state:null,$:()=>({focus(){}}),activityLabel:()=>'',el:()=>({}),button:()=>({})};
vm.createContext(box);
for(const name of ['session-map.js','conversation.js'])vm.runInContext(fs.readFileSync('web/'+name,'utf8'),box);
const run=code=>vm.runInContext(code,box);

const current=Array.from({length:9},(_,i)=>({id:'current-'+i,group:i%2?'attention':'open'}));
const history=Array.from({length:13},(_,i)=>({id:'history-'+i,group:'history'}));
let page=box.sessionPageTasks([...current,...history],0);
assert.equal(page.visible.length,13,'Every current/attention task remains visible on the graph');
assert.equal(page.visible.filter(node=>node.group==='history').length,4,'Only history is paginated');
page=box.sessionPageTasks([...current,...history],2);
assert.equal(page.visible.length,13);assert.equal(page.visible.at(-1).id,'history-11');
page=box.sessionPageTasks([...current,...history],99);
assert.equal(page.page,3,'History pagination is bounded');assert.equal(page.visible.length,10);

run("sessionSelectRoute('roadmap')");
assert.equal(run("sessionMapPreferences.get('alpha').selected"),'brain');
assert.equal(run("sessionMapPreferences.get('alpha').section"),'roadmap');
assert.equal(run("sessionMapPreferences.get('alpha').tab"),'section');
run("sessionSelectRoute('conversation')");
assert.equal(run("sessionMapPreferences.get('alpha').tab"),'conversation');
assert.equal(run("sessionMapPreferences.get('alpha').selected"),'brain');
run("sessionSelectRoute('overview')");
assert.equal(run("sessionMapPreferences.get('alpha').inspectorOpen"),false,'The graph-only route dismisses the narrow sheet');
run("sessionMapPreferences.get('alpha').focus='brain-message';sessionMapPreferences.get('alpha').inspectorOpen=true;sessionSavePreferences('alpha',sessionMapPreferences.get('alpha'))");
const restored=box.sessionPreferences('alpha');
assert.equal(restored.selected,'brain');assert.equal(restored.tab,'conversation','Selection survives a page reload');
assert.equal(restored.focus,'brain-message','The project brain composer can regain focus after a reload');
assert.equal(restored.inspectorOpen,true,'A selected mobile sheet stays open after reload');
run("sessionMapPreferences.delete('alpha');sessionSelectRoute('overview')");
assert.equal(run("sessionMapPreferences.get('alpha').inspectorOpen"),true,'Initial URL replay does not close the restored sheet');
run("sessionShowGuide()");
assert.equal(run("sessionMapPreferences.get('alpha').tab"),'guide','Advice remains a visibly separate inspector section');

assert.equal(box.sessionCreationDelivery({clientThreadId:'pending-1'}),'Client ID pending · do not retry');
assert.equal(box.sessionCreationDelivery({threadId:'confirmed-1'}),'Confirmed native task ID');
assert.equal(box.sessionCreationDelivery({issuedAt:1}),'Creation issued · outcome unconfirmed');
assert.equal(box.sessionCreationDelivery({}),'No creation delivery recorded');

box.saveBrainDraft('alpha',{text:'Do not start Play.',confirmed:false,request:null});
assert.equal(box.loadBrainDraft('alpha').text,'Do not start Play.');
box.saveBrainDraft('beta',{text:'Other project',confirmed:false,request:null});
assert.equal(box.loadBrainDraft('alpha').text,'Do not start Play.','Drafts remain project-scoped');
box.clearBrainDraft('alpha');assert.equal(box.loadBrainDraft('alpha').text,'');

const html=fs.readFileSync('web/index.html','utf8'),css=fs.readFileSync('web/one-page.css','utf8');
assert.match(html,/id="navigation-pane"[^>]*hidden/,'Legacy route controls are not a persistent rail');
assert.match(html,/id="assistant-pane"[^>]*hidden/,'Advisory chat is not a competing side pane');
assert.match(html,/id="brand-graph"/,'Brand keeps the owner in the current project');
assert.match(css,/@media \(max-width:799px\)/,'Inspector has narrow-sheet layout');
assert.match(css,/\.session-canvas\[data-layout=list\]/,'Searchable list can reflow without diagram scrolling');
assert.match(fs.readFileSync('web/session-map.js','utf8'),/aria-modal/,'Mobile sheet exposes dialog semantics');
console.log('One-page workspace: graph inventory, history pagination, contextual routes, separate advice, scoped drafts, delivery facts and narrow layout passed');
