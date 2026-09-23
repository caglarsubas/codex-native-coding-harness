'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const links=[];
const box={titles:{},Map,Date,Set,Number,activityLabel:a=>a.status==='running'?'Active recently':'Idle observed',
  el:(tag,text)=>({tag,text}),button:(text,action)=>({text,action})};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/session-map.js','utf8'),box);
const now=10_000;
const snapshot={meta:{brainId:'brain-task',paused:true},brainActivity:{title:'The project brain',fresh:true,status:'running',observedAt:now-1},
  standard:{run:{tasks:[
    {id:'active',threadId:'native-active',title:'Build <script>alert(1)</script>',repository:'web',status:'active',nativeStatus:'active',observedAt:now-1},
    {id:'pending',clientThreadId:'pending-client',title:'Pending creation',status:'pending',nativeStatus:'active',observedAt:now-1},
    {id:'done',threadId:'native-done',title:'Finished work',status:'completed',nativeStatus:'active',observedAt:now-1},
    {id:'absent',title:'Confirmed non-creation',status:'not_created'},
    {id:'failed',threadId:'native-failed',title:'Failed task',status:'failed'}]}},
  workers:[{id:'same-native',threadId:'native-active',status:'running'},
    {id:'old',threadId:'native-old',status:'running',nativeStatus:'active',observedAt:now-121},
    {id:'legacy',threadId:'native-legacy',status:'running'},
    {id:'archived',threadId:'native-archived',status:'complete',archived:true}]};
const frozen=JSON.stringify(snapshot),model=box.sessionGraphModel(snapshot,now);
assert.equal(JSON.stringify(snapshot),frozen,'Projection must not mutate retained observations');
assert.equal(model.tasks.length,8,'Same confirmed native task is displayed once');
assert.equal(model.brain.moving,true);
assert.equal(model.tasks[0].title,'Build <script>alert(1)</script>','Text stays literal');
assert.equal(model.tasks.find(n=>n.id==='standard:pending').moving,false,'Pending client identity never becomes an active task');
assert.equal(model.tasks.find(n=>n.id==='standard:pending').group,'attention');
assert.equal(model.tasks.find(n=>n.id==='standard:done').moving,false,'A terminal record must not animate an old active observation');
assert.equal(model.tasks.find(n=>n.id==='standard:done').label,'Completed · recorded','Complete is not archived');
assert.equal(model.tasks.find(n=>n.id==='standard:absent').label,'Not created');
assert.equal(model.tasks.find(n=>n.id==='worker:archived').label,'Archived · recorded');
assert.equal(model.tasks.find(n=>n.id==='worker:old').label,'Activity stale');
assert.equal(model.tasks.find(n=>n.id==='worker:legacy').moving,false,'Legacy running status is not fresh native activity');
assert.equal(box.sessionGraphModel(snapshot,now+121).brain.moving,false,'Freshness expires without refreshing evidence timestamps');
assert.equal(box.sessionGraphModel({...snapshot,brainActivity:{...snapshot.brainActivity,observedAt:now+10}},now).brain.moving,false,'Future-dated evidence is not fresh');
assert.equal(box.sessionGraphModel({...snapshot,brainActivity:{...snapshot.brainActivity,fresh:false}},now).brain.moving,false);
assert.equal(box.sessionTaskState({status:'active',threadId:'n',nativeStatus:'idle',observedAt:now-1},now).label,'Idle · observed');
assert.equal(box.sessionTaskState({status:'active',threadId:'n',nativeStatus:'completed',observedAt:now-1},now).group,'attention','Finished native turn still needs review');
const active=box.sessionVisibleTasks(model,{filter:'open',query:'WEB'});
assert.equal(active.length,1);assert.equal(active[0].threadId,'native-active');
assert.equal(box.sessionVisibleTasks(model,{filter:'attention',query:'pending-client'}).length,0,'Pending identity is not a native task search match');
assert.equal(box.sessionVisibleTasks(model,{filter:'all',query:'no match'}).length,0);
assert.equal(box.sessionGraphModel({meta:{},workers:[]},now).tasks.length,0,'No invented demo nodes in an empty project');
const root={append:value=>links.push(value)};
for(const id of ['javascript:alert(1)','a/b','<img>',null,''])box.sessionNativeLink(root,id);
assert.equal(links.length,0);
box.sessionNativeLink(root,'native-task');assert.equal(links[0].href,'codex://threads/native-task');
const source=fs.readFileSync('web/session-map.js','utf8');
assert(!source.includes('innerHTML'));
assert(!source.includes("api("),'Map must not introduce scans, collection, commands or transcript APIs');
assert(!source.includes('localStorage'),'Task selection remains transient');
console.log('Session map: fresh/stale states, pending IDs, terminal/archive separation, scope, deduplication, empty/filter states and safe links passed');
