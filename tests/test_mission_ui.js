"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const sent=[],notices=[];let fail=true,sequence=0;
class Node{
  constructor(tag,text=''){this.tag=tag;this.tagName=tag.toUpperCase();this.textContent=text;this.children=[];this.classList={contains:()=>false};}
  append(...children){this.children.push(...children);}
  setAttribute(){}
  setCustomValidity(message){this.validationMessage=message;}
  after(){}
  closest(){return null;}
  reportValidity(){return true;}
}
const nodes=root=>[root,...root.children.flatMap(nodes)];
const inspectorRoutes=[];
const box={titles:{},Map,JSON,crypto:{randomUUID:()=>`fixture-${++sequence}`},busy:false,connected:true,
  workspaceId:'alpha',csrf:'fixture-csrf',selected:null,
  state:{mission:{revision:1,document:{spec:{goal:'Earlier reviewed scope'}}},repositories:[{id:'fixture',policyProfile:'standard',mergePolicy:'manual'}]},
  document:{querySelector:()=>null},render(){},
  sessionSelectRoute:route=>inspectorRoutes.push(route),
  el:(tag,text)=>new Node(tag,text),section:(title)=>new Node('h2',title),callout:(title,body)=>new Node('aside',title+' '+body),
  button:(title,click)=>Object.assign(new Node('button',title),{click}),num:String,updateWorkspaceSelector(){},
  showNotice:(message)=>notices.push(message),refresh:async()=>{},
  api:async(path,options)=>{sent.push({path,body:JSON.parse(options.body)});if(fail)throw new Error('Connection lost');return {receipt:{executionAuthorized:false}};}};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/missions.js','utf8'),box);
