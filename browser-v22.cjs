const fs=require('fs'),os=require('os'),path=require('path'),{spawn}=require('child_process'),assert=require('assert');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),temp=fs.mkdtempSync(path.join(os.tmpdir(),'halaqat-v22-')),port=8491,base='http://127.0.0.1:'+port;
let logs='',browser;const server=spawn('python',['-m','uvicorn','app.main:app','--host','127.0.0.1','--port',String(port)],{cwd:root,env:{...process.env,APP_ENV:'development',NOTIFICATION_WORKER:'0',DATABASE_URL:'sqlite:///'+path.join(temp,'app.db')}});
server.stderr.on('data',d=>logs+=d);server.stdout.on('data',d=>logs+=d);
async function api(c,url,data,method='post',form=false){const r=await c.request[method](base+url,form?{form:data}:{data});assert(r.ok(),url+' '+await r.text());return (r.headers()['content-type']||'').includes('json')?r.json():null;}
(async()=>{
 for(let i=0;i<100;i++){try{if((await fetch(base+'/healthz')).ok)break;}catch{}await new Promise(r=>setTimeout(r,200));}
 browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/tmp/chromium',headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 const owner=await browser.newContext(),errors=[];await api(owner,'/setup',{organization:'جامع الاختبار',full_name:'مالك التحقق',username:'owner_test',password:'OwnerPass1@',confirm_password:'OwnerPass1@'},'post',true);
 const B='/api/halaqat/mosques/1';
 async function activate(d){const c=await browser.newContext();await api(c,'/login',{identity:d.user.username,password:d.temporary_password},'post',true);await api(c,'/account/security',{current_password:d.temporary_password,new_password:'NewPass1@abc',confirm_password:'NewPass1@abc'},'post',true);return c;}
 const sup=await activate(await api(owner,B+'/supervisors',{full_name:'مشرف الاختبار',username:'supervisor'}));
 const ring=(await api(sup,B+'/rings',{name:'حلقة النور'})).ring;
 const tr=(await api(sup,B+'/requests/teacher',{full_name:'معلم الاختبار',halaqa_id:ring.id})).request;
 const teacher=await activate(await api(owner,B+'/requests/'+tr.id+'/approve',{}));
 const sr=(await api(teacher,B+'/requests/student',{full_name:'طالب الاختبار',halaqa_id:ring.id,guardian_name:'ولي أمر الاختبار'})).request;
 const family=await activate(await api(owner,B+'/requests/'+sr.id+'/approve',{}));
 const dash=await api(teacher,B+'/dashboard',undefined,'get'),sid=dash.students[0].id;
 const t=await teacher.newPage(),p=await family.newPage(),o=await owner.newPage();for(const page of [t,p,o])page.on('pageerror',e=>errors.push(e.message));
 async function ready(page){await page.goto(base+'/halaqat');await page.locator('#halaqatStatus').filter({hasText:'تم تحديث البيانات'}).waitFor();}
 async function tab(page,name,root='studentFile'){await page.locator('#'+root).getByRole('tab',{name,exact:true}).click();}
 async function open(page){if(await page.locator('#halaqatWorkspace').getByRole('tab',{name:'الطلاب والحلقات',exact:true}).count())await tab(page,'الطلاب والحلقات','halaqatWorkspace');await page.locator('[data-file="'+sid+'"]').first().click();await page.locator('#studentFile .workspace-tabs').waitFor();}
 async function save(page,selector,suffix){const wait=page.waitForResponse(r=>r.url().includes(suffix)&&['POST','PUT'].includes(r.request().method()));await page.locator(selector).click();assert((await wait).ok());await page.locator('#halaqatStatus').filter({hasText:'تم الحفظ بنجاح'}).waitFor();}
 await ready(t);await open(t);await tab(t,'التسميع والأوراد');
 await t.locator('#mistakeForm [name="surah"]').selectOption('112');assert.equal(await t.locator('#mistakeForm [name="ayah"] option').count(),4);
 await t.locator('#mistakeForm [name="ayah"]').selectOption('3');await t.locator('#mistakeForm [name="support"]').selectOption('strong');
 await save(t,'#mistakeForm button:not([type="button"])','/mistakes');assert((await t.locator('#studentFile').innerText()).includes('تثبيت قوي'));
 await t.locator('[data-edit-mistake]').click();assert.equal(await t.locator('#mistakeForm [name="ayah"]').inputValue(),'3');
 await tab(t,'الخريطة والخطط');await t.getByText('تحديث جزء',{exact:true}).click();await t.locator('#juzForm [name="status"]').selectOption('memorized');await save(t,'#juzForm button','/juz/');
 await t.getByText('إنشاء خطة قصيرة',{exact:true}).click();await t.locator('#supportPlanForm [name="title"]').fill('تثبيت الإخلاص');await t.locator('#supportPlanForm [name="tasks"]').fill('تثبيت الآية الثالثة\nمراجعة السورة');await save(t,'#supportPlanForm button','/support-plans');
 await t.locator('summary').filter({hasText:/^الإخلاص ·/}).click();await save(t,'#reviewApprove112 button','/review/112/approve');
 await ready(p);await open(p);assert.equal(await p.locator('#mistakeForm').count(),0);assert.equal(await p.locator('#juzForm').count(),0);
 await tab(p,'المحادثة');await tab(t,'المحادثة');await p.locator('#messageForm [name="body"]').fill('رسالة متابعة مباشرة');await save(p,'#messageForm button','/messages');await t.locator('#messageRows').getByText('رسالة متابعة مباشرة',{exact:true}).waitFor({timeout:15000});
 await p.locator('#notificationBox summary').click();assert(await p.getByRole('button',{name:'تفعيل إشعارات هذا الجهاز',exact:true}).isVisible());await p.locator('#notificationBox summary').click();
 for(const width of [390,768,1280]){await p.setViewportSize({width,height:900});assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Overflow '+width);}
 await p.setViewportSize({width:390,height:844});await p.screenshot({path:path.join(temp,'family-mobile.png'),fullPage:true});
 // Offline shell loads again without the network; drafts survive and synchronize once.
 const notebook=await teacher.newPage();await notebook.goto(base+'/offline?mid=1');await notebook.locator('#prepareOffline').click();await notebook.locator('#offlineStatus').filter({hasText:'تم التجهيز'}).waitFor();await notebook.evaluate(()=>navigator.serviceWorker.ready);
 await teacher.setOffline(true);await notebook.reload();await notebook.locator('summary').first().click();await notebook.locator('[name="memorized"]').fill('سورة الإخلاص');await notebook.locator('form button').click();await notebook.locator('#offlineStatus').filter({hasText:'حُفظت المسودة'}).waitFor();await teacher.setOffline(false);await notebook.locator('#syncOffline').click();await notebook.locator('#offlineStatus').filter({hasText:'تمت مزامنة 1'}).waitFor();
 await ready(o);await tab(o,'الإدارة','halaqatWorkspace');await o.screenshot({path:path.join(temp,'owner-desktop.png'),fullPage:true});
 assert.equal(errors.length,0,errors.join('\n'));console.log('v22 browser passed: tabs, mistakes, plans, spaced review, guardian read-only, live chat, notification controls, offline reload/save/sync, responsive. Screenshots: '+temp);
})().catch(e=>{console.error(e);console.error(logs.slice(-4000));process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill();});
