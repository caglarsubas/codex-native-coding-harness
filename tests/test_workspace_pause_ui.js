"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const box={Date};vm.createContext(box);vm.runInContext(fs.readFileSync('web/workspace-pause.js','utf8'),box);
const state={meta:{brainId:'fixture',brainControl:{desired:'running',phase:'ready'}},workspacePause:{status:'not_requested'}};
const present=()=>box.workspacePausePresentation(state,100);
assert.equal(present().kind,'brain_stop');assert.equal(present().button,'Pause project');assert.equal(present().disabled,false);
state.meta.brainControl={protocol:'workspace_pause_v1',desired:'stopped',phase:'checkpointing'};
state.workspacePause={status:'pausing',blockers:[{code:'inventory_missing'}]};
assert.equal(present().disabled,true);assert.equal(present().observedPaused,false);assert.equal(present().label,'Pausing safely');
state.meta.brainControl.phase='parked';state.workspacePause={status:'checkpoint_saved',blockers:[],checkpointAt:90,validUntil:150};
assert.equal(present().kind,'brain_resume');assert.equal(present().disabled,false);assert.equal(present().observedPaused,false);
state.brainActivity={fresh:true,status:'idle',observedAt:95};assert.equal(present().observedPaused,true);
for(const change of [{fresh:false},{status:'running'},{observedAt:85},{observedAt:105}]) {
  state.brainActivity={fresh:true,status:'idle',observedAt:95,...change};assert.equal(present().observedPaused,false);
}
state.brainActivity={fresh:true,status:'idle',observedAt:95};
state.meta.controller={owner:'still coordinating'};assert.equal(present().observedPaused,false);state.meta.controller=null;
state.workspacePause.validUntil=99;assert.equal(present().observedPaused,false);state.workspacePause.validUntil=150;
state.workspacePause.blockers=[{code:'ownership_changed'}];assert.equal(present().observedPaused,false);
state.meta.brainControl={desired:'stopped',phase:'parked'};state.workspacePause={status:'not_requested'};
assert.equal(present().disabled,false);assert.equal(present().label,'Earlier brain checkpoint saved');assert.equal(present().observedPaused,false);
state.meta.brainControl={desired:'running',phase:'resume_requested'};assert.equal(present().disabled,false);
assert.equal(present().kind,'brain_stop','Pause must still supersede an unreceived resume');
class Element{
  constructor(tag,text=''){this.tag=tag;this.text=text;this.children=[];}
  append(...children){this.children.push(...children);}
  setAttribute(name,value){this[name]=value;}
  addEventListener(){}
}
Object.assign(box,{state,el:(tag,text)=>new Element(tag,text),button:text=>new Element('button',text),
  connected:true,busy:false,num:String,when:String,navigateView:()=>{},
  dispatchPresentation:()=>({button:'Hold dispatch',disabled:false})});
state.workspace={name:'Pilot'};state.meta.brainControl={desired:'stopped',phase:'checkpointing',protocol:'workspace_pause_v1'};
state.workspacePause={status:'pausing',requestedAt:80,retainedWorkers:0,observedTasks:null,blockers:[{code:'inventory_missing',detail:'Inventory required'}]};
const root=new Element('main');box.workspacePausePanel(root);
const content=(node)=>[node.text,...node.children.flatMap(content)].join(' ');
assert.match(content(root),/operator evidence check/);
assert.match(content(root),/do not repeat Play or send a duplicate wake/);
console.log('Project Pause control, legacy checkpoint and fresh native inactivity checks passed');
