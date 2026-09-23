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

// Delivery associations are scoped and exact; unknown evidence is never success.
const sha='a'.repeat(40),other='b'.repeat(40),stamp=Date.now()/1000;
const data={meta:{},standard:{run:{phaseId:'WSP-PHASE-07',tasks:[{id:'standard',repository:'ui',finishedAt:stamp-30,status:'completed'}]}},
  workers:[
    {id:'open',packetId:'WSP-UI-01',title:'Open work',repository:'ui',commit:sha,branch:'codex/ui',pr:'https://github.com/example/ui/pull/1',createdAt:stamp-500,updatedAt:stamp-60,evidence:{ci:{status:'verified',reference:'retained-proof'}}},
    {id:'old',packetId:'WSP-UI-02',repository:'ui',commit:other,pr:'https://github.com/example/ui/pull/2',completedAt:stamp-40*86400,evidence:{ci:{status:'failed',reference:'failure-proof'}}},
    {id:'unknown',repository:'elsewhere',commit:sha,createdAt:stamp+100,evidence:{ci:{status:'verified',reference:null}}}],
  observations:{git:[{repository:'ui',status:'measured',remoteStatus:'observed',at:stamp-5,remoteAt:stamp-90,
    branches:[{branch:'codex/ui',commit:sha,remoteCommit:sha}],pullRequests:[
      {number:1,url:'https://github.com/example/ui/pull/1',state:'open',draft:true,head:sha},
      {number:2,url:'https://github.com/example/ui/pull/2',state:'merged',head:other}]}]}};
const before=JSON.stringify(data),projection=box.sessionGraphModel(data,stamp),open=projection.tasks.find(t=>t.raw.id==='open').delivery;
assert.equal(open.prStatus,'draft');assert.equal(open.commitStatus,'matches_remote');assert.equal(open.ciStatus,'verified');
assert.equal(open.roadmapId,'WSP-UI-01');assert.equal(open.lastActivity,stamp-60);
assert.equal(projection.tasks[0].delivery.roadmapId,'WSP-PHASE-07');
assert.equal(projection.tasks[0].delivery.lastActivity,stamp-30,'Cooperative finishedAt is activity');
const unknown=projection.tasks.find(t=>t.raw.id==='unknown').delivery;
assert.equal(unknown.prStatus,'unknown','A same-SHA observation in another repository cannot attach');
assert.equal(unknown.ciStatus,'unverified','Verified without reference is not proof');
assert.equal(unknown.lastActivity,null,'Future activity is not current activity');
const filtered=facets=>box.sessionVisibleTasks(projection,{filter:'all',query:'',facets},stamp).map(n=>n.raw.id).join(',');
assert.equal(filtered({repository:'repo:ui',pr:'draft',ci:'verified',roadmap:'scope:WSP-UI-01',activity:'24h'}),'open');
assert.equal(filtered({pr:'draft',ci:'failed'}),'','Filters intersect');
assert.equal(filtered({commit:'recorded'}),'open,old,unknown','Recorded includes remotely observed commits');
assert.equal(filtered({commit:'unknown'}),'standard');
assert.equal(filtered({pr:'merged',activity:'older'}),'old');
assert.equal(filtered({roadmap:'unknown',activity:'unknown'}),'unknown');
assert.equal(filtered({sort:'newest'}),'standard,open,old,unknown','Unknown dates stay last');
assert.equal(filtered({sort:'oldest'}),'old,open,standard,unknown');
assert.equal(box.sessionVisibleTasks(projection,{filter:'all',query:'WSP-UI-02'},stamp)[0].raw.id,'old');
assert.equal(box.sessionVisibleTasks(projection,{filter:'all',query:'#1'},stamp)[0].raw.id,'open');
assert.equal(JSON.stringify(data),before,'Filtering never mutates records or evidence clocks');
const remote=data.observations.git[0];
const changed={...data,observations:{git:[{...remote,branches:[{branch:'codex/ui',commit:sha,remoteCommit:other}]}]}};
assert.equal(box.sessionGraphModel(changed,stamp).tasks.find(t=>t.raw.id==='open').delivery.commitStatus,'differs_remote');
const unavailable={...data,observations:{git:[{...remote,remoteStatus:'unavailable',previousRemote:remote}]}};
assert.equal(box.sessionGraphModel(unavailable,stamp).tasks.find(t=>t.raw.id==='open').delivery.prStatus,'linked','Failed refresh does not reuse a prior success');
const retained={...data,observations:{git:[{...remote,remoteStatus:'not_requested',remoteAt:null,previousRemote:remote}]}};
assert.equal(box.sessionGraphModel(retained,stamp).tasks.find(t=>t.raw.id==='open').delivery.remoteAt,stamp-90,'Retained timestamp stays historical');
const ambiguous={...data,workers:[{id:'multi',repository:'ui',commit:sha}],observations:{git:[{...remote,pullRequests:[{state:'open',head:sha},{state:'merged',head:sha}]}]}};
assert.equal(box.sessionGraphModel(ambiguous,stamp).tasks.at(-1).delivery.prStatus,'unknown','Multiple matching PRs are not guessed');
assert.equal(box.sessionDelivery({repository:'ui',status:'complete',evidence:{merge:{status:'verified'}}},data,'worker',stamp).prStatus,'unknown','Completion or merge evidence is not a measured PR state');
assert.equal(box.sessionDelivery({repository:'ui'},data,'worker',stamp).commit,null,'Do not inherit a repository default commit');
assert.equal(box.sessionDelivery({evidence:{tests:{status:'verified'}}},data,'worker',stamp).ciStatus,'unverified','Local tests do not imply CI');
assert.equal(box.sessionDelivery({evidence:{ci:{status:'not_applicable'}}},data,'worker',stamp).ciStatus,'not_applicable');
const begin=box.sessionDateBoundary('2026-09-23'),end=box.sessionDateBoundary('2026-09-23',true);
assert.equal(box.sessionDateBoundary('2026-02-30'),null);
const dates={tasks:[begin-1,begin,end-1,end].map((at,i)=>({raw:{id:String(i)},group:'open',title:'Task',delivery:{lastActivity:at}}))};
assert.equal(box.sessionVisibleTasks(dates,{facets:{activity:'custom',from:'2026-09-23',through:'2026-09-23'}},end+1).map(n=>n.raw.id).join(','),'1,2','Date range includes the whole local Through day');
assert.equal(box.sessionVisibleTasks(dates,{facets:{activity:'custom',from:'2026-09-24',through:'2026-09-22'}},end+1).length,0,'Reversed range shows no misleading matches');
assert.equal(box.sessionZoomValue(9,1000,620),2);assert.equal(box.sessionZoomValue(-1,1000,620),.25);
assert.equal(box.sessionZoomValue('fit',320,620),320/820,'Narrow map fits its logical canvas');
assert.equal(box.sessionZoomValue('fit',1100,620),520/620,'Fit includes the graph height');
assert.equal(box.sessionZoomValue('fit',1100,360),1);
console.log('Session map controls: combined filters, exact repository/PR matches, missing and failed evidence, local date boundaries, stable ordering and bounded zoom passed');

