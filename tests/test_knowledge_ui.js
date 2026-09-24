"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag,text=''){this.tag=tag;this.text=String(text||'');this.children=[];this.value='';}
  append(...items){this.children.push(...items);}
  setAttribute(){}
}
const calls=[],views=[];
const box={Map,URLSearchParams,workspaceId:'alpha',state:{repositories:[{id:'app',policyProfile:'standard'}]},csrf:'fixture',
  el:(tag,text)=>new Element(tag,text),button:(title,click)=>Object.assign(new Element('button',title),{click}),
  section:(title,body)=>new Element('section',title+' '+(body||'')),callout:(title,body)=>new Element('p',title+' '+body),
  when:String,render(){},navigateView:(view,id)=>views.push([view,id]),
  api:async(path)=>{calls.push(path);
    if(path.includes('/status'))return {status:'current',fileCount:2,commit:'a'.repeat(40),provider:{status:'unavailable'}};
    if(path.includes('/records'))return {records:[{kind:'roadmap',title:'Plan',id:'b'.repeat(64),version:2,provenance:'RECORDED_SOURCE'}],truncated:false};
    if(path.includes('/search'))return {status:'current',coverage:'indexed_source_only',truncated:false,results:[{repository:'app',path:'src/service.py',line:3,excerpt:'def approve():',provenance:'EXTRACTED',commit:'a'.repeat(40),indexHash:'c'.repeat(64)}]};
    if(path.includes('/source'))return {path:'src/service.py',commit:'a'.repeat(40),excerpt:'def approve():'};
    if(path.includes('/related'))return {status:'unavailable',items:[]};
    throw Error('Unexpected '+path);
  }};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/knowledge.js','utf8'),box);
const nodes=root=>[root,...root.children.flatMap(item=>item instanceof Element?nodes(item):[])];
(async()=>{
  let root=new Element('root');box.projectKnowledge(root);
  await nodes(root).find(item=>item.text==='Index status').click();
  assert.ok(calls.some(path=>path.includes('/status')));
  const input=nodes(root).find(item=>item.tag==='input');input.value='approve';
  await nodes(root).find(item=>item.text==='Search').click();
  root=new Element('root');box.projectKnowledge(root);
  assert.ok(nodes(root).some(item=>item.text.includes('RECORDED_SOURCE')));
  await nodes(root).find(item=>item.text==='Read cited source').click();
  await nodes(root).find(item=>item.text==='Related items').click();
  nodes(root).find(item=>item.text==='Open recorded version').click();
  assert.deepEqual(views,[['artifacts','b'.repeat(64)]]);
  assert.ok(calls.some(path=>path.includes('/source')));
  box.api=async(path)=>{if(path.includes('/refresh'))throw Error('Local extraction failed');throw Error('Unexpected '+path);};
  await nodes(root).find(item=>item.text==='Refresh local index').click();
  root=new Element('root');box.projectKnowledge(root);
  assert.ok(nodes(root).some(item=>item.text.includes('Local extraction failed')));
  console.log('Knowledge UI: project-scoped search, citation reading and record navigation passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
