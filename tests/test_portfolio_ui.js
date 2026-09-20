const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Node {
  constructor(tag,text){this.tag=tag;this.text=text;this.children=[];this.dataset={};this.events={};}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  addEventListener(event,fn){this.events[event]=fn;}
}
let navigation;
const box={titles:{},Map,el:(tag,text)=>new Node(tag,text),num:v=>v===null?'—':String(v),
  textCell:(a,b)=>[a,b],button:(label,fn)=>Object.assign(new Node('button',label),{click:fn}),
  table:(headers,rows)=>Object.assign(new Node('table'),{headers,rows}),
  callout:(a,b)=>new Node('aside',a+' '+b)};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/workspaces.js','utf8'),box);
vm.runInContext('switchWorkspace=(id,route)=>recordNavigation(id,route)',box);
box.recordNavigation=(id,route)=>{navigation={id,route};};
const run=code=>vm.runInContext(code,box);
assert.equal(run("codeCountingLabel({status:'alias'})"),'Alias · counted elsewhere');
assert.match(run("codeCountingLabel({status:'excluded',issues:['repository_configuration_changed']})"),/settings changed/);
assert.match(run("codeCountingLabel({status:'excluded',issues:['identity_refresh_required']})"),/refresh identity/);
const root=new Node('main');box.root=root;
box.data=Array.from({length:85},(_,i)=>({commit:String(i).padStart(40,'a'),identityBasis:'conventional_origin',
  aliases:[{workspaceId:'alpha',repository:'<script>repo</script>'},{workspaceId:'beta',repository:'clone'}],lines:3,status:'counted'}));
run('codeSnapshotTable(root,data)');
let block=root.children[0];assert.equal(block.children[0].rows.length,40);
let aliases=block.children[0].rows[0][1];assert.equal(aliases.children.length,1);
aliases.open=true;aliases.events.toggle();assert.equal(aliases.children.length,2);
aliases.events.toggle();assert.equal(aliases.children.length,2); // lazy content only once
aliases.children[1].children[1].children[0].click();
assert.equal(navigation.id,'beta');assert.equal(navigation.route.view,'metrics');
assert.equal(aliases.children[1].children[0].children[0].text,'alpha / <script>repo</script>');
block.children[1].children[2].click();assert.equal(block.children[0].rows.length,40);
assert.equal(run('codeSnapshotPage'),1);
const rerender=new Node('main');box.rerender=rerender;run('codeSnapshotTable(rerender,data)');
assert.equal(run('codeSnapshotPage'),1); // polling preserves the snapshot page
block=rerender.children[0];block.children[1].children[2].click();
assert.equal(block.children[0].rows.length,5);assert.equal(block.children[1].children[2].disabled,true);
run('codeSnapshotTable(rerender,[])');assert.equal(run('codeSnapshotPage'),0); // shrink safely
const coverageRoot=new Node('main');box.coverageRoot=coverageRoot;
run('codeCountingCoverage(coverageRoot,{configuredRows:4,duplicateAliases:1,excludedRows:2,localOnlySnapshots:1})');
assert.match(coverageRoot.children[1].text,/Missing values are not zero/);
assert.match(coverageRoot.children[2].text,/cannot be matched automatically/);
const detail=new Node('details');box.detail=detail;
run("rememberCodeDetails(detail,'fixture-exclusions')");detail.open=true;detail.events.toggle();
const restored=new Node('details');box.restored=restored;run("rememberCodeDetails(restored,'fixture-exclusions')");
assert.equal(restored.open,true);
detail.isConnected=false;detail.open=false;detail.events.toggle();
assert.equal(run("codeDetailsOpen.has('fixture-exclusions')"),true); // detached polling nodes cannot erase intent
const app=fs.readFileSync('web/app.js','utf8');
vm.runInContext(app.slice(app.indexOf('function metrics('),app.indexOf('function render(')),box);
box.state={summary:{aggregate:{measuredRepositories:0,meanCycleSeconds:null},repositories:[],usage:{reason:'Fixture'}},metrics:[],observationJob:{status:'idle'}};
box.section=(text)=>new Node('h2',text);let observed=[];box.observe=remote=>observed.push(remote);
const metricsRoot=new Node('main');box.metricsRoot=metricsRoot;run('metrics(metricsRoot)');
assert.equal(observed.length,0);metricsRoot.children.find(n=>n.text==='Refresh local observations').click();
assert.deepEqual(observed,[false]); // explicit local-only refresh; nothing on render
console.log('Portfolio counting labels, bounded pagination, alias navigation and refresh isolation passed');
