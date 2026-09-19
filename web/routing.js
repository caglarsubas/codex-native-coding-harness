"use strict";
const ROUTE_VIEWS=["workspaces","overview","mission","decisions","queue","workers","knowledge","metrics","usage","gitStatus","artifacts","roadmap","readiness"];
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
function applyDashboardRoute(activateWorkspace=true){
  const route=location.hash?dashboardRoute(location.hash):{view:'overview',id:null};
  if(!route){if(location.hash.startsWith("#/"))showNotice("This dashboard link is not recognized.",true);return;}
  if(route.workspaceId&&route.workspaceId!==workspaceId){switchWorkspace(route.workspaceId,route);return;}
  if(!state)return;
  activateWorkspace=activateWorkspace||Boolean(route.id);
  if(route.id&&route.view==="artifacts"&&!state.observations?.artifacts.some(a=>a.id===route.id)){
    navigateView("artifacts",null,false,activateWorkspace);showNotice("The linked artifact is not in the retained library. No file was opened.",true);return;
  }
  navigateView(route.view,route.id,false,activateWorkspace);
}
window.addEventListener("hashchange",()=>applyDashboardRoute());
