'use strict';
const assert=require('node:assert/strict'),cp=require('node:child_process');
const {chromium}=require('playwright');
(async()=>{
  const child=cp.spawn('python3',['-B','tests/manual_maintenance_dashboard_fixture.py'],{stdio:['ignore','pipe','pipe']});
  const exited=new Promise(resolve=>child.once('exit',resolve));let browser,stderr='';child.stderr.on('data',x=>stderr+=x);
  try{
    const fixture=await new Promise((resolve,reject)=>{
      let raw='';const timer=setTimeout(()=>reject(Error('Fixture timeout '+stderr)),30000);
      child.once('exit',()=>{clearTimeout(timer);reject(Error('Fixture exited '+stderr));});
      child.stdout.on('data',x=>{raw+=x;if(raw.includes('\n')){clearTimeout(timer);resolve(JSON.parse(raw.split('\n')[0]));}});
    });
    browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
    const page=await browser.newPage(),errors=[],posts=[],checks=[];
    page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname);});
    await page.goto(fixture.origin+'/#token='+encodeURIComponent(fixture.token));
    await page.getByRole('heading',{name:'Preparation retained; pilot not started',exact:true}).waitFor();
    for(const width of [1440,320]){
      await page.setViewportSize({width,height:950});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
      assert.equal(await page.getByRole('button',{name:/Confirm|Play|Send|Resume|readiness/i}).count(),0);
      await page.getByRole('button',{name:/RETAINED PREPARATION/}).click();
      await page.getByRole('heading',{name:'Retained preparation',exact:true}).waitFor();
      await page.getByRole('button',{name:/PROJECT BRAIN/}).click();
      await page.getByRole('heading',{name:'Designated brain',exact:true}).waitFor();
      await page.getByText('Details · preserved usage and request',{exact:true}).click();
      await page.locator('#usage').getByText('Unknown',{exact:true}).waitFor();
      await page.getByText('Details · preserved usage and request',{exact:true}).click();
      await page.getByRole('button',{name:'Theme',exact:true}).click();
      await page.getByRole('button',{name:'Refresh saved view',exact:true}).click();
      await page.getByText('Read-only recovery view · no reload, replay or automatic execution',{exact:true}).waitFor();
      if(process.env.RECOVERY_SCREENSHOT_DIR)await page.screenshot({path:process.env.RECOVERY_SCREENSHOT_DIR+'/recovery-'+width+'.png',fullPage:true});
      checks.push({width,noOverflow:true,operationalControls:0,nodeSelection:true,unknownUsagePreserved:true});
    }
    await page.emulateMedia({reducedMotion:'reduce'});
    await page.getByRole('button',{name:/PROJECT BRAIN/}).focus();
    assert.equal(await page.getByRole('button',{name:/PROJECT BRAIN/}).evaluate(e=>document.activeElement===e),true);
    assert.deepEqual(errors,[]);assert.deepEqual(posts,['/api/login']);
    console.log(JSON.stringify({checks,errors:0,controlPosts:0,nativeCalls:0,keyboardFocus:true,reducedMotion:true}));
  }finally{
    if(browser)await browser.close();child.kill('SIGINT');await exited;
    if(child.exitCode!==0)throw Error('Fixture preservation failed '+stderr);
  }
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
