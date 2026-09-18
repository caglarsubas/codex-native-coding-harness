const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const box={titles:{},window:{addEventListener(){}},Map,TextEncoder};vm.createContext(box);
for(const file of ['routing.js','workspaces.js'])vm.runInContext(fs.readFileSync('web/'+file,'utf8'),box);
const run=code=>vm.runInContext(code,box);
run("workspaceId='alpha'");
assert.equal(run("workspacePath('/api/state')"),'/api/workspaces/alpha/state');
assert.equal(run("workspacePath('/api/artifacts/abc/download')"),'/api/workspaces/alpha/artifacts/abc/download');
assert.equal(run("workspacePath('/api/workspaces/summary')"),'/api/workspaces/summary');
assert.equal(run("workspacePath('/api/login')"),'/api/login');
assert.equal(run("workspaceHref('overview')"),'#/w/alpha/overview');
assert.equal(run("dashboardRoute('#/w/beta/usage').workspaceId"),'beta');
assert.equal(run("dashboardRoute('#/w/beta/usage').view"),'usage');
for(const route of ['#/w/../overview','#/w/UPPER/overview','#/w/a%2Fb/overview','#/w/beta/w/alpha/overview'])assert.equal(run(`dashboardRoute(${JSON.stringify(route)})`),null);
const app=fs.readFileSync('web/app.js','utf8');
// Exercise the production request function with a late response after selection changes.
const api=app.slice(app.indexOf('async function api('),app.indexOf('const controlRequests='));
let resolve;box.fetch=()=>new Promise(r=>{resolve=r;});box.updateWorkspaceSelector=()=>{};
vm.runInContext(api,box);
const pending=run("api('/api/state')");
run("workspaceId='beta';workspaceGeneration++");
resolve({ok:true,json:async()=>({workspace:{id:'alpha'}})});
pending.then(()=>assert.fail('Old workspace response leaked'),error=>{
  assert.equal(error.workspaceChanged,true);
  console.log('Workspace routing and stale-response isolation checks passed');
}).catch(error=>{console.error(error);process.exitCode=1;});
