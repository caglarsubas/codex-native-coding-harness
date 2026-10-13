"use strict";
// Render against manual_session_map_fixture.py only. No live ledger or controls.
// Usage: NODE_PATH=/path/to/bundled/node_modules node tests/manual_inspector_resize.cjs ORIGIN OUTPUT_DIR
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const origin=process.argv[2],output=process.argv[3];
assert(/^http:\/\/127\.0\.0\.1:\d+$/.test(origin));assert(output&&fs.statSync(output).isDirectory());
const checks=[],errors=[],blocked=[];
async function main(){
  assert(fs.existsSync(chromium.executablePath()),'Use an installed browser; no downloads');
  const browser=await chromium.launch({headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  let auth;
  try{
    const login=await context.request.post(origin+'/api/login',{headers:{Origin:origin},data:{token:'disposable-session-map-preview',rememberDays:0}});
    assert.equal(login.status(),200);auth=await login.json();
    await context.route('**/*',route=>{
      const request=route.request(),url=new URL(request.url());
      if(url.origin===origin&&['GET','HEAD'].includes(request.method()))return route.continue();
      blocked.push({method:request.method(),path:url.pathname});return route.abort();
    });
    const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
    await page.goto(origin+'/#/w/map-preview/overview');
    const brain=page.locator('.session-node[data-node="brain"]'),inspector=page.locator('#session-inspector');
    await brain.waitFor();await brain.focus();await brain.press('Enter');
    const composer=page.locator('#brain-message');await composer.waitFor();
    await composer.fill('An unsent fixture draft — do not send.');
    await composer.evaluate(node=>{node.setSelectionRange(4,12);window.qaComposer=node;});
    async function intact(){
      assert.equal(await composer.evaluate(node=>node===window.qaComposer),true);
      assert.equal(await composer.inputValue(),'An unsent fixture draft — do not send.');
      assert.deepEqual(await composer.evaluate(node=>[node.selectionStart,node.selectionEnd]),[4,12]);
      assert.equal(await composer.evaluate(node=>node===document.activeElement),true);
    }
    assert.equal(await inspector.getAttribute('role'),'complementary');await intact();
    for(const width of [320,1440,375,1440,799,800,320]){
      await page.setViewportSize({width,height:780});
      await page.waitForFunction(w=>document.getElementById('session-inspector').getAttribute('role')===(w<=799?'dialog':'complementary'),width);
      assert.equal(await inspector.getAttribute('aria-modal'),String(width<=799));await intact();
      assert.equal(await page.locator('.onepage-toolbar').evaluate(node=>node.inert),width<=799);
      const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
      assert.equal(overflow,false,'No horizontal document overflow at '+width);
      checks.push({width,role:await inspector.getAttribute('role'),draftCaretFocusPreserved:true,reflow:true});
    }
    const focusable=inspector.locator('button:enabled,a[href],input:enabled,textarea:enabled,select:enabled,summary,[tabindex="0"]');
    const visible=[];for(let i=0;i<await focusable.count();i++)if(await focusable.nth(i).isVisible())visible.push(focusable.nth(i));
    await visible.at(-1).focus();await page.keyboard.press('Tab');
    assert.equal(await visible[0].evaluate(node=>node===document.activeElement),true);
    await page.keyboard.press('Shift+Tab');assert.equal(await visible.at(-1).evaluate(node=>node===document.activeElement),true);
    await page.screenshot({path:path.join(output,'inspector-mobile.png'),fullPage:true});
    await page.keyboard.press('Escape');assert.equal(await inspector.getAttribute('aria-modal'),'false');
    assert.equal(await page.locator('.onepage-toolbar').evaluate(node=>node.inert),false);
    assert.equal(await brain.evaluate(node=>node===document.activeElement),true);
    await page.setViewportSize({width:1440,height:1000});await page.setViewportSize({width:320,height:780});
    assert.equal(await inspector.getAttribute('aria-modal'),'false');assert.equal(await brain.evaluate(node=>node===document.activeElement),true);
    await brain.press('Enter');await composer.waitFor();
    const close=inspector.locator('.session-inspector-close');await close.focus();
    await page.setViewportSize({width:1440,height:1000});
    await page.waitForFunction(()=>document.activeElement?.getClientRects().length>0);
    assert.equal(await close.evaluate(node=>node===document.activeElement),false,'Hidden close control relinquishes focus');
    await composer.focus();await composer.evaluate(node=>{node.setSelectionRange(4,12);window.qaComposer=node;});
    await page.waitForTimeout(6000);await intact();
    await page.screenshot({path:path.join(output,'inspector-desktop.png'),fullPage:true});
    checks.push({keyboardLoop:true,escapeRestoresGraph:true,closedResizeNoFocusSteal:true,hiddenCloseFocusCorrected:true,pollPreservesDraft:true});
    await page.goto(origin+'/#/w/empty-preview/overview');await page.locator('.session-node[data-node="brain"]').waitFor();
    await page.setViewportSize({width:320,height:780});
    assert.equal(await page.locator('.onepage-toolbar').evaluate(node=>node.inert),false,'Old workspace cannot keep background inert');
    await page.locator('.session-node[data-node="brain"]').click();await page.locator('#brain-message').waitFor();
    assert.equal(await page.locator('#session-inspector').getAttribute('role'),'dialog');
    await page.keyboard.press('Escape');
    checks.push({projectSwitch:true,initialMobileDialog:true,backgroundRestored:true});
    // Synthetic frontend projection only: no real run, policy or authority is
    // changed. Inspecting the policy pane must remain navigation/GET-only.
    await page.setViewportSize({width:1440,height:1000});
    await page.evaluate(()=>{
      state.repositories=[{id:'fixture',policyProfile:'standard',mergePolicy:'manual'}];
      state.standard={available:true,boundary:'Synthetic policy fixture; not a native qualification.',contextHash:'fixture',
        blockers:['Native Code Mode-off policy is unverified'],nativePolicyVerification:{codeMode:'unverified',policyVerified:false,
          configurationMatches:true,resumeAcknowledged:true,sandbox:'reported_matching',approvalPolicy:'reported_matching',
          approvalsReviewer:'reported_matching',observedAt:1,boundary:'Saved metadata; terminal safety remains unknown.'},
        run:{id:'fixture-run',status:'paused',phaseId:'fixture-policy-gap',brainId:state.meta.brainId,expiresAt:Date.now()/1000+3600,
          tasks:[],brainAllowance:6000000,brainUsageCoverage:'not_observed',limits:{tokenBudget:20000000,maxTasks:3,maxParallelTasks:1,
          checkpointReserveTokens:2000000,mergeMode:'manual'}}};
      state.mission=null;state.recovery=null;sessionSelectRoute('overview');render();
    });
    await page.getByRole('button',{name:'Inspect policy evidence',exact:true}).click();
    await page.getByText('Code Mode is not verified off',{exact:true}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Review Resume',exact:true}).count(),0);
    await page.screenshot({path:path.join(output,'policy-gap-desktop.png'),fullPage:true});
    checks.push({syntheticPolicyBlockerVisible:true,noRecoveryOrResumeInvitation:true,policyInspectionNavigationOnly:true});
    assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);
    const report={checks,errors,blocked,sourceUiOnly:true,nativeActions:0,pilotAccepted:false};
    fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx',mode:0o600});
    console.log(JSON.stringify(report));
  }finally{
    if(auth?.csrf)await context.request.post(origin+'/api/logout',{headers:{Origin:origin,'X-CSRF-Token':auth.csrf},data:{}});
    await context.close();await browser.close();
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
