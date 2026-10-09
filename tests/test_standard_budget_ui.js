"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag,text=''){Object.assign(this,{tag,text,children:[],disabled:false});}
  append(...items){this.children.push(...items);}
  setAttribute(k,v){this[k]=v;}
}
const calls=[],notices=[];
const budget={available:true,contextHash:'budget-context',currentAllowance:10000,maximumAllowance:89999,suggestedAllowance:30000};
const run={id:'run',status:'paused',limits:{tokenBudget:100000,checkpointReserveTokens:10000},expiresAt:Date.now()/1000+3600};
let proposal;
const box={Map,Set,JSON,Math,String,Number,Date,setTimeout,workspaceId:'alpha',state:{standard:{brainBudget:budget,run}},busy:false,connected:true,csrf:'session',
  document:{getElementById:()=>null},el:(tag,text)=>new Element(tag,text),section:(title,detail)=>new Element('h2',title+' '+detail),
  button:(text,click)=>Object.assign(new Element('button',text),{click}),num:String,when:String,render(){},refresh:async()=>{},updateWorkspaceSelector(){},
  showNotice:text=>notices.push(text),api:async(path,opts)=>{
    const body=JSON.parse(opts.body);calls.push({path,body});
    if(path.endsWith('preview')){proposal={preview:{...body,previousAllowance:10000,recordedBrainTokens:null,recordedCoverage:'unknown',boundary:'Phase stays paused',expiresAt:Date.now()/1000+300},signature:'fixture'};return proposal;}
    return {id:'review',result:'Phase remains paused'};
  }};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/standard.js','utf8'),box);
const all=n=>[n,...n.children.flatMap(all)];
const render=()=>{const root=new Element('root');box.brainBudgetPanel(root,box.state.standard,run);return all(root);};
(async()=>{
  let nodes=render();assert.equal(calls.length,0,'Render never prepares or confirms');
  assert.ok(nodes.some(n=>String(n.text).includes('unchanged')||String(n.text).includes('does not increase')));
  await nodes.find(n=>n.text==='Review brain allowance').click();assert.equal(calls.length,1);
  assert.equal(calls[0].body.brainAllowance,30000);
  nodes=render();let confirm=nodes.find(n=>n.text==='Confirm brain allowance'),check=nodes.find(n=>n.type==='checkbox');
  assert.equal(confirm.disabled,true);assert.ok(nodes.some(n=>String(n.text).includes('Unknown')));
  check.checked=true;check.onchange();assert.equal(confirm.disabled,false);
  box.workspaceId='beta';await confirm.click();assert.equal(calls.length,1,'Detached project cannot submit');
  assert.ok(!render().some(n=>n.text==='Confirm brain allowance'));box.workspaceId='alpha';
  box.connected=false;await confirm.click();assert.equal(calls.length,1);box.connected=true;
  box.state.standard.brainBudget={...budget,contextHash:'changed'};await confirm.click();assert.equal(calls.length,1);box.state.standard.brainBudget=budget;
  nodes=render();confirm=nodes.find(n=>n.text==='Confirm brain allowance');check=nodes.find(n=>n.type==='checkbox');check.checked=true;check.onchange();
  const input=nodes.find(n=>n.type==='number');input.value='35000';input.oninput();assert.equal(confirm.disabled,true);await confirm.click();assert.equal(calls.length,1,'Editing requires a freshly signed review');
  nodes=render();await nodes.find(n=>n.text==='Review brain allowance').click();assert.equal(calls.at(-1).body.brainAllowance,35000);
  proposal.preview.expiresAt=Date.now()/1000-1;assert.ok(!render().some(n=>n.text==='Confirm brain allowance'),'Expired preview is not confirmable');
  await render().find(n=>n.text==='Review brain allowance').click();nodes=render();confirm=nodes.find(n=>n.text==='Confirm brain allowance');check=nodes.find(n=>n.type==='checkbox');
  check.checked=true;check.onchange();await confirm.click();assert.equal(calls.at(-1).path,'/api/standard/budget/confirm');
  assert.equal(calls.at(-1).body.confirmed,true);assert.equal(run.status,'paused');
  assert.ok(!calls.some(c=>c.path.includes('resume')||c.path.includes('usage-refresh')),'Confirmation never refreshes usage or Resumes implicitly');
  assert.ok(!render().some(n=>n.text==='Confirm brain allowance'));
  box.state.standard.brainBudget={...budget,available:false,reason:'Native delivery unresolved'};
  assert.ok(render().some(n=>n.text==='Native delivery unresolved'));assert.ok(!render().some(n=>n.text==='Review brain allowance'));
  console.log('Brain budget UI: exact review, editing, expiry, project isolation and no implicit Resume passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
