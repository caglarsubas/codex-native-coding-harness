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
const box={titles:{},workspaceId:'alpha',setInterval(){},el:(tag,text)=>new Node(tag,text),
  section:(title,subtitle)=>new Node('h2',title+' '+(subtitle||'')),when:String,
  table:(headers,rows)=>Object.assign(new Node('table'),{headers,rows}),textCell:(a,b)=>a+' '+b,
  button:(label,click)=>Object.assign(new Node('button',label),{click}),empty:(a,b)=>new Node('p',a+' '+b),
  navigateView:(view,id)=>navigation={view,id},state:{observations:{artifacts:[]}}};
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
assert(!fs.readFileSync('web/observations.js','utf8').includes('innerHTML'));
console.log('Roadmap UI: honest empty counts, literal current excerpts, collapsed history, proposals, versions, legacy snapshots and source links passed');
