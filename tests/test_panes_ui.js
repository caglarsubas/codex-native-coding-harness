const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const sandbox={TextEncoder,window:{addEventListener(){}},localStorage:{getItem(){return null;}},document:{addEventListener(){}}};
vm.createContext(sandbox);
for(const file of ['panes.js','routing.js','assistant.js'])vm.runInContext(fs.readFileSync('web/'+file,'utf8'),sandbox);
const run=code=>vm.runInContext(code,sandbox);
assert.equal(run('paneGeometry(1440,defaultPanes()).widths.workspace'),854);
// Every combination of collapsed panes fits, including old/corrupt saved widths.
for(const width of [320,390,719,720,760,800,1024,1280,1920])for(let mask=0;mask<8;mask++)for(const focus of ['navigation','workspace','assistant']){
  const layout=run(`paneGeometry(${width},cleanPanePreferences({navigation:999,assistant:999,collapsed:{navigation:${!!(mask&1)},workspace:${!!(mask&2)},assistant:${!!(mask&4)}},focus:'${focus}'}))`);
  assert.equal(Object.values(layout.widths).reduce((a,b)=>a+b,0)+(layout.single?0:16),width);
  assert(Object.values(layout.widths).every(n=>n>=0));
  if(layout.single)assert.equal(Object.values(layout.closed).filter(v=>!v).length,1);
  else if(!layout.closed.workspace)assert(layout.widths.workspace>=320);
}
assert.equal(run('cleanPanePreferences({navigation:-100,assistant:"bad"}).navigation'),180);
assert.equal(run('cleanPanePreferences({navigation:-100,assistant:"bad"}).assistant'),350);
assert.equal(run('paneGeometry(760,defaultPanes()).closed.navigation'),true);
assert.equal(run('paneGeometry(760,{...defaultPanes(),focus:"navigation"}).closed.navigation'),false);
assert.equal(run('defaultPanes().collapsed.navigation'),false);
for(const hash of ['#token=secret','#/unknown','#/decisions/../../secret','#/artifacts/%3Cscript%3E','https://external.example','#/overview/'+ 'a'.repeat(64)]){
  assert.equal(run(`dashboardRoute(${JSON.stringify(hash)})`),null);
}
assert.equal(run(`dashboardRoute('#/decisions/${'a'.repeat(64)}').id`),'a'.repeat(64));
assert.equal(run(`dashboardRoute('#/usage').view`),'usage');
assert.equal(run(`assistantMessages(Array.from({length:12},(_,i)=>({role:i%2?'assistant':'user',content:'x'})),'q').length`),9);
assert(run(`assistantMessages(Array.from({length:8},(_,i)=>({role:i%2?'assistant':'user',content:'界'.repeat(4000)})),'q').length`)<9);
assert.equal(run(`assistantMessages([],'hello')[0].role`),'user');
assert(run(`assistantRecordedFacts({facts:[{id:'F1',data:{dispatchPaused:true}},{id:'F9',data:{workflow:{openDecisions:2,pendingRequests:0}}}]}).includes('2 open decisions')`));
const ui=fs.readFileSync('web/assistant.js','utf8');
assert(!ui.includes('innerHTML'));assert(!ui.includes('/api/commands'));assert(!ui.includes('localStorage'));
assert(fs.readFileSync('web/index.html','utf8').includes('aria-orientation="vertical"'));
console.log('Pane geometry, responsive states, route allowlist and bounded chat checks passed');
