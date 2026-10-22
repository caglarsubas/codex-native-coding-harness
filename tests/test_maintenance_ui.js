'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
class Element {
  constructor() { this.children = []; this.dataset = {}; this.hidden = false; this.textContent = ''; }
  replaceChildren(...values) { this.children = values; }
  append(...values) { this.children.push(...values); }
  setAttribute(key, value) { this[key] = value; }
  addEventListener(key, fn) { this['on' + key] = fn; }
}
const ids = ['notice','project','workspace','next-step','brain-status','brain-node','preparation-node','inspector-title','inspector-summary','facts','usage','request','refresh','theme'];
const nodes = Object.fromEntries(ids.map(id => [id, new Element()]));
const requests = [], fragmentChanges = [], store = new Map();
let payload = {mode:'certificate_read_only',workspaceId:'<script>NOT_EXECUTED</script>',
  nextStep:'No load or Play',originalReadiness:{id:'original'},preparation:{latestTurnId:'ended',historicalObservedAt:1},
  usage:{observedLastTurnTokens:null,chargedReservationFloor:15823,carriedPhaseCeiling:5736373,futurePhaseCeiling:5720550,coverage:'per_turn_not_lifetime',gaps:['lifetime_coverage_not_asserted']},
  connection:{activityAtObservation:'notLoaded',observedAt:1,savedSignInPresentAtObservation:true,loadedPolicyMatchedAtObservation:false,observationStale:true}};
let failure = null;
const box = {URLSearchParams, Date, Number, String, document:{getElementById:id=>nodes[id],createElement:()=>new Element(),documentElement:{dataset:{}}},
  location:{hash:'#token=fixture-token',pathname:'/'},history:{replaceState:(...args)=>fragmentChanges.push(args)},
  localStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)},
  fetch:async (path, options={})=>{requests.push({path,options});return {ok:!failure,status:failure||200,json:async()=>payload};}};
const source = fs.readFileSync('web/maintenance.js','utf8');
vm.createContext(box); vm.runInContext(source, box);
const flush = ()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
  await flush();
  assert.deepEqual(requests.map(r=>[r.path,r.options.method||'GET']),[['/api/login','POST'],['/api/state','GET']]);
  assert.equal(fragmentChanges.length,1,'Private token is removed from the URL');
  assert.equal(nodes.project.textContent,payload.workspaceId,'Foreign markup remains text');
  assert.equal(nodes.workspace.hidden,false); assert.match(nodes['brain-status'].textContent,/Unloaded.*unknown/);
  assert(nodes.usage.children.some(n=>n.textContent==='Unknown'),'Missing usage never becomes zero');
  assert(nodes.facts.children.some(n=>n.textContent==='Stale; no automatic refresh'));
  nodes['preparation-node'].onclick();
  assert.equal(nodes['inspector-title'].textContent,'Retained preparation');
  assert.equal(nodes['preparation-node']['aria-pressed'],'true');
  assert.equal(requests.length,2,'Selecting a node performs no native or HTTP request');
  nodes.theme.onclick(); assert.equal(box.document.documentElement.dataset.theme,'dark');
  await nodes.refresh.onclick(); await flush(); assert.equal(requests.at(-1).path,'/api/state');
  assert.equal(requests.filter(r=>r.options.method==='POST').length,1,'Only private browser pairing posts');
  failure=503;await nodes.refresh.onclick();await flush();
  assert.equal(nodes.workspace.hidden,true,'Scope failure hides the last good view');
  assert.match(nodes.notice.textContent,/unavailable or changed/);
  assert(!source.includes('setInterval')&&!source.includes('innerHTML'),'No native polling or HTML injection');
  console.log('Read-only recovery workspace: auth, unknowns, node selection, freshness, no controls or polling, fail-closed refresh passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
