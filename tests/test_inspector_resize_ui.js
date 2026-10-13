'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag,id=''){this.tagName=tag.toUpperCase();this.id=id;this.children=[];this.attrs={};this.inert=false;this.isConnected=true;this.visible=true;this.focusCalls=0;}
  append(...children){for(const child of children){child.parentElement=this;this.children.push(child);}}
  contains(node){return node===this||this.children.some(child=>child.contains(node));}
  setAttribute(name,value){this.attrs[name]=value;}
  getClientRects(){return this.visible?[{}]:[];}
  querySelectorAll(){return this.children.flatMap(child=>[child,...child.querySelectorAll()]);}
  querySelector(selector){return selector==='.session-inspector'?this.inspector:selector.includes('[role=tab]')?this.tab:null;}
  focus(){this.focusCalls++;document.activeElement=this;}
}
const document={body:new Element('body'),activeElement:null};
const media={matches:false,listeners:new Set(),addEventListener(type,fn){assert.equal(type,'change');this.listeners.add(fn);},removeEventListener(type,fn){this.listeners.delete(fn);},change(mobile){this.matches=mobile;for(const fn of [...this.listeners])fn();}};
const header=new Element('header'),root=new Element('main'),footer=new Element('footer');
document.body.append(header,root,footer);
footer.inert=true; // Preserve an unrelated pre-existing inert state.
const shell=new Element('div'),board=new Element('section'),inspector=new Element('aside'),scrim=new Element('button','session-sheet-scrim');
const tab=new Element('button'),close=new Element('button'),composer=new Element('textarea','brain-message');
shell.inspector=inspector;inspector.tab=tab;inspector.append(tab,close,composer);shell.append(board,scrim,inspector);root.append(shell);
const prefs={inspectorOpen:true},box={titles:{},Map,document,matchMedia:query=>{assert.equal(query,'(max-width: 799px)');return media;}};
const observers=[];
box.MutationObserver=class{constructor(fn){this.fn=fn;observers.push(this);}observe(target,options){assert.equal(target,document.body);assert.equal(options.subtree,true);}disconnect(){this.disconnected=true;}};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/session-map.js','utf8'),box);
document.activeElement=composer;composer.value='An unsent private draft';composer.selectionStart=3;composer.selectionEnd=9;
box.sessionWatchInspectorViewport(shell,prefs);
vm.runInContext('sessionInspectorViewport.sync()',box);
assert.equal(inspector.attrs.role,'complementary');assert.equal(inspector.attrs['aria-modal'],'false');
media.change(true);
assert.equal(inspector.attrs.role,'dialog');assert.equal(inspector.attrs['aria-modal'],'true');
assert.equal(document.activeElement,composer,'Resize never replaces or blurs a visible composer');
assert.equal(composer.value,'An unsent private draft');assert.deepEqual([composer.selectionStart,composer.selectionEnd],[3,9]);
assert.equal(composer.focusCalls,0);assert.equal(board.inert,true);assert.equal(header.inert,true);assert.equal(footer.inert,true);
assert.equal(scrim.inert,false,'Dismiss scrim remains pointer-accessible');
media.change(false);
assert.equal(inspector.attrs.role,'complementary');assert.equal(inspector.attrs['aria-modal'],'false');
assert.equal(board.inert,false);assert.equal(header.inert,false);assert.equal(footer.inert,true);
assert.equal(document.activeElement,composer);
document.activeElement=board;media.change(true);
assert.equal(document.activeElement,tab,'Entering an open modal moves outside focus inside');
document.activeElement=close;close.visible=false;media.change(false);
assert.equal(document.activeElement,tab,'Hidden mobile-only controls cannot retain desktop focus');
prefs.inspectorOpen=false;document.activeElement=board;media.change(true);
assert.equal(inspector.attrs.role,'dialog');assert.equal(inspector.attrs['aria-modal'],'false');
assert.equal(document.activeElement,board);assert.equal(header.inert,false);
prefs.inspectorOpen=true;vm.runInContext('sessionInspectorViewport.sync()',box);
assert.equal(inspector.attrs['aria-modal'],'true');assert.equal(header.inert,true);
prefs.inspectorOpen=false;vm.runInContext('sessionInspectorViewport.sync()',box);
assert.equal(header.inert,false,'Closing restores background controls');
assert.equal(media.listeners.size,1);
box.sessionWatchInspectorViewport(shell,prefs);assert.equal(media.listeners.size,1,'Rebinding cannot accumulate media listeners');
assert.equal(observers[0].disconnected,true);
shell.isConnected=false;observers.at(-1).fn();
assert.equal(media.listeners.size,0,'Detached workspace removes its listener');assert.equal(header.inert,false);assert.equal(footer.inert,true);
assert.equal(observers.at(-1).disconnected,true,'Teardown restores inert state without another resize');
assert.equal(vm.runInContext('sessionInspectorViewport',box),null);
console.log('Inspector resize: live roles, modal focus boundary, drafts/caret, both directions, close and listener cleanup passed');
