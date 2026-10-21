'use strict';
const assert=require('node:assert/strict'),cp=require('node:child_process');
const {chromium}=require('playwright');
(async()=>{
  const child=cp.spawn('python3',['-B','tests/manual_prestart_startup_fixture.py'],{stdio:['ignore','pipe','pipe']});
  const exited=new Promise(r=>child.once('exit',r));let browser,stderr='';child.stderr.on('data',x=>stderr+=x);
  try{
    const f=await new Promise((resolve,reject)=>{
      let raw='';const t=setTimeout(()=>reject(Error('Fixture timeout '+stderr)),90000);
      child.once('exit',()=>{clearTimeout(t);reject(Error('Fixture ended '+stderr));});
      child.stdout.on('data',x=>{raw+=x;if(raw.includes('\n')){clearTimeout(t);resolve(JSON.parse(raw.split('\n')[0]));}});
    });
    browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
    const context=await browser.newContext(),page=await context.newPage(),errors=[],writes=[],rendered=[];
    page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')writes.push(new URL(r.url()).pathname);});
    await page.goto(f.origin+'/#token='+encodeURIComponent(f.token));
    await page.waitForFunction(()=>document.body.textContent.includes('All projects'));
    await page.goto(f.origin+'/#/w/'+f.workspace+'/overview');
    for(const width of [1440,320]){
      await page.setViewportSize({width,height:950});
      const title=page.getByText('Pilot proposal prepared · not started',{exact:true}).first();
      await title.waitFor();await title.scrollIntoViewIfNeeded();
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
      assert.equal(await page.getByRole('button',{name:/Confirm Play|Check Codex readiness|Request a new readiness check/i}).filter({visible:true}).count(),0);
      if(process.env.STARTUP_SCREENSHOT_DIR)await page.screenshot({path:process.env.STARTUP_SCREENSHOT_DIR+'/startup-'+width+'.png',fullPage:true});
      rendered.push({width,noOverflow:true,noRetryOrPlay:true});
    }
    assert.deepEqual(errors,[]);assert.equal(writes.filter(x=>!x.endsWith('/login')).length,0);
    console.log(JSON.stringify({rendered,controlPosts:0,nativeActions:0,errors:0}));await context.close();
  }finally{
    if(browser)await browser.close();child.kill('SIGINT');await exited;
    if(child.exitCode!==0)throw Error('Preservation failed '+stderr);
  }
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
