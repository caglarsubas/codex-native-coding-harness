'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag,text){this.tag=tag;this.text=text;this.children=[];this.isConnected=true;}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(k,v){this[k]=v;}
}
const all=root=>[root,...root.children.flatMap(c=>c instanceof Element?all(c):[])];
const find=(root,text)=>all(root).find(n=>n.text===text);
let response={status:'review_available',commandId:'original',detail:'Original request retained.'},navigation=null,late;
const calls=[],notices=[];
const proposal={document:{commandId:'original',workspaceId:'pilot',brainId:'brain-a',turnId:'turn-a',
  action:'cancel_then_reconcile',expiresAt:Date.now()/1000+300,boundary:'No Play or permission response.',
  observation:{status:'inProgress',observedAt:Date.now()/1000}},signature:'signed'};
const box={Map,Date,titles:{},csrf:'fixture',workspaceId:'pilot',workspaceGeneration:1,
  el:(tag,text)=>new Element(tag,text),button:(text,click)=>Object.assign(new Element('button',text),{click}),
  when:value=>String(value),navigateView:v=>{navigation=v;},journeyAction:v=>{navigation=v;},showNotice:(...v)=>notices.push(v),refresh:async()=>{},
  api:async(path,options)=>{calls.push([path,options]);return path.endsWith('/preview')?proposal:response;}};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/conversation.js','utf8'),box);
const tick=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
(async()=>{
  const root=new Element('section');box.turnRecoveryPanel(root,'original');await tick();
  assert.equal(calls.length,1);assert.equal(calls[0][0],'/api/turn-recovery');assert(!calls[0][1]);
  assert(!find(root,'Confirm turn recovery'),'Mount only reads saved status');
  await find(root,'Review turn recovery').click();await tick();
  assert.equal(calls[1][0],'/api/turn-recovery/preview');
  assert.equal(JSON.parse(calls[1][1].body).commandId,'original');
  assert(find(root,'Details · Exact recovery target'));
  let confirm=find(root,'Confirm turn recovery'),check=all(root).find(n=>n.tag==='input');
  assert.equal(confirm.disabled,true);await confirm.click();assert.equal(calls.length,2);
  check.checked=true;check.onchange();assert.equal(confirm.disabled,false);
  response={status:'awaiting_end',commandId:'original',delivery:'unknown',detail:'Claim retained, do not resend.'};
  await confirm.click();await tick();
  assert.equal(calls[2][0],'/api/turn-recovery/confirm');
  assert.equal(JSON.parse(calls[2][1].body).confirmed,true);
  assert(!find(root,'Confirm turn recovery'));assert(!find(root,'Review turn recovery'));
  response={status:'controller_recovered',commandId:'original',detail:'Development stays stopped.'};
  await find(root,'Check this existing turn again').click();await tick();
  assert.equal(calls[3][0],'/api/turn-recovery/reconcile');
  const count=calls.length;find(root,'Review safe phase checkpoint').click();
  assert.equal(navigation,'pause');assert.equal(calls.length,count,'Next opens existing checkpoint review, never wakes or confirms');
  response={status:'review_available',commandId:'original',detail:'Original request retained.'};
  const expiredRoot=new Element('section');box.turnRecoveryPanel(expiredRoot,'original');await tick();
  proposal.document.expiresAt=Date.now()/1000-1;
  await find(expiredRoot,'Review turn recovery').click();await tick();
  confirm=find(expiredRoot,'Confirm turn recovery');check=all(expiredRoot).find(n=>n.tag==='input');
  check.checked=true;check.onchange();assert.equal(confirm.disabled,true);
  assert(find(expiredRoot,'This review expired. Refresh recovery review above; nothing was sent.'));
  const before=calls.length;await confirm.click();assert.equal(calls.length,before,'Expired reviews never send');
  box.api=()=>new Promise(resolve=>{late=resolve;});
  const old=new Element('section');box.turnRecoveryPanel(old,'old-project');
  box.workspaceId='other';box.workspaceGeneration++;
  late({status:'review_available',commandId:'old-project',detail:'PRIVATE old project'});await tick();
  assert(!all(old).some(n=>n.text?.includes('PRIVATE')),'Late replies cannot cross project selection');
  assert(calls.every(([path])=>!path.includes('turn/start')&&!path.includes('permission/confirm')));
  console.log('Turn recovery UI: saved-only load, exact unchecked review, claim progress, no resend, expiry and project isolation passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
