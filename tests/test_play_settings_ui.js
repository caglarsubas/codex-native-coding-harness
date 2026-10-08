const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag,text='',className=''){Object.assign(this,{tag,text,className,children:[],dataset:{},value:''});}
  append(...items){this.children.push(...items);}
  insertBefore(child,before){this.children.splice(this.children.indexOf(before),0,child);}
  replaceWith(next){this.replacement=next;}
  setAttribute(k,v){this[k]=v;}
  focus(){this.focused=true;}
  scrollIntoView(){}
}
const calls=[],notices=[],elements=new Map();
const box={workspaceId:'alpha',connected:true,csrf:'session',Date,
  state:{meta:{revision:2,brainId:'brain'},commands:[],standard:{contextHash:'scope'}},
  document:{addEventListener(){},querySelectorAll:()=>[]},el:(...a)=>new Element(...a),
  $:id=>{if(!elements.has(id))elements.set(id,new Element('div'));return elements.get(id);},
  num:String,when:String,refresh:async()=>{},chatTurn:()=>new Element('article'),assistantScroll(){}};
vm.createContext(box);
vm.runInContext(fs.readFileSync('web/assistant-workflow.js','utf8'),box);
vm.runInContext(fs.readFileSync('web/assistant.js','utf8'),box);
box.assistantConnectionChanged=()=>box.refreshAssistantActions();box.assistantStatus=(...args)=>notices.push(args);
const run=code=>vm.runInContext(code,box);
const proposal=(id,settings)=>({document:{workflow:'phase_play',id,brainId:'brain',expiresAt:Date.now()/1000+300,
  request:{preview:{operation:'play',contextHash:'scope'}},preview:{title:'Play this phase',impact:'New phase only.',runSettings:{...settings,measureUsage:true}}}});
const original={durationHours:24,brainAllowance:1800000};
(async()=>{
  let action=box.assistantWorkflowPreview(new Element('article'),proposal('old',original));
  assert.equal(action.confirm.disabled,false);
  action.playInputs.hours.value='4';action.playInputs.allowance.value='3900000';action.playInputs.hours.oninput();
  assert.equal(action.confirm.disabled,true);assert.equal(action.renew.textContent,'Update Play preview');
  box.assistantTypedConfirmation('confirm play');assert.equal(calls.length,0,'Edited unsigned values cannot be confirmed');
  box.api=async(path,options)=>{const body=JSON.parse(options.body);calls.push({path,body});return proposal('new',body.runSettings);};
  await box.assistantRefreshWorkflow(action,new Element('article'));
  assert.deepEqual(calls,[{path:'/api/assistant/preview',body:{key:'phase_play',runSettings:{durationHours:4,brainAllowance:3900000}}}]);
  action=run('assistantActions.get("new")');assert.equal(action.confirm.disabled,false);
  assert.equal(action.playInputs.hours.value,'4');assert.equal(action.playInputs.allowance.value,'3900000');
  assert.equal(run('assistantActions.has("old")'),false,'Only the fresh signed preview stays confirmable');
  action.proposal.document.expiresAt=0;
  box.api=async(path,options)=>{const body=JSON.parse(options.body);calls.push({path,body});return proposal('renewed',body.runSettings);};
  await box.assistantRefreshWorkflow(action,new Element('article'));
  assert.deepEqual(calls.at(-1).body,{key:'phase_play',runSettings:{durationHours:4,brainAllowance:3900000}},'Expiry refresh retains exact selected values');
  action=run('assistantActions.get("renewed")');
  const previewCount=calls.length;
  for(const value of ['', '4.5', '1e2', '-1', '25', '9007199254740993']){
    action.playInputs.hours.value=value;action.playInputs.hours.oninput();
    assert.equal(action.confirm.disabled,true);
    await box.assistantRefreshWorkflow(action,new Element('article'));assert.equal(calls.length,previewCount,'Bad numbers send no request');
  }
  action.playInputs.hours.value='4';action.playInputs.allowance.value='4000000';action.playInputs.hours.oninput();
  box.api=async()=>{throw Error('Checkpoint reserve must remain available');};
  await box.assistantRefreshWorkflow(action,new Element('article'));
  assert.equal(action.confirm.disabled,true);assert.equal(action.refreshError,'Checkpoint reserve must remain available');
  assert.equal(run('assistantActions.get("renewed")'),action,'Failure preserves the edited draft without reverting to confirmable defaults');
  box.workspaceId='beta';await box.assistantRefreshWorkflow(action,new Element('article'));
  assert.equal(calls.length,previewCount,'Foreign project cannot refresh');box.workspaceId='alpha';
  action.uncertain=true;box.refreshAssistantActions();
  assert.equal(action.playInputs.hours.disabled,true,'Uncertain delivery freezes its exact values');
  await box.assistantRefreshWorkflow(action,new Element('article'));assert.equal(calls.length,previewCount,'Uncertain sends never become a new preview');
  assert(!calls.some(c=>c.path.endsWith('/confirm')));
  console.log('Play settings: edited values require a fresh signature; invalid, foreign and uncertain requests remain fenced');
})().catch(error=>{console.error(error);process.exitCode=1;});