const run=code=>vm.runInContext(code,box),control={disabled:false,closest:()=>null,after(){}};
(async()=>{
  for(const [count,tokens,total] of [[1,20000000,3],[2,20000000,3],[3,30000000,6],[5,30000000,6],[6,40000000,10],[10,40000000,10]]){
    const result=run(`missionLimitSuggestion(Array.from({length:${count}},(_,i)=>({title:'Task '+i,repository:'fixture',exactFiles:['src/task-'+i+'.py']})))`);
    assert.equal(result.limits.tokenBudget,tokens);assert.equal(result.limits.maxTasks,total);
    assert.equal(result.limits.checkpointReserveTokens,tokens/10);
    assert.equal(result.limits.maxParallelTasks,Math.min(3,count));
  }
  assert.equal(run("missionLimitSuggestion([{title:'a',repository:'fixture',exactFiles:['a.py']},{title:'b',repository:'fixture',exactFiles:['a.py']}]).limits.maxParallelTasks"),1);
  assert.equal(run("missionLimitSuggestion([{title:'a',repository:'fixture',exactFiles:['a.py','b.py']},{title:'b',repository:'fixture',exactFiles:['a.py']},{title:'c',repository:'fixture',exactFiles:['b.py']}]).limits.maxParallelTasks"),2,
    'Choose the largest disjoint task subset, not merely the first task');
  assert.equal(run("missionLimitSuggestion([]).limits.maxParallelTasks"),1);
  assert.equal(run("missionLimitSuggestion(Array.from({length:11},(_,i)=>({title:String(i),repository:'fixture',exactFiles:[i+'.py']}))).limits"),null);
  assert.match(run("missionLimitSuggestion(Array.from({length:10},(_,i)=>({title:String(i),repository:'fixture',exactFiles:[i+'.py']})),'isolated_worktrees').reason"),/11 total task slots/);
  assert.match(run("missionTaskOutline('One | fixture | ../secret.py').error"),/exact repository-relative/);
  box.source={repository:'fixture',path:'docs/plan.md',commit:'a'.repeat(40),documentId:'b'.repeat(64),
    documentVersion:3,observedAt:12,kind:'checklist',line:4,text:'Build a bounded fixture'};
  assert.equal(run('openMissionEditor(source)'),true);
  assert.equal(inspectorRoutes.at(-1),'mission','Opening a local draft invalidates the cached in-page inspector');
  const handoff=run("missionDrafts.get('alpha')");
  assert.equal(handoff.revision,1);assert.equal(handoff.spec.goal,'Build a bounded fixture');
  assert.equal(handoff.spec.authority.approvalMode,'prepare_only');
  assert.equal(handoff.spec.phase.scope.length,0);assert.equal(handoff.spec.authority.tokenBudget,20000000);
  assert.equal(handoff.spec.phase.durationHours,24,'New standard drafts suggest one explicit 24-hour phase window');
  assert.equal(handoff.spec.authority.checkpointReserveTokens,2000000);
  assert.equal(handoff.spec.authority.maxParallelTasks,1,'No outline cannot imply independent work');
  assert.match(handoff.spec.phase.objective,/Roadmap source: fixture \/ docs\/plan.md/);
  assert.match(handoff.spec.phase.objective,/retained document b{64} v3; checklist line 4: Build a bounded fixture/);
  assert.equal(sent.length,0,'Preparing a local draft sends no request');
  assert.equal(run("missionDrafts.get('alpha').source.line"),4);
  box.root=new Node('main');run('missionEditor(root,state.mission)');
  const phaseHours=nodes(box.root).find(n=>n.tag==='label'&&n.textContent==='Phase window (hours from Play)').children[0];
  assert.equal(phaseHours.value,24);phaseHours.value='4';phaseHours.oninput();
  assert.equal(handoff.spec.phase.durationHours,4,'Editing changes only the unsaved proposal');
  assert.equal(sent.length,0);
  assert.ok(nodes(box.root).some(n=>String(n.textContent).includes('The phase window above controls Play.')));
  assert.ok(!nodes(box.root).some(n=>String(n.textContent).includes('Play suggests 24 hours')),
    'Outline copy must not introduce a competing duration');
  const mergeMode=nodes(box.root).find(n=>n.tag==='label'&&n.textContent==='Phase merge mode').children[0];
  assert.equal(mergeMode.value,'manual','Manual is the default');
  assert.ok(!('mergeMode' in handoff.spec.authority),'Rendering does not opt in');
  mergeMode.value='brain_exact_pr_v1';mergeMode.onchange();
  assert.equal(handoff.spec.authority.mergeMode,'brain_exact_pr_v1');
  assert.equal(sent.length,0,'Selecting merge mode is only an unsaved draft');
  mergeMode.value='manual';mergeMode.onchange();
  assert.ok(nodes(box.root).some(n=>String(n.textContent).includes('a schema-1-only launcher cannot operate this protocol')));
  const objective=nodes(box.root).find(n=>n.tag==='label'&&n.textContent==='Phase objective').children[0];
  assert.equal(objective.value,'','The objective is editable without exposing the provenance line as removable text');
  objective.value='Deliver one local fixture';objective.oninput();
  assert.match(handoff.spec.phase.objective,/^Deliver one local fixture\n\nRoadmap source:/);
  assert.equal(nodes(box.root).filter(n=>n.tag==='input'&&n.type==='checkbox'&&n.checked).length,0,
    'No repository or operation is selected');
  box.invalidSource={...box.source,documentId:'wrong'};
  assert.equal(run('openMissionEditor(invalidSource)'),false,'Malformed source cannot replace a draft');
  assert.equal(run("missionDrafts.get('alpha').source.line"),4);
  run("missionDrafts.set('beta',{spec:{goal:'Beta only'}})");
  const payload={operation:'save',expectedRevision:1,spec:JSON.parse(JSON.stringify(handoff.spec))};
  await box.missionWrite(payload,control);
  assert.equal(run("missionDrafts.get('alpha').spec.goal"),'Build a bounded fixture');
  assert.equal(box.busy,false);assert.equal(control.disabled,false);
  fail=false;await box.missionWrite(payload,control);
  assert.equal(sent[0].body.id,sent[1].body.id,'Uncertain retry must keep request identity');
  assert.match(sent[1].body.spec.phase.objective,/Roadmap source: fixture \/ docs\/plan.md/);
  assert.equal(sent[1].body.spec.authority.approvalMode,'prepare_only');
  assert.ok(sent.slice(0,2).every(r=>r.body.operation==='save'&&!('confirmed' in r.body)),
    'The handoff never submits an owner review or Play confirmation');
  assert.equal(run("missionDrafts.has('alpha')"),false);
  assert.equal(run("missionDrafts.get('beta').spec.goal"),'Beta only');
  assert.ok(sent.every(r=>r.path==='/api/mission'));
  assert.equal(run('missionRequests.size'),0);
  box.workspaceId='beta';await box.missionWrite(payload,control);
  assert.notEqual(sent[2].body.id,sent[1].body.id);
  assert.ok(notices.at(-1).includes('No execution was authorized'));
  box.connected=false;await box.missionWrite(payload,control);
  assert.equal(sent.length,3,'Disconnected UI must not submit');
  box.workspaceId='alpha';box.resetDraft=handoff;box.root=new Node('main');
  run("missionDrafts.set('alpha',resetDraft);missionEditor(root,state.mission)");
  const routesBeforeDiscard=inspectorRoutes.length;
  nodes(box.root).find(n=>n.tag==='button'&&n.textContent==='Discard unsaved edits').click();
  assert.equal(run("missionDrafts.has('alpha')"),false);
  assert.equal(inspectorRoutes.length,routesBeforeDiscard+1);
  assert.equal(inspectorRoutes.at(-1),'mission','Discard invalidates the inspector without a ledger write');
  assert.equal(sent.length,3);
  console.log('Mission draft isolation, retry identity and no-activation checks passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
