'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const calls=[];
const box={workspaceId:'v3',state:{meta:{brainId:'brain',revision:2},commands:[],standard:{contextHash:'scope'},
  brainNotification:{readinessOwnedSourceAvailable:true}},Map,Set,Date,
  assistantRequestStep:key=>calls.push(key),setTimeout:()=>{throw Error('No automatic readiness retry');}};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/assistant-workflow.js','utf8'),box);
const doc={workflow:'codex_readiness_start',id:'new-readiness',brainId:'brain',expiresAt:null,
  validity:'until_scope_changes',request:{contextHash:'scope'}};
const action={workspace:'v3',proposal:{document:doc}};
assert.equal(box.assistantWorkflowState(action,box.state,Number.MAX_SAFE_INTEGER).locked,false);
box.state.standard.contextHash='changed';assert.equal(box.assistantWorkflowState(action).locked,true);
box.state.standard.contextHash='scope';
const legacy={...action,proposal:{document:{...doc,workflow:'codex_check',expiresAt:1}}};
assert.equal(box.assistantWorkflowState(legacy,box.state,1000).locked,true,'Legacy review clocks are unchanged');
vm.runInContext(fs.readFileSync('web/standard.js','utf8'),box);
box.assistantRequestStep=key=>calls.push(key);
box.requestCatalogForPlay(box.state.standard);
assert.equal(calls.at(-1),'codex_readiness_start','Primary readiness opens a review, never directly submits');
box.scheduleCatalogFollowup({catalogRefresh:{status:'queued',id:'owned',readinessOwned:true,
  notification:{status:'unavailable'},deliveryAttempts:1,maxDeliveryAttempts:3}});
box.scheduleCatalogFollowup({catalogRefresh:{status:'queued',id:'owned-v3',
  notification:{status:'unavailable',preplayCatalog:{version:3}},deliveryAttempts:1,maxDeliveryAttempts:3}});
console.log('Readiness-owned UI: scope validity, legacy expiry, explicit review and no automatic retries');
