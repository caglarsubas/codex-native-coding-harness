"use strict";
const ROUTE_VIEWS=["workspaces","overview","conversation","mission","runReadiness","phaseCheckpoints","retention","decisions","queue","workers","knowledge","metrics","usage","gitStatus","artifacts","roadmap","readiness"];
function dashboardRoute(hash){
  const scoped=hash.match(/^#\/w\/([a-z][a-z0-9-]{0,47})\/(.+)$/);
  if(scoped){const route=dashboardRoute('#/'+scoped[2]);return route&&!route.workspaceId?{...route,workspaceId:scoped[1]}:null;}
  const parts=hash.match(/^#\/([a-zA-Z]+)(?:\/([a-f0-9]{64}))?$/);
  if(!parts||!ROUTE_VIEWS.includes(parts[1])||(parts[2]&&!["decisions","artifacts"].includes(parts[1])))return null;
  return {view:parts[1],id:parts[2]||null};
}
function focusRouteTarget(route){
  let target;
  if(route.view==="decisions"&&route.id){
    target=document.getElementById("decision-"+route.id);
    if(target){let ancestor=target.parentElement;while(ancestor){if(ancestor.tagName==="DETAILS")ancestor.open=true;ancestor=ancestor.parentElement;}}
  }else if(route.view==="artifacts"&&route.id)target=document.querySelector(".artifact-reader");
  if(route.id&&!target){showNotice("This linked item is no longer available in the current snapshot. Review the latest items in this view.",true);return;}
  if(target){target.tabIndex=-1;target.scrollIntoView({block:"start"});target.focus({preventScroll:true});}
  else{document.querySelector(".workspace").scrollTop=0;document.getElementById("main").focus({preventScroll:true});}
}
async function applyDashboardRoute(activateWorkspace=true){
  const route=location.hash?dashboardRoute(location.hash):{view:'overview',id:null};
  if(!route){if(location.hash.startsWith("#/"))showNotice("This dashboard link is not recognized.",true);return false;}
  if(route.workspaceId&&route.workspaceId!==workspaceId)return switchWorkspace(route.workspaceId,route,false);
  if(!state&&!unconfiguredProject())return false;
  activateWorkspace=activateWorkspace||Boolean(route.id);
  if(route.id&&route.view==="artifacts"&&!state?.observations?.artifacts.some(a=>a.id===route.id)){
    navigateView("artifacts",null,false,activateWorkspace);showNotice("The linked artifact is not in the retained library. No file was opened.",true);return true;
  }
  navigateView(route.view,route.id,false,activateWorkspace);
  return true;
}

// Only our marked, same-tab dashboard entries enable Back. history.length also
// counts unrelated websites and must never be used to decide whether to leave.
let dashboardNavigation=null,navigationPending=false,navigationApplying=false,navigationTimer=null;
function navigationEntry(value=history.state){
  const entry=value?.dashboardNavigation;
  return entry?.version===1&&typeof entry.route==='string'&&dashboardRoute(entry.route)
    &&Array.isArray(entry.previous)&&entry.previous.length<=100&&entry.previous.every(path=>typeof path==='string'&&dashboardRoute(path))?entry:null;
}
function replaceNavigationEntry(entry){history.replaceState({dashboardNavigation:entry},'',entry.route);}
function initializeDashboardNavigation(){
  const parsed=dashboardRoute(location.hash);
  const route=workspaceHref(parsed?.view||view,parsed?.id||null);
  const retained=navigationEntry();
  dashboardNavigation=retained?.route===route?retained:{version:1,route,previous:[]};
  replaceNavigationEntry(dashboardNavigation);
  $('navigation-back').onclick=goBackInDashboard;
  updateNavigationButton();
}
function resetDashboardNavigation(){
  clearTimeout(navigationTimer);navigationTimer=null;
  dashboardNavigation=null;navigationPending=false;
  history.replaceState(null,'',location.href);
  updateNavigationButton();
}
function updateNavigationButton(){
  const button=$('navigation-back');if(!button)return;
  button.disabled=!dashboardNavigation?.previous.length||navigationPending||workspaceLocked();
  button.title=navigationPending?'Waiting for page navigation':workspaceLocked()?'Wait for the current request':dashboardNavigation?.previous.length?'Back to previous dashboard page':'No previous dashboard page';
}
function recordDashboardVisit(route){
  if(navigationPending){showNotice('Wait for page navigation to finish.',true);return false;}
  if(!dashboardRoute(route))return false;
  if(!dashboardNavigation){history.pushState(null,'',route);return true;}
  if(route===dashboardNavigation.route)return true;
  dashboardNavigation={version:1,route,previous:[...dashboardNavigation.previous,dashboardNavigation.route].slice(-100)};
  history.pushState({dashboardNavigation},'',route);updateNavigationButton();return true;
}
function goBackInDashboard(){
  if(!dashboardNavigation?.previous.length||navigationPending||workspaceLocked())return;
  navigationPending=true;updateNavigationButton();history.back();
}
async function followDashboardHistory(){
  if(!dashboardNavigation)return;
  navigationPending=true;updateNavigationButton();
  if(navigationApplying)return;
  if(workspaceLocked()){
    showNotice('Page navigation will continue when the current request finishes. Nothing has been cancelled.');
    clearTimeout(navigationTimer);navigationTimer=setTimeout(followDashboardHistory,200);return;
  }
  clearTimeout(navigationTimer);navigationTimer=null;
  navigationApplying=true;
  const route=location.hash,entry=navigationEntry();
  try{
    const applied=await applyDashboardRoute();
    if(!dashboardNavigation)return; // Authentication may have expired while switching.
    if(location.hash!==route)return; // A newer browser traversal wins.
    const parsed=dashboardRoute(route);
    // A failed project load can already have changed identity and cleared data.
    // Keep that project's URL, so Back can retry the previous project safely.
    const switched=parsed?.workspaceId===workspaceId&&dashboardRoute(dashboardNavigation.route)?.workspaceId!==workspaceId;
    if(applied||switched){
      const canonical=workspaceHref(parsed.view,parsed.id);
      // An unmarked entry may be an older browser visit, not a newly pushed
      // in-app link. Start a boundary rather than guessing where Back would go.
      dashboardNavigation=entry?.route===canonical?entry:{version:1,route:canonical,previous:[]};
      replaceNavigationEntry(dashboardNavigation);
    }else replaceNavigationEntry(dashboardNavigation);
  }catch(error){
    if(dashboardNavigation&&location.hash===route)replaceNavigationEntry(dashboardNavigation);
    showNotice('Could not open this page. '+error.message,true);
  }finally{
    navigationApplying=false;
    if(dashboardNavigation&&location.hash!==dashboardNavigation.route){followDashboardHistory();}
    else{navigationPending=false;updateNavigationButton();}
  }
}
function dashboardHistoryChanged(){if(dashboardNavigation)followDashboardHistory();else applyDashboardRoute();}
window.addEventListener("hashchange",dashboardHistoryChanged);
// popstate also covers two history entries with the same hash (e.g. a rejected
// link restored to the visible page). Such a Back must not remain pending forever.
window.addEventListener("popstate",dashboardHistoryChanged);
