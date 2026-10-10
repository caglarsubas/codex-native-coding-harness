const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {
  constructor(tag,text='',className=''){Object.assign(this,{tag,text,className,children:[],dataset:{},value:''});}
  append(...nodes){this.children.push(...nodes);}
  prepend(...nodes){this.children.unshift(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  contains(node){return this===node||this.children.some(c=>c.contains?.(node));}
  setAttribute(k,v){this[k]=v;}
  addEventListener(k,v){this['on'+k]=v;}
}
const root=new Element('section'),requests=[],steps=[],submits=[];
const base=()=>({workspace:{id:'alpha'},meta:{revision:1,brainId:'11111111-2222-4333-8444-555555555555'},standard:{contextHash:'a'},repositories:[{policyProfile:'standard'}],commands:[]});
let response={mode:'prepare',title:'Help me continue development',proposal:{document:{id:'help-1',workflow:'phase_help',expiresAt:Date.now()/1000+300}}};
const box={state:base(),workspaceId:'alpha',csrf:'session',connected:true,assistantPending:false,assistantActions:new Map(),Date,
  $:()=>root,el:(...a)=>new Element(...a),button:(label,onclick)=>Object.assign(new Element('button',label),{onclick}),
  api:async(path,options)=>{requests.push([path,options]);return response;},
  assistantWorkflowState:a=>({locked:!!a.sending||!!a.receipt}),
  assistantWorkflowPreview:(panel,proposal)=>{const element=new Element('article');panel.append(element);const a={element,proposal,workspace:box.workspaceId,guided:true,submit:()=>{submits.push(proposal.document.id);a.sending=true;}};box.assistantActions.set(proposal.document.id,a);return a;},
  assistantRequestStep:(...a)=>steps.push(a),assistantStatus:()=>{},focusAssistantConversation:()=>{},navigateView:()=>{},
  narrative:(t)=>new Element('p',t),when:String,commandPresentation:c=>c.conversationReply?{label:'Brain replied',detail:'Reply saved'}:c.notification?.status==='unavailable'?{label:'Notification unavailable',detail:'Notifier is off'}:{label:'Sent to Codex',detail:'No receipt yet'},
  journeyDisclosure:(key,label)=>new Element('details',label),recoverySummary:()=>{}};
vm.createContext(box);vm.runInContext(fs.readFileSync('web/assistant-help.js','utf8'),box);
const run=s=>vm.runInContext(s,box),flush=()=>new Promise(resolve=>setImmediate(resolve));
const elements=n=>[n,...n.children.flatMap(elements)];
(async()=>{
  box.developmentHelpUpdate();await flush();
  assert.equal(requests.length,1);assert.equal(submits.length,0,'Loading never confirms the help request');
  assert(requests.every(([p,o])=>p==='/api/assistant/help'&&!o),'Automatic work is GET only');
  box.developmentHelpUpdate();await flush();assert.equal(requests.length,1,'Unchanged polls do not rebuild previews');
  box.developmentHelpStart();assert.deepEqual(submits,['help-1'],'One owner click submits the displayed bounded request');
  box.developmentHelpStart();assert.equal(submits.length,1,'No double click duplicate');
  run('developmentHelpViews.get("alpha").action.sending=false; developmentHelpViews.get("alpha").action.uncertain=true');
  box.state.meta.revision=2;box.developmentHelpUpdate();await flush();assert.equal(requests.length,1,'Uncertain receipt keeps original ID, not a new request');
  const command={id:'help-1',kind:'reconcile',status:'queued',createdAt:1,payload:{message:'Guided help'},notification:{status:'accepted',finishedAt:2}};
  let progress=box.developmentHelpProgress(command,box.state,3);
  assert.equal(progress.rows[1][1],'done');assert.equal(progress.rows[2][1],'waiting','Acknowledgment is not a receipt');
  command.conversationReceivedAt=4;progress=box.developmentHelpProgress(command,box.state,400);
  assert.equal(progress.attention,true);assert.match(progress.detail,/not proof of active work/);
  command.conversationReply={message:'Need exact identity',at:5};command.notification.status='unavailable';
  progress=box.developmentHelpProgress(command,box.state,400);
  assert.equal(progress.title,'Preparation reply received');assert.equal(progress.rows[1][1],'unverified','Receipt never fabricates transport success');
  const recovery={id:'recovery-1',kind:'standard_recovery',status:'processing',createdAt:6,receivedAt:7,
    payload:{messageId:'held-1'},notification:{status:'accepted',finishedAt:6}};
  box.state.commands=[recovery,{id:'held-1',conversationReply:{message:'Prepare successor',at:8}}];
  const recoveryProgress=box.developmentHelpProgress(recovery,box.state,9);
  assert.equal(recoveryProgress.rows[2][1],'done');assert.equal(recoveryProgress.rows[3][1],'done');
  assert.match(recoveryProgress.detail,/Phase Resume and Play remain separate/);
  delete recovery.receivedAt;delete box.state.commands[1].conversationReply;
  box.state.standard={run:{recovery:{id:'recovery-1',receiveBy:10}}};
  const expired=box.developmentHelpProgress(recovery,box.state,11);
  assert.equal(expired.rows[2][1],'attention');assert.match(expired.title,/window expired/);
  box.state.standard={contextHash:'a'};
  box.state.commands=[command];response={mode:'needs_input',requestId:'help-1',title:'Preparation finished',detail:'Missing evidence'};
  box.developmentHelpUpdate();await flush();
  assert(elements(root).some(e=>e.text==='Need exact identity'),'Reloaded ledger reply is shown');
  const input=elements(root).find(e=>e.id==='help-evidence'),send=elements(root).find(e=>e.text==='Prepare follow-up');
  assert.equal(send.disabled,true);input.value='codex://threads/confirmed-id';input.oninput();send.onclick();
  assert.equal(steps.at(-1)[0],'brain_message');assert.match(steps.at(-1)[1],/Follow up.*confirmed-id.*no worker retry/);
  assert.equal(submits.length,1,'Evidence prepares a preview, not an automatic send');
  run('developmentHelpViews.clear()');box.state.meta.revision=3;response={mode:'decision',key:'phase_review',title:'Review',detail:'No Play'};
  box.developmentHelpUpdate();await flush();assert.equal(submits.length,1);
  elements(root).find(e=>e.text==='Review next step').onclick();assert.equal(steps.at(-1)[0],'phase_review');
  assert.equal(submits.length,1,'Review never auto-confirms or triggers Play');
  run('developmentHelpViews.clear()');box.state.meta.revision=4;
  response={mode:'decision',key:'phase_close',title:'Recovery finished; close the expired phase',detail:'Blocked and unqualified'};
  box.developmentHelpUpdate();await flush();
  const closeout=elements(root).find(e=>e.text==='Review stopped-phase closeout');assert(closeout);
  closeout.onclick();assert.equal(steps.at(-1)[0],'phase_close');assert.equal(submits.length,1,'Closeout only prepares its own preview');
  box.state.meta.revision++;
  response={mode:'decision',key:'phase_pause_recovery',title:'Recover the saved Pause',detail:'Development stays stopped'};
  box.developmentHelpUpdate();await flush();
  const recoverPause=elements(root).find(e=>e.tag==='button'&&e.text==='Recover the saved Pause');assert(recoverPause);
  recoverPause.onclick();assert.equal(steps.at(-1)[0],'phase_pause_recovery');assert.equal(submits.length,1,'Recovery does not auto-confirm from Help');
  box.state.meta.revision++;
  response={mode:'decision',key:'phase_pause_recovery',title:'Review replacement checkpoint recovery',detail:'No third attempt'};
  box.developmentHelpUpdate();await flush();
  const replacement=elements(root).find(e=>e.tag==='button'&&e.text==='Review replacement checkpoint recovery');assert(replacement);
  replacement.onclick();assert.equal(steps.at(-1)[0],'phase_pause_recovery');assert.equal(submits.length,1,'Replacement also prepares only, never retries automatically');
  const pauseRecovery={id:'recover-pause',kind:'standard_pause_recovery',status:'queued',createdAt:1,notification:{status:'accepted',finishedAt:2}};
  box.state.standard.run={pauseRecovery:{id:'recover-pause',receiveBy:500}};
  progress=box.developmentHelpProgress(pauseRecovery,box.state,3);
  assert.equal(progress.rows[1][1],'done');assert.equal(progress.rows[2][1],'waiting');assert.equal(progress.rows[3][1],'waiting');
  pauseRecovery.receivedAt=4;pauseRecovery.status='processing';progress=box.developmentHelpProgress(pauseRecovery,box.state,5);
  assert.equal(progress.rows[2][1],'done');assert.equal(progress.rows[3][1],'waiting','Pause receipt is not a checkpoint');
  pauseRecovery.checkpointHash='checkpoint';pauseRecovery.status='completed';progress=box.developmentHelpProgress(pauseRecovery,box.state,6);
  assert.equal(progress.rows[3][1],'done');
  const receiptRecovery={...pauseRecovery,id:'receipt',kind:'standard_pause_receipt_recovery'};
  box.state.standard.run.pauseReceiptRecovery={id:'receipt',receiveBy:500};
  progress=box.developmentHelpProgress(receiptRecovery,box.state,6);
  assert.match(progress.detail,/historical effect uncertainty.*not pilot acceptance/);
  box.state.meta.revision++;response={mode:'decision',key:'phase_pause_receipt_recovery',title:'Recover the Pause receipt',detail:'No replay'};
  box.developmentHelpUpdate();await flush();
  elements(root).find(e=>e.tag==='button'&&e.text==='Recover the Pause receipt').onclick();
  assert.equal(steps.at(-1)[0],'phase_pause_receipt_recovery');assert.equal(submits.length,1);
  // A response arriving after project selection changes cannot cross projects.
  let resolve;box.api=()=>new Promise(r=>resolve=r);box.state.meta.revision++;box.developmentHelpUpdate();
  box.workspaceId='beta';box.state={...base(),workspace:{id:'beta'}};
  resolve({mode:'blocked',title:'FOREIGN RESULT'});await flush();assert(!elements(root).some(e=>e.text==='FOREIGN RESULT'));
  box.state.repositories=[{policyProfile:'harness'}];assert.equal(box.developmentHelpUpdate(),false);
  assert(!fs.readFileSync('web/assistant-help.js','utf8').includes('innerHTML'));
  console.log('Guided help: read-only preparation, one-click intent, progress, replay, isolation, evidence follow-up and separate review passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
