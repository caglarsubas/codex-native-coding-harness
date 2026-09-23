const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Node{
  constructor(tag,text=''){this.tag=tag;this.text=text;this.children=[];this.events={};this.isConnected=true;}
  append(...children){this.children.push(...children);}
  setAttribute(){}
  addEventListener(name,fn){this.events[name]=fn;}
  scrollIntoView(){}
  focus(){}
  querySelector(tag){return this.children.find(c=>c.tag===tag);}
}
let navigation=null;
const notices=[],prepared=[];const drafts=new Map();
const box={titles:{},workspaceId:'alpha',workspaceGeneration:1,setInterval(){},el:(tag,text)=>new Node(tag,text),
  section:(title,subtitle)=>new Node('h2',title+' '+(subtitle||'')),when:String,
  table:(headers,rows)=>Object.assign(new Node('table'),{headers,rows}),textCell:(a,b)=>a+' '+b,
  button:(label,click)=>Object.assign(new Node('button',label),{click}),empty:(a,b)=>new Node('p',a+' '+b),
  navigateView:(view,id)=>navigation={view,id},showNotice:(message)=>notices.push(message),missionDrafts:drafts,
  openMissionEditor:(source)=>{prepared.push(source);drafts.set(box.workspaceId,{source});return true;},
  state:{meta:{paused:true},workspace:{id:'alpha',projectProfile:{version:0,profile:null}},repositories:[{id:'fixture',policyProfile:'standard'}],standard:{available:false,blocker:'Review an exact mission first',catalog:null,run:null},mission:{effectiveStatus:'not_configured'},observations:{artifacts:[]}}};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/observations.js','utf8'),box);
const run=code=>vm.runInContext(code,box),nodes=root=>[root,...root.children.flatMap(nodes)],text=root=>nodes(root).map(n=>n.text).join('\n');
const plan={repository:'fixture',path:'docs/plan.md',title:'Main plan',status:'observed',at:1,commit:'a'.repeat(40),documentId:'b'.repeat(64),documentVersion:2,items:[],
  content:{highlights:[{heading:'Current gate',line:3,text:'W01 ONGOING_DESIGN. G04 OPEN. <script>inert</script>'}],tables:[{headers:['Phase','Status'],rows:[['Alpha2','OLD_DONE']],heading:'Old gate',line:10,scope:'historical'}],historyStart:9,issues:[],omittedTables:0,omittedHighlights:0}};
box.plan=plan;box.root=new Node('main');run('roadmapDocument(root,plan)');
assert.match(text(box.root),/Checklist completion not available/);assert(!text(box.root).includes('0 / 0'));
assert.match(text(box.root),/W01 ONGOING_DESIGN/);
const historical=nodes(box.root).find(n=>n.tag==='details'&&n.children[0]?.text==='Historical checkpoints · not current status');
assert(historical);assert.equal(historical.open,undefined);assert.equal(historical.children[2].text,'Old gate · line 10');
nodes(box.root).find(n=>n.text==='Read source · v2').click();assert.deepEqual(navigation,{view:'artifacts',id:plan.documentId});
box.root=new Node('main');box.plan={...plan,items:[{checked:true,line:11,label:'old',scope:'historical'}]};run('roadmapDocument(root,plan)');
assert.match(box.root.children[0].children[2].text,/Checklist completion not available/);
box.root=new Node('main');run('roadmapDocument(root,plan,true)');assert.match(text(box.root),/Private proposal · not published/);
assert(!nodes(box.root).some(n=>n.text==='Current sections — as recorded in this source'));
box.root=new Node('main');box.plan={...plan,content:null,statusTable:{headers:['Status'],rows:[['OLD']]}};run('roadmapDocument(root,plan)');assert.match(text(box.root),/currency unknown/);
run('observationFilters=()=>{};inRepo=()=>true');box.root=new Node('main');box.state.observations.roadmaps={plans:[plan],drafts:[]};run('roadmap(root)');
assert.match(text(box.root),/1 \/ 1 configured sources readable/);assert.match(text(box.root),/does not mean no drafts exist/);
assert.match(text(box.root),/Review & Play/);assert.match(text(box.root),/Reviewing a mission does not start work/);assert.match(text(box.root),/Review an exact mission first/);
nodes(box.root).find(n=>n.text==='Review mission & prerequisites').click();assert.deepEqual(navigation,{view:'mission',id:undefined});
assert(!nodes(box.root).some(n=>n.text==='Open Review Play'));
box.state.standard.available=true;box.root=new Node('main');run('roadmap(root)');
nodes(box.root).find(n=>n.text==='Open Review Play').click();assert.deepEqual(navigation,{view:'operations',id:undefined});
box.state.standard.run={status:'paused'};box.root=new Node('main');run('roadmap(root)');
assert.match(text(box.root),/A cooperative phase is already recorded/);
nodes(box.root).find(n=>n.text==='Open current phase').click();assert.deepEqual(navigation,{view:'operations',id:undefined});
box.state.standard.run=null;box.state.standard.available=false;
for(const repositories of [[{policyProfile:'harness'}],[{policyProfile:'standard'},{policyProfile:'harness'}],[],undefined]){
  box.state.repositories=repositories;box.root=new Node('main');run('roadmap(root)');
  assert.match(text(box.root),/Unavailable for this project/);assert.match(text(box.root),/cannot opt a Harness/);
  assert(!nodes(box.root).some(n=>n.text==='Review mission & prerequisites'||n.text==='Open Review Play'));
}
box.state.workspace=null;box.root=new Node('main');run('roadmap(root)');assert(!text(box.root).includes('Review & Play'));
box.state.workspace={id:'alpha'};
box.state.repositories=[{id:'fixture',policyProfile:'standard'}];
const actionable={...plan,status:'observed',documentId:'b'.repeat(64),documentVersion:3,at:12,
  items:[{line:4,label:'Build a bounded fixture',checked:false,scope:'current'},{line:5,label:'Historical work',checked:false,scope:'historical'},{line:6,label:'Already done',checked:true,scope:'current'}],
  content:{classificationComplete:true,highlights:[{heading:'Current recommendation',line:3,text:'Review this',truncated:false}],tables:[],issues:[],omittedTables:0,omittedHighlights:0}};
