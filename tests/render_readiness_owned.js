'use strict';
// Disposable browser context. Opt-in local confirmation suppresses notification.
const assert=require('node:assert/strict'),cp=require('node:child_process');
const {chromium}=require('playwright');
(async()=>{
  const confirmBrowser=process.argv.includes('--confirm-browser'),admitted=process.argv.includes('--admitted');
  const child=cp.spawn('python3',['tests/manual_readiness_owned_fixture.py',...(confirmBrowser?['--confirm-browser']:[]),...(admitted?['--admitted']:[])],{stdio:['ignore','pipe','pipe']});
  const exited=new Promise(resolve=>child.once('exit',resolve));
  let browser,stderr='';child.stderr.on('data',x=>stderr+=x);
  try{
    const fixture=await new Promise((resolve,reject)=>{
      let raw='';const timer=setTimeout(()=>reject(Error('Fixture startup timeout: '+stderr)),admitted?60000:15000);
      child.once('exit',()=>{clearTimeout(timer);reject(Error('Fixture ended: '+stderr));});
      child.stdout.on('data',x=>{raw+=x;if(raw.includes('\n')){clearTimeout(timer);resolve(JSON.parse(raw.split('\n')[0]));}});
    });
    browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
    const context=await browser.newContext(),page=await context.newPage(),errors=[],writes=[],runs=[];
    page.setDefaultTimeout(admitted?120000:30000);
    page.setDefaultNavigationTimeout(admitted?120000:30000);
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>{if(r.method()==='POST')writes.push(new URL(r.url()).pathname);});
    await page.goto(fixture.origin+'/#token='+encodeURIComponent(fixture.token));
    await page.waitForFunction(()=>document.body.textContent.includes('All projects'));
    await page.goto(fixture.origin+'/#/w/'+fixture.workspace+'/overview');
    for(const width of [1440,320]){
      await page.setViewportSize({width,height:950});
      if(width===320)await page.keyboard.press('Escape');
      const check=page.getByRole('button',{name:'Check Codex readiness',exact:true}).first();
      await check.waitFor();await check.scrollIntoViewIfNeeded();await check.click();
      const scope=page.getByText('Same project and brain · readiness only. Play remains separate.',{exact:true}).last();
      await scope.waitFor();await scope.scrollIntoViewIfNeeded();
      if(admitted)await page.getByText('First readiness for this admitted target. Existing admission, usage and predecessor holds stay unchanged.',{exact:true}).last().waitFor();
      const binding=page.getByText('Receipt binding & expiry',{exact:true}).last();await binding.click();
      await page.getByText('Valid until scope changes; no timer expiry.',{exact:true}).last().waitFor();
      const details=page.getByText('Details · exact readiness scope',{exact:true}).last();await details.click();
      try{
        await page.waitForFunction(()=>{const a=[...assistantActions.values()].at(-1);return a&&!a.confirm.disabled;});
      }catch(error){
        console.error(JSON.stringify(await page.evaluate(()=>({connected,assistantPending,
          actions:[...assistantActions.values()].map(a=>({state:assistantWorkflowState(a),status:a.status.textContent}))}))));
        throw error;
      }
      assert.equal(await page.getByRole('button',{name:'confirm readiness-owned startup',exact:true}).last().isEnabled(),true);
      assert.equal(await page.getByText('Confirmation window ended. Refresh the review here; no need to write another message.',{exact:true}).count(),0,'No expired footer on a scope-bound review');
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'Reflow at '+width);
      runs.push({width,exactReview:true,noTimerExpiry:true,noOverflow:true,confirmed:false});
      await details.click();await binding.click();
      const footer=page.getByText('Valid until scope changes; no timer expiry.',{exact:true}).last();
      await footer.scrollIntoViewIfNeeded();assert.equal(await footer.isVisible(),true);
      if(process.env.READINESS_SCREENSHOT_DIR)await page.screenshot({path:process.env.READINESS_SCREENSHOT_DIR+'/readiness-'+width+'.png',fullPage:true});
    }
    assert.deepEqual(errors,[]);
    assert.equal(writes.filter(x=>!x.endsWith('/login')&&!x.endsWith('/assistant/preview')).length,0,'No control/confirm POST');
    assert.equal(writes.filter(x=>x.endsWith('/assistant/preview')).length,2);
    if(confirmBrowser){
      const response=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/assistant/confirm')&&r.request().method()==='POST');
      await page.getByRole('button',{name:'confirm readiness-owned startup',exact:true}).last().click();
      const received=await response;
      assert.equal(received.status(),200,await received.text());
      await page.waitForFunction(()=>[...document.querySelectorAll('.chat-action')].some(x=>x.dataset.actionState==='recorded'));
      assert.equal(writes.filter(x=>x.endsWith('/assistant/confirm')).length,1);
      assert.equal(writes.filter(x=>!x.endsWith('/login')&&!x.endsWith('/assistant/preview')&&!x.endsWith('/assistant/confirm')).length,0);
    }
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({rendered:runs,admitted,previews:2,confirmations:confirmBrowser?1:0,
      localCommandOnly:confirmBrowser,nativeActions:0,exactNanosecondPins:true,errors:0}));
    await context.close();
  }catch(error){
    console.error(error.stack);throw error;
  }finally{
    if(browser)await browser.close();child.kill('SIGINT');
    await exited;
    if(child.exitCode!==0)throw Error('Fixture preservation failed: '+stderr);
  }
})().catch(e=>{console.error(e.message);process.exitCode=1;});
