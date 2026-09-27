"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const nodes=new Map();
const box={workspaceId:'alpha',connected:true,state:{commands:[],standard:{run:{id:'run',status:'blocked'}}},
  $:id=>{if(!nodes.has(id))nodes.set(id,{dataset:{},hidden:false,textContent:''});return nodes.get(id);},
  commandPresentation:c=>({label:c.status==='queued'?'Waiting for receipt':'Completed',detail:'Retained status'}),
  roadmapJourneyState:()=>({title:'Review the proposed phase',label:'Review phase plan'})};
vm.createContext(box);
const app=fs.readFileSync('web/app.js','utf8'),assistant=fs.readFileSync('web/assistant.js','utf8');
vm.runInContext(app.slice(app.indexOf('function showNotice('),app.indexOf('function table(')),box);
vm.runInContext(assistant.slice(assistant.indexOf('function assistantStatus('),assistant.indexOf('function assistantDirectMessage(')),box);
const cmd={id:'exact',kind:'reconcile',status:'queued'};box.state.commands=[cmd];
box.showNotice('Queued once; waiting for receipt',false,cmd.id);
box.assistantStatus('Request saved',false,cmd.id);
box.refreshCommandNotice();box.refreshAssistantStatus();
assert.match(box.$('notice').textContent,/Waiting for receipt/);
cmd.status='completed';cmd.conversationReply={message:'Draft saved'};
box.refreshCommandNotice();box.refreshAssistantStatus();
assert.match(box.$('notice').textContent,/Brain replied.*Review the proposed phase/);
assert.match(box.$('assistant-status').textContent,/Brain replied.*Next: Review phase plan/);
assert(!box.$('notice').textContent.includes('waiting'),'Completion replaces delivery text, not just a regex match');
box.showNotice('Unrelated refresh error',true);box.assistantStatus('Inference timed out',true);
box.refreshCommandNotice();box.refreshAssistantStatus();
assert.equal(box.$('notice').textContent,'Unrelated refresh error');
assert.equal(box.$('assistant-status').textContent,'Inference timed out');
box.showNotice('Saved in alpha',false,cmd.id);box.assistantStatus('Saved in alpha',false,cmd.id);box.workspaceId='beta';
box.refreshCommandNotice();box.refreshAssistantStatus();
assert.equal(box.$('notice').textContent,'Saved in alpha');
assert.equal(box.$('assistant-status').textContent,'Saved in alpha','Foreign-project receipt never updates status');
box.workspaceId='alpha';box.state.commands=[];box.refreshCommandNotice();
assert.equal(box.$('notice').textContent,'Saved in alpha','A missing record is not proof of receipt');
box.state.commands=[{id:'play',status:'completed',kind:'standard_play',payload:{runId:'run'}}];
box.showNotice('Queued',false,'play');box.refreshCommandNotice();
assert.match(box.$('notice').textContent,/Play was received.*stopped at a safety checkpoint/);
console.log('Progress UI: exact receipt replaces stale delivery, project isolation, errors and blocked Play passed');
