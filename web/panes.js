"use strict";
const PANE_NAMES=["navigation","workspace","assistant"], PANE_STORE="orchestrator-panes-v1";
function defaultPanes(){return {navigation:220,assistant:350,collapsed:{navigation:false,workspace:false,assistant:false},focus:"workspace"};}
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
let panePreferences=defaultPanes(), paneLayout;
try{panePreferences=cleanPanePreferences(JSON.parse(localStorage.getItem(PANE_STORE)));}catch{}
function savePanes(){try{localStorage.setItem(PANE_STORE,JSON.stringify(panePreferences));}catch{}}
function applyPanes(){
  const shell=document.getElementById("pane-shell");if(!shell)return;
  const focused=document.activeElement;
  paneLayout=paneGeometry(shell.clientWidth,panePreferences);
  const g=paneLayout;
  shell.style.gridTemplateColumns=`${g.widths.navigation}px ${g.single?0:8}px ${g.widths.workspace}px ${g.single?0:8}px ${g.widths.assistant}px`;
  for(const name of PANE_NAMES){
    const pane=document.getElementById(name+"-pane"), body=pane.querySelector(".pane-body"), expand=pane.querySelector(".pane-expand");
    pane.hidden=g.single&&g.closed[name];body.hidden=g.closed[name];expand.hidden=!g.closed[name]||g.single;
    document.querySelectorAll(`[data-pane-toggle="${name}"]`).forEach(b=>b.setAttribute("aria-expanded",String(!g.closed[name])));
    if(g.closed[name]&&body.contains(focused))document.querySelector(`.pane-toolbar [data-pane-toggle="${name}"]`).focus();
  }
  for(const name of ["navigation","assistant"]){
    const handle=document.getElementById(name+"-resizer"), disabled=g.single||g.closed[name]||(g.closed.workspace&&(name==='assistant'||g.closed.assistant));
    handle.hidden=g.single;handle.tabIndex=disabled?-1:0;handle.setAttribute("aria-disabled",String(disabled));
    const [min,max]=g.limits[name]||[0,0];handle.setAttribute("aria-valuemin",Math.min(min,g.widths[name]));handle.setAttribute("aria-valuemax",Math.max(min,max,g.widths[name]));
    handle.setAttribute("aria-valuenow",Math.round(g.widths[name]));handle.setAttribute("aria-valuetext",Math.round(g.widths[name])+" pixels");
  }
}
function revealPane(name){panePreferences.collapsed[name]=false;panePreferences.focus=name;savePanes();applyPanes();}
function resizePane(name,value){
  const [min,max]=paneLayout.limits[name];panePreferences[name]=Math.max(min,Math.min(max,value));savePanes();applyPanes();
}
function initPanes(){
  document.querySelectorAll("[data-pane-toggle]").forEach(b=>b.addEventListener("click",()=>{
    const name=b.dataset.paneToggle;
    if(paneLayout.single){if(!paneLayout.closed[name]){panePreferences.focus=name==="workspace"?"navigation":"workspace";panePreferences.collapsed[panePreferences.focus]=false;}else revealPane(name);}
    else{panePreferences.collapsed[name]=!paneLayout.closed[name];if(!panePreferences.collapsed[name])panePreferences.focus=name;}
    savePanes();applyPanes();document.getElementById("pane-announcement").textContent=name+(paneLayout.closed[name]?" collapsed":" expanded");
  }));
  document.getElementById("reset-panes").onclick=()=>{panePreferences=defaultPanes();savePanes();applyPanes();};
  for(const name of ["navigation","assistant"]){
    const handle=document.getElementById(name+"-resizer");
    handle.addEventListener("keydown",e=>{
      if(handle.getAttribute("aria-disabled")==="true"||!["ArrowLeft","ArrowRight","Home","End"].includes(e.key))return;
      e.preventDefault();const [min,max]=paneLayout.limits[name], sign=name==="navigation"?1:-1;
      resizePane(name,e.key==="Home"?min:e.key==="End"?max:paneLayout.widths[name]+(e.key==="ArrowRight"?1:-1)*sign*(e.shiftKey?48:16));
    });
    handle.addEventListener("pointerdown",e=>{
      if(e.button!==0||handle.getAttribute("aria-disabled")==="true")return;
      e.preventDefault();handle.focus();handle.setPointerCapture(e.pointerId);
      const start=e.clientX, initial=paneLayout.widths[name];let frame=0, latest=start;
      const shell=document.getElementById("pane-shell");shell.classList.add("is-resizing");handle.dataset.dragging="true";
      const update=()=>{frame=0;resizePane(name,initial+(latest-start)*(name==="navigation"?1:-1));};
      const move=ev=>{latest=ev.clientX;if(!frame)frame=requestAnimationFrame(update);};
      const end=()=>{if(frame){cancelAnimationFrame(frame);update();}shell.classList.remove("is-resizing");delete handle.dataset.dragging;handle.removeEventListener("pointermove",move);handle.removeEventListener("lostpointercapture",end);};
      handle.addEventListener("pointermove",move);handle.addEventListener("lostpointercapture",end);
    });
  }
  new ResizeObserver(applyPanes).observe(document.getElementById("pane-shell"));applyPanes();
}
if(typeof document!=="undefined")document.addEventListener("DOMContentLoaded",initPanes,{once:true});
