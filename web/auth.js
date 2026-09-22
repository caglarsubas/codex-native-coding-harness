"use strict";
let browserSession=null, dashboardPoll=null, authBusy=false;

function browserSignedOut(message='This browser is signed out. Open the current private dashboard link to sign in again.'){
  clearInterval(dashboardPoll);dashboardPoll=null;
  connected=false;state=null;csrf=null;browserSession=null;workspaceGeneration++;
  $('browser-access').hidden=true;$('browser-access-panel').hidden=true;
  $('mode').textContent='Sign-in required';$('connection').textContent='Authentication required';
  $('pause').disabled=true;$('reconcile').disabled=true;
  $('workspace-picker').hidden=true;
  $('content').replaceChildren(empty('Connect this browser',message),el('p','After signing in, open Browser access and choose Remember this browser. Your normal workspace bookmark will then work through server restarts.','muted'));
  // A signed-out tab must not continue displaying private assistant content.
  $('assistant-log').querySelectorAll('.chat-turn').forEach(node=>node.remove());
  $('assistant-context-preview').textContent='';$('assistant-question').value='';
  if(typeof workspaceTabs!=='undefined')workspaceTabs.clear();
  if(typeof assistantHistory!=='undefined'){assistantHistory=[];assistantActions.clear();}
  assistantConnectionChanged();
}

async function changeBrowserAccess(path,body){
  if(authBusy||workspaceLocked()){showNotice('Wait for the current request before changing browser access.',true);return;}
  authBusy=true;
  try{
    // Use the global browser CSRF, not the selected workspace's scoped token.
    const session=await api('/api/session',{global:true});
    await api(path,{global:true,method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf},body:JSON.stringify(body)});
    // Rotation invalidates previews bound to the old session. Reload clears them.
    location.reload();
  }catch(error){showNotice(error.message,true);}
  finally{authBusy=false;}
}

function renderBrowserAccess(){
  const root=$('browser-access-panel');root.replaceChildren();
  if(!browserSession)return;
  const remembered=browserSession.remembered;
  root.append(el('h2','Browser access'),el('p',remembered
    ?`Remembered on this Mac until ${when(browserSession.expiresAt)}. Normal server restarts keep you signed in.`
    :`Temporary sign-in until ${when(browserSession.expiresAt)} or the next server restart.`));
  const form=el('form',null,'browser-access-form'),label=el('label','Remember this browser for '),select=el('select');
  select.setAttribute('aria-label','Remember this browser duration');
  for(const days of [7,30,90]){const option=el('option',`${days} days`);option.value=String(days);select.append(option);}
  select.value=String(browserSession.rememberDays||30);label.append(select);
  const remember=el('button',remembered?'Renew remembered sign-in':'Remember this browser','primary');remember.type='submit';
  form.append(label,remember);form.onsubmit=event=>{event.preventDefault();changeBrowserAccess('/api/session/remember',{rememberDays:Number(select.value)});};
  root.append(form,el('p','Use only on a trusted browser. This grants dashboard access across its workspaces, not permission to start development. Cookies cleared, expiry or revocation require pairing again.','muted'));
  const actions=el('div',null,'browser-access-actions');
  if(remembered)actions.append(button('Use temporary sign-in',()=>changeBrowserAccess('/api/session/remember',{rememberDays:0})));
  actions.append(button('Sign out',()=>changeBrowserAccess('/api/logout',{})));root.append(actions);
  const details=el('details'),confirmLabel=el('label'),confirmation=el('input'),revoke=button('Sign out all browsers',()=>{if(confirmation.checked)changeBrowserAccess('/api/sessions/revoke',{confirmed:true});});
  confirmation.type='checkbox';confirmation.checked=false;revoke.disabled=true;
  confirmation.onchange=()=>{revoke.disabled=!confirmation.checked;};
  confirmLabel.append(confirmation,el('span','I understand every browser, including this one, will need the private link again.'));
  details.append(el('summary','Revoke all browser access'),confirmLabel,revoke);
  root.append(details,el('p','Sign-out does not stop brains or workers. Use workspace Pause to stop development safely.','muted'));
}

async function start(){
  try{
    const token=new URLSearchParams(location.hash.slice(1)).get('token');
    if(token){
      history.replaceState(null,'',location.pathname+location.search);
      browserSession=await api('/api/login',{global:true,method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})});
    }else browserSession=await api('/api/session',{global:true});
    csrf=browserSession.csrf;
    $('browser-access').hidden=false;
    $('browser-access').textContent=browserSession.remembered?'Browser access':'Remember this browser';
    renderBrowserAccess();
    $('browser-access').onclick=async()=>{
      const root=$('browser-access-panel');
      if(root.hidden){
        try{browserSession=await api('/api/session',{global:true});renderBrowserAccess();}catch(error){showNotice(error.message,true);return;}
      }
      root.hidden=!root.hidden;$('browser-access').setAttribute('aria-expanded',String(!root.hidden));
    };
    await initializeWorkspaces();await refresh();applyDashboardRoute(false);
    if(connected)dashboardPoll=setInterval(()=>{const editing=document.activeElement?.matches('input,select,textarea');if(!busy&&!authBusy&&!selected&&!editing&&document.visibilityState==='visible')refresh();},5000);
  }catch(error){
    if(error.authRequired)browserSignedOut();
    showNotice(error.message,true);$('pause').disabled=true;$('reconcile').disabled=true;
  }
}
document.addEventListener('DOMContentLoaded',start,{once:true});
