'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const box={};vm.createContext(box);vm.runInContext(fs.readFileSync('web/journey.js','utf8'),box);
const s={workspace:{id:'fixture'},repositories:[{policyProfile:'standard'}],standard:{available:false,
  startupPreparation:{status:'startup_preparation_completed'}}};
const value=box.roadmapJourneyState(s,true,1);
assert.match(value.title,/proposal prepared · not started/);assert.equal(value.action,'operations');
assert.match(value.detail,/old readiness request remains consumed and unqualified/);
assert.match(value.detail,/No worker Play, retry or safety assertion/);
s.standard.startupPreparation.status='incomplete_unknown';
assert.match(box.roadmapJourneyState(s,true,1).title,/needs inspection/);
console.log('new preparation has separate inert result; old readiness, Play and safety remain fenced');
