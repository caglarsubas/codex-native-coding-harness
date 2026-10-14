"use strict";
// Explicit optional rendered fixture, using already installed Chrome/Playwright.
// No live project, browser profile, model service or native host is touched.
const assert=require('node:assert/strict'),cp=require('node:child_process');
const {chromium}=require('playwright');
(async()=>{
  const child=cp.spawn('python3',['tests/manual_policy_evidence_fixture.py'],{stdio:['ignore','pipe','pipe']});
  let browser,stderr='';child.stderr.on('data',x=>stderr+=x);
  try{
    const fixture=await new Promise((resolve,reject)=>{
      let raw='';const timeout=setTimeout(()=>reject(Error('Fixture startup timeout')),10000);
      child.once('exit',()=>{clearTimeout(timeout);reject(Error('Fixture ended: '+stderr));});
      child.stdout.on('data',x=>{raw+=x;if(raw.includes('\n')){clearTimeout(timeout);resolve(JSON.parse(raw.split('\n')[0]));}});
    });
    browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
    const context=await browser.newContext(),page=await context.newPage(),errors=[],writes=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>{if(r.method()==='POST')writes.push({url:new URL(r.url()).pathname,body:r.postDataJSON()});});
    await page.goto(fixture.origin+'/#token='+encodeURIComponent(fixture.token));
    await page.waitForFunction(()=>document.body.textContent.includes('All projects'));
    await page.goto(fixture.origin+'/#/w/alpha/operations');
    const check=page.getByRole('button',{name:'Check native policy evidence',exact:true});
    await check.waitFor();
    let runs=[];
    for(const width of [1440,320]){
      await page.setViewportSize({width,height:950});
      if(width===320){const show=page.getByRole('button',{name:'Show details',exact:true});if(await show.isVisible())await show.click();}
      await check.scrollIntoViewIfNeeded();
      assert.equal(await check.isEnabled(),true);
      await check.click();
      await page.waitForTimeout(250);
      await page.getByText('Unloaded native policy remains unknown. No Resume was sent.',{exact:true}).first().waitFor();
      assert.equal(await page.getByRole('button',{name:'Review Resume',exact:true}).count(),0);
      const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
      assert.equal(overflow,false,'No horizontal overflow at '+width);
      runs.push({width,policyCheckVisible:true,unknownPreserved:true,noResume:true,noOverflow:true});
    }
    const policyWrites=writes.filter(r=>r.url.endsWith('/native-policy/check'));
    assert.equal(policyWrites.length,2);for(const r of policyWrites)assert.deepEqual(r.body,{});
    assert.equal(writes.filter(r=>!r.url.endsWith('/native-policy/check')&&!r.url.endsWith('/login')).length,0,'No phase/control submission');
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({rendered:runs,policyChecks:2,phaseControls:0,errors:0,liveNativeActions:0}));
    await context.close();
  }finally{
    if(browser)await browser.close();
    child.kill('SIGINT');
    await new Promise(resolve=>child.once('exit',resolve));
  }
})().catch(e=>{console.error(e.message);process.exitCode=1;});
