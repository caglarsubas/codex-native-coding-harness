"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(saved=null){
  const nodes=new Map(),listeners={},notices=[],timers=new Map();let timerId=0;
  const node=id=>{if(!nodes.has(id))nodes.set(id,{disabled:false,setAttribute(){},removeAttribute(){},focus(){},scrollIntoView(){},scrollTop:0});return nodes.get(id);};
  const entries=saved?.entries||[{url:'https://elsewhere.test/',state:null},{url:'http://localhost/#/w/alpha/overview',state:null}];
  let index=saved?.index??1;
  const location={};
  const sync=()=>Object.assign(location,new URL(entries[index].url),{hash:new URL(entries[index].url).hash,href:entries[index].url});sync();
  const write=(value,url,push)=>{
    const entry={url:new URL(url,location.href).href,state:JSON.parse(JSON.stringify(value))};
    if(push){entries.splice(++index);entries.push(entry);}else entries[index]=entry;
    sync();
  };
  function go(delta){const next=index+delta;if(next<0||next>=entries.length)return;const oldHash=location.hash;index=next;sync();listeners.popstate?.();if(location.hash!==oldHash)listeners.hashchange?.();}
  const history={get state(){return entries[index].state;},pushState(value,_,url){write(value,url,true);},replaceState(value,_,url){write(value,url,false);},back(){go(-1);}};
  const box={console,location,history,Map,window:{addEventListener:(name,fn)=>listeners[name]=fn},
    document:{getElementById:node,querySelector:node,querySelectorAll:()=>[]},$:node,
    setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id),
    titles:Object.fromEntries(['overview','usage','roadmap','artifacts','decisions'].map(k=>[k,[k]])),
    busy:false,assistantPending:false,assistantActions:new Map(),state:{observations:{artifacts:[]}},connected:true,
    view:'overview',selected:null,observationPage:0,observationRepo:'all',artifactQuery:'',csrf:null,
    render(){},showNotice:message=>notices.push(message)};
  vm.createContext(box);
  for(const file of ['routing.js','workspaces.js','activity.js'])vm.runInContext(fs.readFileSync('web/'+file,'utf8'),box);
  const run=code=>vm.runInContext(code,box);
  run(`workspaceId='alpha';workspaceList=[{id:'alpha',name:'Alpha'},{id:'beta',name:'Beta',managed:false}];
    saveWorkspaceTab=()=>{};restoreWorkspaceTab=()=>{};
    selectWorkspaceIdentity=async id=>{workspaceId=id;};refresh=async()=>{};
    initializeDashboardNavigation();`);
  return {run,box,nodes,entries,notices,go,async visitHash(hash){history.pushState(null,'',hash);listeners.hashchange();await settle();},
    async retry(){for(const [id,fn] of timers){timers.delete(id);fn();}await settle();},saved:()=>({entries,index})};
}
(async()=>{
  let f=fixture(),{run}=f;
  assert.equal(f.nodes.get('navigation-back').disabled,true,'Direct entry never backs into another site');
  run('goBackInDashboard()');assert.equal(f.saved().index,1);
  run("navigateView('usage');navigateView('usage');navigateView('roadmap')");
  assert.equal(f.entries.length,4,'Repeated current-page clicks do not add history');
  assert.equal(f.nodes.get('navigation-back').disabled,false);
  run('goBackInDashboard();goBackInDashboard()');await settle();
  assert.equal(f.box.view,'usage','Double click is one traversal');
  f.go(-1);await settle();assert.equal(f.box.view,'overview');assert.equal(f.nodes.get('navigation-back').disabled,true);
  f.go(1);await settle();assert.equal(f.box.view,'usage','Native Forward restores the route');
  const reloaded=fixture(f.saved());reloaded.run('goBackInDashboard()');await settle();
  assert.equal(reloaded.box.view,'overview','Back survives reload');
  const legacy=fixture({entries:[{url:'http://localhost/#/usage',state:null}],index:0});
  assert.equal(legacy.box.location.hash,'#/w/alpha/usage','Legacy links capture their original project');
  await legacy.run("switchWorkspace('beta')");legacy.run('goBackInDashboard()');await settle();
  assert.equal(legacy.run('workspaceId'),'alpha');assert.equal(legacy.box.view,'usage');

  f=fixture();run=f.run;
  run("navigateView('usage')");await run("switchWorkspace('beta')");
  const count=f.entries.length;
  assert.equal(run('workspaceId'),'beta');
  assert.equal(f.box.view,'roadmap','New project selection lands on Roadmap & Play');
  run('goBackInDashboard()');await settle();
  assert.equal(run('workspaceId'),'alpha');assert.equal(f.box.view,'usage');
  assert.equal(f.entries.length,count,'Cross-project Back must not push a new entry');
  f.go(1);await settle();assert.equal(run('workspaceId'),'beta');assert.equal(f.entries.length,count);
  run('goBackInDashboard()');await settle();run("navigateView('roadmap')");
  f.go(1);await settle();assert.equal(run('workspaceId'),'alpha','New visit truncates the forward branch');

  // Native Back waits for an in-flight write; the in-app button is disabled.
  f=fixture();run=f.run;run("navigateView('usage');busy=true;updateWorkspaceSelector()");
  assert.equal(f.nodes.get('navigation-back').disabled,true);

  run('goBackInDashboard()');assert.equal(f.box.view,'usage');
  f.go(-1);await settle();assert.equal(f.box.view,'usage');
  run("navigateView('roadmap')");assert.equal(f.box.view,'usage');
  assert.equal(await run("switchWorkspace('beta')"),false);
  run('busy=false');await f.retry();assert.equal(f.box.view,'overview');

  f=fixture();run=f.run;run("navigateView('usage')");await run("switchWorkspace('beta')");
  run('refresh=async()=>{connected=false;state=null;}');
  run('goBackInDashboard()');await settle();
  assert.equal(run('workspaceId'),'alpha');assert.equal(f.box.location.hash,'#/w/alpha/usage','Failed load keeps URL aligned with the cleared project identity');
  assert.equal(run('navigationPending'),false);

  // Newer browser traversal wins over a project switch that is still loading.
  f=fixture();run=f.run;run("navigateView('usage')");await run("switchWorkspace('beta')");
  let release;f.box.waitForSwitch=()=>new Promise(resolve=>release=resolve);
  run('selectWorkspaceIdentity=async id=>{await waitForSwitch();workspaceId=id;}');
  f.go(-1);await settle();f.go(-1);release();await settle();await settle();
  assert.equal(run('workspaceId'),'alpha');assert.equal(f.box.view,'overview');
  assert.equal(f.nodes.get('navigation-back').disabled,true);

  // Unmarked browser visits start a safe boundary; invalid targets stay closed.
  f=fixture();run=f.run;await f.visitHash('#/w/alpha/roadmap');
  assert.equal(f.nodes.get('navigation-back').disabled,true);
  f.go(-1);await settle();assert.equal(f.box.view,'overview');
  await f.visitHash('#/w/missing/overview');assert.equal(run('workspaceId'),'alpha');
  assert.equal(f.box.location.hash,'#/w/alpha/overview');
  await f.visitHash('#/unknown');assert.equal(f.box.location.hash,'#/w/alpha/overview');
  run("navigateView('usage')");await f.visitHash('#/unknown');
  run('goBackInDashboard()');await settle();
  assert.equal(run('navigationPending'),false,'Same-hash browser entries must finish navigation');
  const artifact='a'.repeat(64);f.box.state.observations.artifacts=[{id:artifact}];
  run(`navigateView('artifacts','${artifact}');navigateView('usage');goBackInDashboard()`);await settle();
  assert.equal(f.box.selected,artifact,'Back restores linked artifact identity');
  run('resetDashboardNavigation()');assert.equal(f.nodes.get('navigation-back').disabled,true);
  assert.equal(f.box.history.state,null,'Sign-out clears current navigation marker');
  run('goBackInDashboard()');
  assert.equal(run("navigationEntry({dashboardNavigation:{version:1,route:'#token=private',previous:[]}})"),null);
  run('initializeDashboardNavigation()');
  for(let i=0;i<110;i++)run(`navigateView('${i%2?'usage':'roadmap'}')`);
  assert.equal(run('dashboardNavigation.previous.length'),100,'Retained history metadata is bounded');
  console.log('Dashboard Back: direct entry, duplicates, reload, projects, native history, locks, races, deep links and sign-out passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