// Event behavior: graph gestures cannot hijack plain scrolling or node keys.
class ViewNode {
  constructor(tag,text){this.tag=tag;this.textContent=text;this.children=[];this.dataset={};this.style={};this.attrs={};this.events={};this.classList={add(){},remove(){}};this.isConnected=true;this.scrollLeft=0;this.scrollTop=0;this.clientWidth=400;this.clientHeight=280;}
  append(...nodes){this.children.push(...nodes);}
  setAttribute(key,value){this.attrs[key]=value;}
  addEventListener(key,fn){this.events[key]=fn;}
  scrollTo(value){this.scrollLeft=Math.max(0,value.left);this.scrollTop=Math.max(0,value.top);}
  getBoundingClientRect(){return {left:0,top:0};}
  focus(){}
  setPointerCapture(id){this.captured=id;}
}
box.el=(tag,text)=>new ViewNode(tag,text);
box.button=(text,click)=>Object.assign(new ViewNode('button',text),{click});
box.ResizeObserver=class{constructor(callback){this.callback=callback;}observe(){}disconnect(){this.disconnected=true;}};
const viewRoot=new ViewNode('section'),wrap=new ViewNode('div'),canvas=new ViewNode('div'),prefs={zoom:'fit'};
box.sessionViewport(viewRoot,wrap,canvas,prefs,620);
const all=node=>[node,...node.children.flatMap(all)];
const control=name=>all(viewRoot).find(node=>node.attrs['aria-label']===name);
control('Zoom in').click();assert(prefs.zoom>400/820);control('Reset zoom to 100%').click();assert.equal(prefs.zoom,1);
let prevented=false;
wrap.events.wheel({ctrlKey:false,metaKey:false,deltaY:-100,preventDefault(){prevented=true;}});
assert.equal(prevented,false);assert.equal(prefs.zoom,1,'Plain scrolling does not zoom');
wrap.events.wheel({ctrlKey:true,deltaY:-100,clientX:100,clientY:100,preventDefault(){prevented=true;}});
assert.equal(prevented,true);assert(prefs.zoom>1);assert(wrap.scrollLeft>0,'Pointer anchor is retained on zoom');
wrap.events.keydown({target:canvas,key:'0'});assert(prefs.zoom>1,'Node keys do not trigger viewport shortcuts');
wrap.events.keydown({target:wrap,key:'0',preventDefault(){}});assert.equal(prefs.zoom,1);
control('Fit map').click();assert.equal(prefs.zoom,'fit');assert.equal(wrap.scrollLeft,0);assert.equal(wrap.scrollTop,0);
control('Reset zoom to 100%').click();wrap.scrollLeft=100;wrap.scrollTop=100;
const pointer={button:0,pointerType:'mouse',pointerId:1,clientX:50,clientY:50,target:{closest:()=>null},preventDefault(){}};
wrap.events.pointerdown(pointer);wrap.events.pointermove({pointerId:1,clientX:80,clientY:80});
assert.equal(wrap.scrollLeft,70);assert.equal(wrap.scrollTop,70);wrap.events.pointerup();
wrap.events.pointerdown({...pointer,target:{closest:()=>true}});wrap.events.pointermove({pointerId:1,clientX:100,clientY:100});
assert.equal(wrap.scrollLeft,70,'Dragging task nodes cannot pan the canvas');
wrap.isConnected=false;prefs.resizeObserver.callback();assert(prefs.resizeObserver.disconnected);
console.log('Session map gestures: zoom controls, pointer anchoring, plain-scroll preservation, keyboard scope, drag pan and observer cleanup passed');
