'use strict';
// Disposable browser context and metadata-only fixture. Never confirms a control.
const assert=require('node:assert/strict'),cp=require('node:child_process');
const {chromium}=require('playwright');
(async()=>{
  const child=cp.spawn('python3',['tests/manual_readiness_owned_fixture.py'],{stdio:['ignore','pipe','pipe']});
  const exited=new Promise(resolve=>child.once('exit',resolve));
  let browser,stderr='';child.stderr.on('data',x=>stderr+=x);
  try{
    const fixture=await new Promise((resolve,reject)=>{
      let raw='';const timer=setTimeout(()=>reject(Error('Fixture startup timeout: '+stderr)),15000);
      child.once('exit',()=>{clearTimeout(timer);reject(Error('Fixture ended: '+stderr));});
      child.stdout.on('data',x=>{raw+=x;if(raw.includes('\n')){clearTimeout(timer);resolve(JSON.parse(raw.split('\n')[0]));}});
    });
    browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
    const context=await browser.newContext(),page=await context.newPage(),errors=[],writes=[],runs=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>{if(r.method()==='POST')writes.push(new URL(r.url()).pathname);});
    await page.goto(fixture.origin+'/#token='+encodeURIComponent(fixture.token));
    await page.waitForFunction(()=>document.body.textContent.includes('All projects'));
    await page.goto(fixture.origin+'/#/w/v3/overview');
    for(const width of [1440,320]){
      await page.setViewportSize({width,height:950});
      if(width===320)await page.keyboard.press('Escape');
      const check=page.getByRole('button',{name:'Check Codex readiness',exact:true}).first();
      await check.waitFor();await check.scrollIntoViewIfNeeded();await check.click();
      const scope=page.getByText('Same project and brain · readiness only. Play remains separate.',{exact:true}).last();
      await scope.waitFor();await scope.scrollIntoViewIfNeeded();
      const binding=page.getByText('Receipt binding & expiry',{exact:true}).last();await binding.click();
      await page.getByText('Valid until scope changes; no timer expiry.',{exact:true}).last().waitFor();
      const details=page.getByText('Details · exact readiness scope',{exact:true}).last();await details.click();
      assert.equal(await page.getByRole('button',{name:'confirm readiness-owned startup',exact:true}).last().isEnabled(),true);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'Reflow at '+width);
      runs.push({width,exactReview:true,noTimerExpiry:true,noOverflow:true,confirmed:false});
      if(process.env.READINESS_SCREENSHOT_DIR)await page.screenshot({path:process.env.READINESS_SCREENSHOT_DIR+'/readiness-'+width+'.png',fullPage:true});
    }
    assert.deepEqual(errors,[]);
    assert.equal(writes.filter(x=>!x.endsWith('/login')&&!x.endsWith('/assistant/preview')).length,0,'No control/confirm POST');
    assert.equal(writes.filter(x=>x.endsWith('/assistant/preview')).length,2);
    console.log(JSON.stringify({rendered:runs,previews:2,confirmations:0,nativeActions:0,errors:0}));
    await context.close();
  }finally{
    if(browser)await browser.close();child.kill('SIGINT');
    await exited;
    if(child.exitCode!==0)throw Error('Fixture preservation failed: '+stderr);
  }
})().catch(e=>{console.error(e.message);process.exitCode=1;});
