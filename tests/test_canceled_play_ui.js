"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag,text='',className=''){Object.assign(this,{tag,text,className,children:[]});}
  append(...items){this.children.push(...items);}
  setAttribute(name,value){this[name]=value;}
}
const calls=[],box={Map,titles:{},state:{},el:(...a)=>new Element(...a),
  callout:(a,b)=>new Element('aside',a+' '+b),button:(label,fn)=>Object.assign(new Element('button',label),{click:fn}),
  num:String,when:String,navigateView:section=>calls.push(section)};
vm.createContext(box);
for(const file of ['summaries','journey','standard','decisions'])vm.runInContext(fs.readFileSync('web/'+file+'.js','utf8'),box);
const disposition={status:'disposed_unqualified',commandId:'old-play',writesBlocked:true,brainReceipt:'missing',
  continuation:{executionAvailable:false,blockers:[{code:'no_reload_owned_subscription_unavailable',
    detail:'The owned subscription requires thread/resume. No reload or substitute send is permitted.'}]}};
const snapshot={workspace:{id:'v3',name:'Fixture'},meta:{paused:true},commands:[{id:'old-play',kind:'standard_play',status:'queued',payload:{runId:'run'}}],
  canceledPlayDisposition:disposition,repositories:[{policyProfile:'standard'}],
  standard:{run:{id:'run',status:'running',brainUsageCoverage:'not_observed'},canceledPlayDisposition:disposition}};
box.state=snapshot;
const journey=box.roadmapJourneyState(snapshot,true,1);
assert.equal(journey.action,'operations');assert.equal(journey.requiresOperator,true);
assert.equal(journey.canPause,undefined);assert.match(journey.title,/Canceled Play/);
assert.match(journey.detail,/No more cancellation is needed/);
assert.match(box.commandPresentation(snapshot.commands[0]).label,/unqualified/);
assert.match(box.commandPresentation(snapshot.commands[0]).detail,/missing brain receipt/);
const root=new Element('main');box.standardPanel(root,'operations');
const all=node=>[node,...node.children.flatMap(all)],text=all(root).map(n=>n.text).join('\n');
assert.match(text,/Cancel is resolved/);assert.match(text,/Continuation requirements/);
assert.match(text,/terminal safety remain unknown/);assert.match(text,/No reload or substitute send/);
assert.equal(all(root).filter(n=>n.tag==='button').length,0,'No confirmation, wake, Play or Resume button');
assert.equal(calls.length,0,'Rendering does not submit a request');
snapshot.standard.canceledPlayDisposition={...disposition,status:'incomplete_or_changed'};
const broken=new Element('main');box.standardPanel(broken,'operations');
assert.match(all(broken).map(n=>n.text).join(' '),/record unavailable/);
console.log('canceled Play: unqualified history, no repeated cancel, no control button, continuation blocked');
