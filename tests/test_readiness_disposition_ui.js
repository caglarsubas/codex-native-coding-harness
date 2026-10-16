'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const calls=[],timers=[];
const box={titles:{},workspaceId:'v3',busy:false,connected:true,csrf:'fixture',
  state:{readinessDisposition:{commandId:'original',status:'disposed_unqualified'}},
  crypto:{randomUUID:()=> 'distinct-new-request'},setTimeout:fn=>{timers.push(fn);return 1;},
  api:async(path,options)=>{calls.push({path,body:JSON.parse(options.body)});return {id:'distinct-new-request',status:'queued'};},
  render:()=>{},refresh:async()=>{},showNotice:()=>{},catalogReadinessIssue:()=>null};
vm.createContext(box);
for(const file of ['web/standard.js','web/decisions.js','web/journey.js'])vm.runInContext(fs.readFileSync(file,'utf8'),box);
const disposition={status:'disposed_unqualified',commandId:'original',brainReceipt:'missing',originalStatus:'queued'};
const refresh={id:'original',status:'queued',createdAt:Date.now()/1000,disposition,
  notification:{status:'unavailable'},deliveryAttempts:1,maxDeliveryAttempts:3};
const state={workspace:{id:'v3'},repositories:[{policyProfile:'standard'}],commands:[],
  mission:{effectiveStatus:'reviewed',document:{spec:{phase:{id:'first'},authority:{approvalMode:'phase_delegated'}}}},
  standard:{run:null,available:false,catalogRequired:true,catalogRefresh:refresh,contextHash:'new-context'}};
assert.match(box.catalogStatus(refresh).title,/ended without a result/);
assert.match(box.catalogStatus(refresh).detail,/missing brain receipt is preserved/);
assert.match(box.commandPresentation({id:'original',kind:'standard_catalog_refresh',status:'queued'}).label,/unqualified/);
const journey=box.roadmapJourneyState(state,true);
assert.equal(journey.action,'catalog');assert.equal(journey.label,'Request a new readiness check');
assert.match(journey.detail,/nothing will be resent automatically/);
for(let i=0;i<10;i++){box.scheduleCatalogFollowup(state.standard);box.roadmapJourneyState(state,true);}
assert.equal(timers.length,0,'Rendering a disposed attempt must not schedule delivery or another check');
assert.equal(calls.length,0);
(async()=>{
  await box.requestCatalogForPlay(state.standard);
  assert.equal(calls.length,1,'Only an explicit new request can submit');
  assert.equal(calls[0].body.id,'distinct-new-request');
  assert.notEqual(calls[0].body.id,refresh.id);
  assert.equal(calls[0].body.contextHash,'new-context');
  assert.equal(refresh.status,'queued','Raw original saved status remains a separate fact');
  console.log('readiness disposition UI: distinct request, preserved history, no automatic send');
})().catch(error=>{console.error(error);process.exitCode=1;});
