const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Node {
  constructor(tag,text=''){this.tag=tag;this.textContent=text;this.children=[];this.hidden=false;this.value='';}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=items;}
  setAttribute(){}
  querySelectorAll(){return [];}
}
const nodes=new Map(),calls=[];
const box={titles:{},Map,TextEncoder,Node,Date,location:{hash:'#/w/harness/conversation'},sessionStorage:{getItem(){return null;},setItem(){}},
  $:id=>{if(!nodes.has(id))nodes.set(id,new Node('div'));return nodes.get(id);},
  el:(tag,text)=>new Node(tag,text),empty:(title,text)=>new Node('section',title+' '+text),
  assistantConnectionChanged(){},window:{addEventListener(){}},
  document:{querySelector:()=>new Node('div')},
  api:async path=>{calls.push(path);return path==='/api/workspaces'?box.data:{csrf:'fixture-csrf'};},
  dashboardRoute:()=>({workspaceId:'harness'}),
};
vm.createContext(box);
vm.runInContext("let csrf=null,state={private:'old'},connected=true,selected=null,view='overview';const brainDrafts=new Map();",box);
vm.runInContext(fs.readFileSync('web/workspaces.js','utf8'),box);
const run=code=>vm.runInContext(code,box);
box.data={enabled:true,workspaces:[{id:'harness',name:'Legacy name'}],catalog:{source:'codex.list_projects',observedAt:100,
  projects:[{id:'p-native-a',name:'Inference',managed:false},{id:'harness',name:'Harness-Onion',managed:true}],unlisted:[]}};
(async()=>{
  await run('initializeWorkspaces()');
  assert.deepEqual(nodes.get('workspace-select').children.map(n=>n.textContent),['Inference','Harness-Onion']);
  assert.equal(run('workspaceId'),'harness');assert.equal(nodes.get('assistant-workspace').textContent,'Harness-Onion');
  calls.length=0;
  await run("selectWorkspaceIdentity('p-native-a')");
  assert.equal(run('state'),null);assert.equal(run('csrf'),null);assert.equal(run('connected'),false);
  assert.equal(run('unconfiguredProject()'),true);assert.equal(nodes.get('export-report').hidden,true);
  assert.equal(calls.length,0,'An unconfigured project must not fetch another ledger session');
  box.button=(text)=>new Node('button',text);
  run('renderUnconfiguredProject()');
  assert.equal(nodes.get('pause').disabled,true);assert.equal(nodes.get('reconcile').disabled,true);
  assert.match(nodes.get('content').children[0].textContent,/no verified development ledger/);
  await run("selectWorkspaceIdentity('harness')");
  assert.equal(run('csrf'),'fixture-csrf');assert.equal(nodes.get('export-report').hidden,false);
  // Native rename stays on the same ledger; saved absent histories have their own group.
  box.data.catalog.projects[1].name='Renamed Harness';
  box.data.catalog.unlisted=[{id:'retained',name:'Old project',managed:true}];
  await run('reloadProjectCatalog()');
  assert.equal(run('workspaceId'),'harness');assert.equal(run('selectedProject().name'),'Renamed Harness');
  assert.equal(nodes.get('workspace-select').children[2].label,'Retained projects · not in Codex list');
  // Preparing sync must never overwrite an existing owner draft.
  box.showNotice=text=>{box.notice=text;};run("brainDrafts.set('harness',{text:'Owner draft'})");
  await run("prepareProjectSync('harness')");
  assert.equal(run("brainDrafts.get('harness').text"),'Owner draft');assert.match(box.notice,/unsent conversation draft/);
  const index=fs.readFileSync('web/index.html','utf8');
  assert.match(index,/aria-label="Project"/);assert.match(index,/>All projects</);
  assert.doesNotMatch(index,/>Development workspace</);
  console.log('Native project selector: order, legacy mapping, inactive selection, isolation, rename, retained history and draft preservation passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
