"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag,text=''){this.tag=tag;this.text=text;this.children=[];this.disabled=false;}
  append(...children){this.children.push(...children);}
}
const messages=[],sent=[];
const box={Map,JSON,Math,String,workspaceId:'alpha',busy:false,connected:true,csrf:'fixture',selected:null,
  state:{standard:{available:true,contextHash:'h',boundary:'Partial observations',catalog:{models:[{model:'native',efforts:['low']}]},run:null},mission:null},
  el:(tag,text)=>new Element(tag,text),button:(text,callback)=>Object.assign(new Element('button',text),{click:callback}),
  section:(text)=>new Element('h2',text),table:(heads,rows)=>new Element('table',JSON.stringify(rows)),
  callout:(a,b)=>new Element('p',a+' '+b),num:String,when:String,textCell:(a,b)=>a+' '+b,
  missionDocument(){},render(){},updateWorkspaceSelector(){},refresh:async()=>{},showNotice:(message)=>messages.push(message),
  api:async(path,opts)=>{sent.push({path,body:JSON.parse(opts.body)});if(path.endsWith('preview'))return {preview:{operation:'play',brainAllowance:1,durationHours:8,expiresAt:1},signature:'signed'};return {result:'Recorded'};}};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/standard.js','utf8'),box);
const render=()=>{const root=new Element('root');box.standardPanel(root);return root;};
function all(root){return [root,...root.children.flatMap(x=>x instanceof Element?all(x):[])];}
(async()=>{
  let nodes=all(render());await nodes.find(n=>n.text==='Review Play').click();
  nodes=all(render());let confirm=nodes.find(n=>n.text==='Confirm play');assert.equal(confirm.disabled,true);
  let check=nodes.find(n=>n.type==='checkbox');check.checked=true;check.onchange();assert.equal(confirm.disabled,false);
  box.workspaceId='beta';assert.ok(!all(render()).some(n=>n.text==='Confirm play'),'Workspace preview isolation');
  box.workspaceId='alpha';await confirm.click();assert.equal(sent.filter(s=>s.path.endsWith('confirm')).length,1);
  box.state.standard.run={id:'run',status:'running',phaseId:'p',tasks:[],limits:{maxTasks:2,checkpointReserveTokens:10},brainUsageCoverage:'not_observed'};
  box.state.standard.observedTokens=null;nodes=all(render());assert.ok(nodes.some(n=>String(n.text).includes('Not observed')));
  assert.ok(nodes.some(n=>n.text==='Pause at safe checkpoint'));
  box.state.standard.run.status='stopping';assert.equal(all(render()).find(n=>n.text==='Pause at safe checkpoint').disabled,true);
  box.state.standard.run.status='paused';assert.ok(all(render()).some(n=>n.text==='Review Resume'));
  console.log('Standard UI: explicit confirmation, workspace separation, unknown usage and checkpoint controls passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
