"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag,text='',className=''){Object.assign(this,{tag,text,className,children:[],events:{},isConnected:true,open:false,dataset:{}});}
  append(...items){this.children.push(...items);}
  addEventListener(name,fn){this.events[name]=fn;}
  setAttribute(name,value){this[name]=value;}
}
const box={workspaceId:'alpha',el:(...args)=>new Element(...args)};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/summaries.js','utf8'),box);
const all=n=>[n,...n.children.flatMap(all)];
box.num=String;box.when=String;
const policyStop={title:'Phase stopped at a policy checkpoint',explanation:'Scope needs review.',
  issues:[{code:'scope',label:'Requested work outside reviewed scope',source:'brain_reported',nextStep:'Review exact scope.'}],
  issueCount:1,issuesTruncated:false,usageRelevant:false,registeredTasks:1,maxTasks:2,maxParallelTasks:1,
  expiresAt:12345,gapLabels:[],nextStep:'Review a new phase.',boundary:'No automatic Play.'};
let recoveryRoot=new Element('div');box.recoverySummary(recoveryRoot,policyStop);
assert(all(recoveryRoot).some(n=>n.text?.includes('Requested work outside reviewed scope')));
assert(!all(recoveryRoot).some(n=>n.text?.includes('observed tokens')||n.text?.includes('reviewed phase limit')),
  'Non-budget stops must not be presented as budget problems');
const text='Implemented a scoped search view. No merge or rollout occurred. '+
  'The following qualification report includes every original detail and preserves all recorded evidence. '.repeat(6)+'\n<script>alert(1)</script>';
let root=box.narrative(text,'Task outcome'),nodes=all(root),details=nodes.find(n=>n.tag==='details');
assert.equal(details.open,false);
assert.equal(nodes.find(n=>n.className==='narrative-full').text,text,'Exact retained prose survives');
assert(nodes.filter(n=>n.tag==='li').length<=3);
assert(nodes.some(n=>n.tag==='li'&&n.text==='No merge or rollout occurred.'));
assert(!nodes.some(n=>n.tag==='script'||n.tag==='a'),'Untrusted text cannot become markup or links');
assert.match(nodes.find(n=>n.className==='narrative-label').text,/selected excerpts/);
details.open=true;details.events.toggle();assert(all(box.narrative(text,'Task outcome')).find(n=>n.tag==='details').open);
box.workspaceId='beta';assert(!all(box.narrative(text,'Task outcome')).find(n=>n.tag==='details').open);
box.workspaceId='alpha';assert(!all(box.narrative(text+'Changed','Task outcome')).find(n=>n.tag==='details').open);
details.isConnected=false;details.open=false;details.events.toggle();assert(all(box.narrative(text,'Task outcome')).find(n=>n.tag==='details').open);
root=box.narrative('Unbroken '.repeat(80));assert(!all(root).some(n=>n.tag==='li'),'No fabricated summary for unsegmentable prose');
assert.equal(box.narrative('Not measured.').text,'Not measured.');
root=box.phaseNarrative(text,[{title:'Add search',status:'completed'},{title:'Review isolation',status:'failed'}]);
assert(all(root).some(n=>n.text==='Completed task: Add search'));
assert(!all(root).some(n=>n.text==='Completed task: Review isolation'));
assert(all(root).some(n=>n.text?.startsWith('1 of 2 tasks')));
assert(!box.narrativeHighlights('a'.repeat(40)+'. Implemented search.').some(s=>s.includes('a'.repeat(40))));
const negative='Tests passed only in the fixture; live qualification is not complete.';
assert(box.narrativeHighlights(negative).includes(negative),'Do not clip qualifications');
for(let i=0;i<110;i++){const d=all(box.narrative(text+i)).find(n=>n.tag==='details');d.open=true;d.events.toggle();}
assert.equal(vm.runInContext('narrativeDisclosures.size',box),100);
const chatNodes={'assistant-welcome':new Element('div'),'assistant-log':new Element('div')};box.$=id=>chatNodes[id];
const assistant=fs.readFileSync('web/assistant.js','utf8');
vm.runInContext(assistant.slice(assistant.indexOf('function chatTurn('),assistant.indexOf('function assistantScroll(')),box);
root=box.chatTurn('assistant',text);
assert(all(root).some(n=>n.className==='narrative-full'&&n.text===text));
assert(all(root).some(n=>n.className==='narrative-boundary'&&n.text.startsWith('AI-generated')));
for(const file of ['journey','standard','conversation','session-map','decisions','activity','workspaces','inference','assistant','app']){
  assert.match(fs.readFileSync('web/'+file+'.js','utf8'),/narrative\(|phaseNarrative\(/,file+' uses shared presentation');
}
const standard=fs.readFileSync('web/standard.js','utf8');
assert(standard.includes("el('p','Owner checkpoint: '+spec.phase.checkpoint)"),'Exact Play checkpoint stays visible, not excerpted');
assert(fs.readFileSync('web/index.html','utf8').includes('<script src="/summaries.js" defer></script>'));
console.log('Summary-first UI: whole excerpts, exact details, non-executable text, project/version isolation, bounded preferences and outcome facts passed');
