'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const box={Map,titles:{},state:{}};vm.createContext(box);
for(const file of ['summaries','journey','standard','decisions'])vm.runInContext(fs.readFileSync('web/'+file+'.js','utf8'),box);
const resolution={status:'disposed_unqualified',kind:'readiness_prestart_resolution_v1',commandId:'original',brainReceipt:'missing'};
const command={id:'original',kind:'standard_catalog_refresh',status:'queued'};
const snapshot={workspace:{id:'fixture'},repositories:[{policyProfile:'standard'}],meta:{paused:true},commands:[command],
  readinessDisposition:resolution,standard:{run:null,available:false,readinessResolution:resolution,
    catalogRefresh:{id:'original',status:'queued',disposition:resolution}}};
box.state=snapshot;
const journey=box.roadmapJourneyState(snapshot,true,1);
assert.match(journey.title,/stopped before loading/);assert.equal(journey.action,'operations');
assert.match(journey.detail,/Do not click readiness again/);assert.match(journey.detail,/terminal safety is unknown/);
assert.match(box.commandPresentation(command).detail,/No retry or new load allowance/);
assert.match(box.catalogStatus(snapshot.standard.catalogRefresh).detail,/No brain receipt/);
snapshot.standard.readinessResolution={status:'incomplete_or_changed',writesBlocked:true};
assert.match(box.roadmapJourneyState(snapshot,true,1).title,/needs inspection/);
assert.equal(box.roadmapJourneyState(snapshot,true,1).action,'operations');
console.log('pre-load resolution: preserved unqualified outcome; no retry, fabricated receipt or load allowance');
