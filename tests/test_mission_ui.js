"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const sent=[],notices=[];let fail=true,sequence=0;
const box={titles:{},Map,JSON,crypto:{randomUUID:()=>`fixture-${++sequence}`},busy:false,connected:true,
  workspaceId:'alpha',csrf:'fixture-csrf',selected:null,
  el:()=>({setAttribute(){},textContent:''}),updateWorkspaceSelector(){},
  showNotice:(message)=>notices.push(message),refresh:async()=>{},
  api:async(path,options)=>{sent.push({path,body:JSON.parse(options.body)});if(fail)throw new Error('Connection lost');return {receipt:{executionAuthorized:false}};}};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/missions.js','utf8'),box);
const run=code=>vm.runInContext(code,box),control={disabled:false,closest:()=>null,after(){}};
(async()=>{
  run("missionDrafts.set('alpha',{spec:{goal:'Alpha only'}});missionDrafts.set('beta',{spec:{goal:'Beta only'}})");
  const payload={operation:'save',expectedRevision:1,spec:{goal:'Alpha only'}};
  await box.missionWrite(payload,control);
  assert.equal(run("missionDrafts.get('alpha').spec.goal"),'Alpha only');
  assert.equal(box.busy,false);assert.equal(control.disabled,false);
  fail=false;await box.missionWrite(payload,control);
  assert.equal(sent[0].body.id,sent[1].body.id,'Uncertain retry must keep request identity');
  assert.equal(run("missionDrafts.has('alpha')"),false);
  assert.equal(run("missionDrafts.get('beta').spec.goal"),'Beta only');
  assert.ok(sent.every(r=>r.path==='/api/mission'));
  assert.equal(run('missionRequests.size'),0);
  box.workspaceId='beta';await box.missionWrite(payload,control);
  assert.notEqual(sent[2].body.id,sent[1].body.id);
  assert.ok(notices.at(-1).includes('No execution was authorized'));
  box.connected=false;await box.missionWrite(payload,control);
  assert.equal(sent.length,3,'Disconnected UI must not submit');
  console.log('Mission draft isolation, retry identity and no-activation checks passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
