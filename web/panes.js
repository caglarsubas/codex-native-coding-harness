"use strict";
const PANE_NAMES=["navigation","workspace","assistant"], PANE_STORE="orchestrator-panes-v1";
function defaultPanes(){return {navigation:220,assistant:460,collapsed:{navigation:false,workspace:true,assistant:false},focus:"assistant"};}
function cleanPanePreferences(raw){
  const p=defaultPanes();
  if(!raw||typeof raw!=="object")return p;
  for(const [name,min,max] of [["navigation",180,360],["assistant",280,640]])
    if(Number.isFinite(raw[name]))p[name]=Math.max(min,Math.min(max,raw[name]));
  for(const name of PANE_NAMES)if(typeof raw.collapsed?.[name]==="boolean")p.collapsed[name]=raw.collapsed[name];
  if(PANE_NAMES.includes(raw.focus))p.focus=raw.focus;
  return p;
}
function paneGeometry(width,p){
  width=Math.max(0,width);
  const closed={...p.collapsed}, size={navigation:p.navigation,workspace:320,assistant:p.assistant};
  const focus=!closed[p.focus]?p.focus:PANE_NAMES.find(n=>!closed[n])||"workspace";
  if(width<720){return {single:true,closed:Object.fromEntries(PANE_NAMES.map(n=>[n,n!==focus])),widths:Object.fromEntries(PANE_NAMES.map(n=>[n,n===focus?width:0])),limits:{}};}
  const minimum=()=>PANE_NAMES.reduce((s,n)=>s+(closed[n]?44:n==="navigation"?180:n==="assistant"?280:320),16);
  // Preserve user preferences; auto-fit only the effective layout.
  for(const n of [...["navigation","assistant","workspace"].filter(n=>n!==focus),focus])if(minimum()>width)closed[n]=true;
  for(const n of PANE_NAMES)if(closed[n])size[n]=44;
  const available=width-16;
  if(!closed.workspace){
    size.navigation=closed.navigation?44:Math.min(p.navigation,Math.max(180,available-320-(closed.assistant?44:280)));
    size.assistant=closed.assistant?44:Math.min(p.assistant,Math.max(280,available-size.navigation-320));
    size.workspace=available-size.navigation-size.assistant;
  }else if(!closed.assistant){size.navigation=closed.navigation?44:Math.min(p.navigation,available-44-280);size.assistant=available-44-size.navigation;}
  else if(!closed.navigation)size.navigation=available-88;
  else size.workspace=available-88;
  const limits={navigation:[180,Math.min(360,available-44-(closed.assistant?44:280)-(closed.workspace?0:276))],
    assistant:[280,Math.min(640,available-size.navigation-(closed.workspace?44:320))]};
  return {single:false,closed,widths:size,limits};
}
// The project graph now owns the desktop layout. Preserve these compatibility
// functions for signed chat controls that formerly revealed a separate pane.
let panePreferences=defaultPanes();
function savePanes(){}
function applyPanes(){}
function revealPane(name){if(name==='assistant'&&typeof sessionShowGuide==='function')sessionShowGuide();}
function initPanes(){
  const picker=document.getElementById('workspace-picker'),slot=document.getElementById('project-switch-slot');
  if(picker&&slot)slot.append(picker);
  const theme=document.getElementById('theme'),toggle=document.getElementById('theme-toggle');
  if(theme&&toggle)toggle.onclick=()=>theme.click();
  document.getElementById('brand-graph').onclick=()=>navigateView('overview');
  document.getElementById('guide-toggle').onclick=()=>sessionShowGuide();
  document.getElementById('reset-panes').onclick=()=>navigateView('overview');
}
if(typeof document!=="undefined")document.addEventListener("DOMContentLoaded",initPanes,{once:true});