box.state.observations.roadmaps={plans:[actionable],drafts:[]};box.root=new Node('main');box.plan=actionable;run('roadmapDocument(root,plan)');
const prepare=nodes(box.root).filter(n=>n.tag==='button'&&n.text.startsWith('Prepare draft'));
assert.equal(prepare.length,2,'Only current open checklist and current excerpt are offered');
prepare[0].click();assert.equal(prepared.length,1);assert.equal(prepared[0].repository,'fixture');
assert.equal(prepared[0].path,'docs/plan.md');assert.equal(prepared[0].line,4);assert.equal(prepared[0].documentId,actionable.documentId);
assert.deepEqual(navigation,{view:'mission',id:undefined});
prepare[1].click();assert.equal(prepared.length,1,'An unsaved draft cannot be overwritten');
drafts.clear();box.state.observations.roadmaps.plans=[{...actionable,documentId:'c'.repeat(64)}];
prepare[0].click();assert.equal(prepared.length,1,'A changed source version makes the old action stale');
assert.match(notices.at(-1),/source or project changed/);
box.state.observations.roadmaps.plans=[actionable];box.workspaceId='beta';prepare[0].click();
assert.equal(prepared.length,1,'An action from another workspace cannot prepare a draft');
box.workspaceId='alpha';box.workspaceGeneration=2;prepare[0].click();assert.equal(prepared.length,1,'An old workspace generation cannot prepare a draft');
box.workspaceGeneration=1;box.state.mission=null;prepare[0].click();assert.equal(prepared.length,1,'Unavailable Mission state fails closed');
box.state.mission={effectiveStatus:'not_configured'};box.state.repositories=[];prepare[0].click();assert.equal(prepared.length,1,'Unregistered source repository fails closed');
box.state.repositories=[{id:'fixture',policyProfile:'standard'}];box.plan={...actionable,content:{...actionable.content,classificationComplete:false}};
box.root=new Node('main');run('roadmapDocument(root,plan)');assert(!nodes(box.root).some(n=>n.tag==='button'&&n.text.startsWith('Prepare draft')));
box.plan={...actionable,sourceKind:'proposal'};box.root=new Node('main');run('roadmapDocument(root,plan,true)');
assert(!nodes(box.root).some(n=>n.tag==='button'&&n.text.startsWith('Prepare draft')),'Private proposals do not become handoff actions');
box.plan={...actionable,items:Array.from({length:30},(_,i)=>({line:i+1,label:'Action '+i,checked:false,scope:'current'}))};
assert.equal(run('roadmapMissionActions(plan).length'),20,'Handoff actions are bounded per source');
assert(!fs.readFileSync('web/observations.js','utf8').includes('innerHTML'));
console.log('Roadmap UI: current bounded actions, source/workspace staleness, draft preservation, Review & Play gates and literal sources passed');
