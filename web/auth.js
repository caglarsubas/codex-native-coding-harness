"use strict";
let browserSession=null, dashboardPoll=null, authBusy=false, authMode=null;

function browserSignedOut(message='Open the current private dashboard link to sign in.'){
  clearInterval(dashboardPoll);dashboardPoll=null;
  connected=false;state=null;csrf=null;browserSession=null;workspaceGeneration++;
  resetDashboardNavigation();
  $('browser-access').hidden=true;$('browser-access-panel').hidden=true;
  $('mode').textContent='Sign-in required';$('connection').textContent='Authentication required';
  $('pause').disabled=true;$('reconcile').disabled=true;
  $('workspace-picker').hidden=true;
  $('title').textContent='Sign in';$('subtitle').textContent='Your local project, ready when you are.';
  if(authMode==='account')renderAccountSignIn();
  else $('content').replaceChildren(empty('Connect this browser',message),el('p','After signing in, open Browser access and choose Remember this browser.','muted'));
  // A signed-out tab must not continue displaying private assistant content.
  $('assistant-log').querySelectorAll('.chat-turn').forEach(node=>node.remove());
  $('assistant-context-preview').textContent='';$('assistant-question').value='';
  if(typeof workspaceTabs!=='undefined')workspaceTabs.clear();
  if(typeof workspaceList!=='undefined'){workspaceList=[];projectCatalog=null;workspaceId=null;}
  if(typeof brainDrafts!=='undefined')brainDrafts.clear();
  if(typeof assistantHistory!=='undefined'){assistantHistory=[];assistantActions.clear();}
  assistantConnectionChanged();
}

function renderAccountSignIn(){
  const form=el('form',null,'account-signin');form.setAttribute('aria-label','Local account sign-in');
  const username=el('input'),password=el('input'),remember=el('input');
  username.id='signin-username';username.name='username';username.type='text';username.autocomplete='username';username.required=true;username.maxLength=254;
  username.setAttribute('autocapitalize','none');username.setAttribute('spellcheck','false');
  password.id='signin-password';password.name='password';password.type='password';password.autocomplete='current-password';password.required=true;password.maxLength=1024;
  const nameLabel=el('label','Account name'),passwordLabel=el('label','Password');
  nameLabel.setAttribute('for',username.id);passwordLabel.setAttribute('for',password.id);
  const nameField=el('div',null,'signin-field'),passwordField=el('div',null,'signin-field');
  nameField.append(nameLabel,username);passwordField.append(passwordLabel,password);
  remember.type='checkbox';remember.checked=false;remember.id='signin-remember';
  const rememberLabel=el('label',null,'signin-remember');rememberLabel.append(remember,el('span','Remember this browser for 30 days'));
  const error=el('p',null,'signin-error');error.id='signin-error';error.setAttribute('role','alert');error.hidden=true;
  password.setAttribute('aria-describedby',error.id);
  const submit=el('button','Sign in','primary');submit.type='submit';
  form.append(el('p','Sign in to manage your projects and talk to their brains.','muted'),nameField,passwordField,rememberLabel,error,submit,
    el('p','This account is local to this Mac. Signing in does not start development.','muted'));
  form.onsubmit=async event=>{
    event.preventDefault();if(authBusy)return;
    authBusy=true;submit.disabled=true;submit.textContent='Signing in…';error.hidden=true;
    try{
      await api('/api/login',{global:true,method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:username.value,password:password.value,rememberDays:remember.checked?30:0})});
      password.value='';$('notice').hidden=true;await start();
    }catch(failure){error.textContent=failure.message;error.hidden=false;}
    finally{password.value='';authBusy=false;submit.disabled=false;submit.textContent='Sign in';}
  };
  $('content').replaceChildren(form);
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
  root.append(form,el('p','Use only on a trusted browser. This grants dashboard access across its workspaces, not permission to start development. Cookies cleared, expiry or revocation require signing in again.','muted'));
  const actions=el('div',null,'browser-access-actions');
  if(remembered)actions.append(button('Use temporary sign-in',()=>changeBrowserAccess('/api/session/remember',{rememberDays:0})));
  actions.append(button('Sign out',()=>changeBrowserAccess('/api/logout',{})));root.append(actions);
  const details=el('details'),confirmLabel=el('label'),confirmation=el('input'),revoke=button('Sign out all browsers',()=>{if(confirmation.checked)changeBrowserAccess('/api/sessions/revoke',{confirmed:true});});
  confirmation.type='checkbox';confirmation.checked=false;revoke.disabled=true;
  confirmation.onchange=()=>{revoke.disabled=!confirmation.checked;};
  confirmLabel.append(confirmation,el('span','I understand every browser, including this one, will need to sign in again.'));
  details.append(el('summary','Revoke all browser access'),confirmLabel,revoke);
  root.append(details,el('p','Sign-out does not stop brains or workers. Use workspace Pause to stop development safely.','muted'));
}

async function start(){
  clearInterval(dashboardPoll);dashboardPoll=null;
  try{
    authMode=(await api('/api/auth/options',{global:true})).mode;
    const token=new URLSearchParams(location.hash.slice(1)).get('token');
    if(token){
      history.replaceState(null,'',location.pathname+location.search);
      browserSession=authMode==='account'?await api('/api/session',{global:true}):await api('/api/login',{global:true,method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})});
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
    await initializeWorkspaces();await refresh();await applyDashboardRoute(false);
    if(connected||unconfiguredProject())initializeDashboardNavigation();
    if(connected||unconfiguredProject())dashboardPoll=setInterval(()=>{const editing=document.activeElement?.matches('input,select,textarea');if(!busy&&!authBusy&&!selected&&!editing&&document.visibilityState==='visible')refresh();},5000);
  }catch(error){
    if(error.authRequired){browserSignedOut();$('notice').hidden=true;return;}
    showNotice(error.message,true);$('pause').disabled=true;$('reconcile').disabled=true;
  }
}
document.addEventListener('DOMContentLoaded',start,{once:true});
