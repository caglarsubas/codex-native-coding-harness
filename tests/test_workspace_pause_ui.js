"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const box={Date};vm.createContext(box);vm.runInContext(fs.readFileSync('web/workspace-pause.js','utf8'),box);
const state={meta:{brainId:'fixture',brainControl:{desired:'running',phase:'ready'}},workspacePause:{status:'not_requested'}};
const present=()=>box.workspacePausePresentation(state,100);
assert.equal(present().kind,'brain_stop');assert.equal(present().button,'Pause workspace');assert.equal(present().disabled,false);
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
console.log('Workspace Pause control, legacy checkpoint and fresh native inactivity checks passed');
