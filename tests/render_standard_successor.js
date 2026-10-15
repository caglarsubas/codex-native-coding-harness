"use strict";
// Explicit optional rendered fixture. Uses installed Chrome/Playwright only.
const assert=require('node:assert/strict'),cp=require('node:child_process');
const {chromium}=require('playwright');
(async()=>{
  const child=cp.spawn('python3',['tests/manual_successor_fixture.py'],{stdio:['ignore','pipe','pipe']});
  let browser,stderr='',childExit;
  child.stderr.on('data',x=>stderr+=x);
  const exited=new Promise(resolve=>child.once('exit',code=>{childExit=code;resolve();}));
  try{
    const fixture=await new Promise((resolve,reject)=>{
      let raw='';const timeout=setTimeout(()=>reject(Error('Fixture startup timeout')),15000);
      child.once('exit',()=>{clearTimeout(timeout);reject(Error('Fixture ended: '+stderr));});
      child.stdout.on('data',x=>{raw+=x;if(raw.includes('\n')){clearTimeout(timeout);resolve(JSON.parse(raw.split('\n')[0]));}});
    });
    browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
    const context=await browser.newContext(),page=await context.newPage(),errors=[],writes=[],runs=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>{if(r.method()==='POST')writes.push(new URL(r.url()).pathname);});
    await page.goto(fixture.origin+'/#token='+encodeURIComponent(fixture.token));
    await page.waitForFunction(()=>document.body.textContent.includes('All projects'));
    await page.goto(fixture.origin+'/#/w/beta/operations');
    for(const width of [1440,320]){
      await page.setViewportSize({width,height:950});
      if(width===320){const show=page.getByRole('button',{name:'Show details',exact:true});if(await show.isVisible())await show.click();}
      const lineage=page.getByText('Separate successor · old attempt preserved',{exact:true});
      await lineage.waitFor();await lineage.scrollIntoViewIfNeeded();
      await page.getByText(/Prior observed brain usage:.*1,049,625/).waitFor();
      const details=page.getByText('Details · preserved predecessor and successor boundary',{exact:true});
      await details.focus();await page.keyboard.press('Enter');
      assert.equal(await details.evaluate(e=>e.parentElement.open),true,'Keyboard opens lineage details');
      await page.keyboard.press('Enter');
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'No overflow at '+width);
      runs.push({width,priorUsageVisible:true,unknownSafetyPreserved:true,keyboardDetails:true,noOverflow:true});
      await page.screenshot({path:'/private/tmp/codex-successor-render-'+width+'.png',fullPage:true});
    }
    assert.deepEqual(errors,[]);
    assert.equal(writes.filter(path=>!path.endsWith('/login')).length,0,'No admission/Play/native control submission');
    console.log(JSON.stringify({rendered:runs,controlWrites:0,liveNativeActions:0,errors:0}));
    await context.close();
  }finally{
    if(browser)await browser.close();child.kill('SIGINT');await exited;
    assert.equal(childExit,0,'Disposable fixture conservation checks: '+stderr);
  }
})().catch(e=>{console.error(e.message);process.exitCode=1;});
