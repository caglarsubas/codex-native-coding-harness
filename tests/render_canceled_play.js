"use strict";
// Explicit disposable browser qualification. No live dashboard or native host.
const assert=require('node:assert/strict'),cp=require('node:child_process'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
(async()=>{
  const output=process.argv[2];assert(output&&path.isAbsolute(output)&&fs.statSync(output).isDirectory());
  const child=cp.spawn('python3',['tests/manual_canceled_play_fixture.py'],{stdio:['ignore','pipe','pipe']});
  let browser,stderr='',childExit;
  child.stderr.on('data',x=>stderr+=x);
  const exited=new Promise(resolve=>child.once('exit',code=>{childExit=code;resolve();}));
  try{
    const fixture=await new Promise((resolve,reject)=>{
      let raw='';const timer=setTimeout(()=>reject(Error('Fixture startup timeout')),15000);
      child.once('exit',()=>{clearTimeout(timer);reject(Error('Fixture ended: '+stderr));});
      child.stdout.on('data',x=>{raw+=x;if(raw.includes('\n')){clearTimeout(timer);resolve(JSON.parse(raw.split('\n')[0]));}});
    });
    browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
    const context=await browser.newContext({reducedMotion:'reduce'}),page=await context.newPage(),errors=[],posts=[],foreign=[],runs=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname);
      if(new URL(r.url()).origin!==fixture.origin)foreign.push(r.url());});
    await page.goto(fixture.origin+'/#token='+encodeURIComponent(fixture.token));
    await page.waitForFunction(()=>document.body.textContent.includes('All projects'));
    await page.goto(fixture.origin+'/#/w/v3/operations');
    for(const width of [1440,320]){
      await page.setViewportSize({width,height:950});
      if(width===320){const show=page.getByRole('button',{name:'Show details',exact:true});if(await show.isVisible())await show.click();}
      const title=page.getByRole('heading',{name:'Canceled Play · unqualified',exact:true});
      await title.waitFor();await title.scrollIntoViewIfNeeded();
      const details=page.getByText('Details · original canceled Play and continuation boundary',{exact:true});
      await details.focus();await page.keyboard.press('Enter');
      assert.equal(await details.evaluate(e=>e.parentElement.open),true);
      await page.keyboard.press('Enter');
      assert.equal(await page.getByRole('button',{name:/confirm (play|cancel|pause|resume)/i}).count(),0);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
      await page.screenshot({path:path.join(output,'canceled-play-'+width+'.png'),fullPage:true});
      runs.push({width,noOverflow:true,keyboardDetails:true,noConfirmationOrWake:true});
    }
    assert.deepEqual(errors,[]);assert.deepEqual(foreign,[]);
    assert.equal(posts.filter(p=>!p.endsWith('/login')).length,0);
    console.log(JSON.stringify({rendered:runs,liveNativeActions:0,controlWrites:0,errors:0}));
    await context.close();
  }finally{
    if(browser)await browser.close();child.kill('SIGINT');await exited;
    assert.equal(childExit,0,'Fixture conservation failed: '+stderr);
  }
})().catch(e=>{console.error(e.message);process.exitCode=1;});
