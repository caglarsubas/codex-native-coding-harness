const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag,text='',className=''){Object.assign(this,{tag,text,className,children:[],dataset:{}});}
  append(...items){this.children.push(...items);}
  insertBefore(child,before){this.children.splice(this.children.indexOf(before),0,child);}
  replaceWith(next){this.replacement=next;}
  setAttribute(k,v){this[k]=v;}
  focus(){this.focused=true;}
}
const box={workspaceId:'alpha',connected:true,assistantPending:false,csrf:'csrf',Date,
  state:{meta:{revision:2,brainId:'brain'},commands:[]},assistantActions:new Map(),
  el:(...a)=>new Element(...a),when:String,num:String,assistantStatus:()=>{},refreshAssistantActions:()=>{},assistantConnectionChanged:()=>{},
  commandPresentation:()=>{throw Error('No receipt exists');}};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/assistant-workflow.js','utf8'),box);
const proposal=()=>({document:{workflow:'phase_close',id:'new',brainId:'brain',expiresAt:Date.now()/1000+300,
  request:{expectedRevision:2},preview:{title:'Close stopped phase',impact:'No wake or Play.'}}});
const expired=()=>({workspace:'alpha',proposal:{document:{...proposal().document,id:'old',expiresAt:0}},element:new Element('section')});
(async()=>{
  let calls=[];box.api=async(path,options)=>{calls.push({path,body:JSON.parse(options.body)});return proposal();};
  let action=expired();box.assistantActions.set('old',action);
  assert.equal(box.assistantWorkflowState(action).refreshable,true);
  await box.assistantRefreshWorkflow(action,new Element('article'));
  assert.deepEqual(calls,[{path:'/api/assistant/preview',body:{key:'phase_close'}}]);
  assert.equal(box.assistantActions.has('old'),false);assert(box.assistantActions.has('new'));
  assert(action.element.replacement);assert(box.assistantActions.get('new').confirm.focused);
  assert(!calls.some(c=>c.path.includes('confirm')),'Refresh never confirms, notifies or retries effects');
  action=expired();action.proposal.document.workflow='brain_message';
  action.proposal.document.preview.message='Keep this exact message.\nDo not start Play.';
  await box.assistantRefreshWorkflow(action,new Element('article'));
  assert.deepEqual(calls.at(-1),{path:'/api/assistant/preview',body:{key:'brain_message',text:'Keep this exact message.\nDo not start Play.'}},'Refresh preserves the exact brain-message draft');
  for(const flags of [{uncertain:true},{sending:true},{receipt:{}},{cancelled:true},{workspace:'other'}]){
    action=Object.assign(expired(),flags);const count=calls.length;
    await box.assistantRefreshWorkflow(action,new Element('article'));
    assert.equal(calls.length,count,'Never replace submitted, ambiguous, cancelled or foreign requests');
  }
  box.assistantActions.clear();action=expired();box.assistantActions.set('old',action);
  box.api=async()=>{throw Error('Host offline; no request sent');};
  await box.assistantRefreshWorkflow(action,new Element('article'));
  assert.equal(action.refreshError,'Host offline; no request sent');assert.equal(action.element.replacement,undefined);
  assert.equal(box.assistantActions.get('old'),action,'Failed refresh preserves the old review');
  assert.equal(box.assistantPending,false);
  box.api=async()=>{box.workspaceId='beta';return proposal();};
  await box.assistantRefreshWorkflow(action,new Element('article'));
  assert.equal(action.element.replacement,undefined,'Late response cannot replace another project');
  console.log('Review refresh: in-place preview only, no effect replay, failed/foreign responses preserved');
})().catch(error=>{console.error(error);process.exitCode=1;});
