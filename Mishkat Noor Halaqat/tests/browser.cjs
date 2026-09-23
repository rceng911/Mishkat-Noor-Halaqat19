const fs=require('fs'),os=require('os'),path=require('path'),{spawn}=require('child_process'),assert=require('assert');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),temp=fs.mkdtempSync(path.join(os.tmpdir(),'halaqat-browser-')),port=8490,base='http://127.0.0.1:'+port;
let logs='',browser;
const server=spawn(process.env.PYTHON_EXE||'python',['-m','uvicorn','app.main:app','--host','127.0.0.1','--port',String(port)],{cwd:root,windowsHide:true,env:{...process.env,APP_ENV:'development',DATABASE_URL:'sqlite:///'+path.join(temp,'browser.db').replaceAll('\\','/')}});
server.stderr.on('data',d=>logs+=d);server.stdout.on('data',d=>logs+=d);
async function post(c,url,data,form=false){const r=await c.request.post(base+url,form?{form:data}:{data});assert(r.ok(),await r.text());return (r.headers()['content-type']||'').includes('application/json')?r.json():null;}
(async()=>{
 for(let i=0;i<100;i++){try{if((await fetch(base+'/healthz')).ok)break;}catch{}if(i===99)throw Error(logs);await new Promise(r=>setTimeout(r,300));}
 const bundled=process.env.SPARTICUZ_MODULE?require(process.env.SPARTICUZ_MODULE).default:null;
 browser=await chromium.launch({headless:true,...(bundled?{executablePath:await bundled.executablePath(),args:bundled.args}:process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
 const errors=[],owner=await browser.newContext(),page=await owner.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/setup');
 for(const [name,value] of Object.entries({organization:'حلقات التحقق',full_name:'مالك التحقق',username:'مالك_التحقق',password:'OwnerPass1@',confirm_password:'OwnerPass1@'}))await page.locator('[name="'+name+'"]').fill(value);
 await page.getByRole('button',{name:'إنشاء حساب المالك'}).click();await page.waitForURL('**/halaqat');
 const b='/api/halaqat/mosques/1';
 async function activate(d){const c=await browser.newContext();await post(c,'/login',{identity:d.user.username,password:d.temporary_password},true);await post(c,'/account/security',{current_password:d.temporary_password,new_password:'NewPass1@abc',confirm_password:'NewPass1@abc'},true);return c;}
 const sup=await activate(await post(owner,b+'/supervisors',{full_name:'مشرف التحقق',username:'مشرف_التحقق'}));
 const ring=(await post(sup,b+'/rings',{name:'حلقة النور',schedule:'الأحد إلى الخميس'})).ring;
 const req=(await post(sup,b+'/requests/teacher',{full_name:'مدرس التحقق',halaqa_id:ring.id})).request;
 const teacher=await activate(await post(owner,b+'/requests/'+req.id+'/approve',{}));
 const sr=(await post(teacher,b+'/requests/student',{full_name:'طالب التحقق',halaqa_id:ring.id,guardian_name:'ولي الطالب'})).request;
 const student=await activate(await post(owner,b+'/requests/'+sr.id+'/approve',{}));
 const t=await teacher.newPage();t.on('pageerror',e=>errors.push(e.message));await t.setViewportSize({width:390,height:844});await t.goto(base+'/halaqat');
 await t.locator('#studentRequestForm [name="full_name"]').fill('ابن ثان للاختبار');
 await t.locator('#studentRequestForm [name="halaqa_id"]').selectOption(String(ring.id));
 await t.locator('#studentRequestForm [name="recipient_type"]').selectOption('guardian');
 await t.locator('#studentRequestForm [name="guardian_name"]').fill('ولي الطالب');
 await t.locator('#studentRequestForm [name="guardian_phone"]').fill('0500000000');
 const requestSaved=t.waitForResponse(r=>r.url().endsWith('/requests/student')&&r.request().method()==='POST');
 await t.locator('#studentRequestForm button').click();assert((await requestSaved).ok());
 await page.reload();await page.locator('.approval-form').waitFor();
 const family=(await (await owner.request.get(base+b+'/dashboard')).json()).accounts.find(a=>a.role==='halaqa_student');
 await page.locator('.approval-form [name="existing_user_id"]').selectOption(String(family.id));
 const approved=page.waitForResponse(r=>r.url().endsWith('/approve')&&r.request().method()==='POST');
 await page.locator('.approval-form button:not([type="button"])').click();assert((await approved).ok());
 await t.getByRole('button',{name:'ملف الطالب',exact:true}).first().click();
 await t.getByText('تعديل خطة الطالب',{exact:true}).click();
 await t.locator('[name="memorization_preset"]').selectOption('0.5');
 await t.locator('[name="revision_preset"]').selectOption('ayah');await t.locator('#planForm [name="revision_amount"]').fill('7');
 const saved=t.waitForResponse(r=>r.url().endsWith('/plan')&&r.request().method()==='PUT');
 await t.getByRole('button',{name:'حفظ خطة الطالب',exact:true}).click();assert((await saved).ok());
 await t.locator('#planForm').waitFor({state:'attached'});
 const s=await student.newPage();s.on('pageerror',e=>errors.push(e.message));await s.goto(base+'/halaqat');await s.getByRole('button',{name:'ملف الطالب',exact:true}).first().waitFor();assert.equal(await s.getByRole('button',{name:'ملف الطالب',exact:true}).count(),2);await s.getByRole('button',{name:'ملف الطالب',exact:true}).first().click();await s.locator('#studentFile h1').waitFor();
 assert.equal(await s.locator('#planForm').count(),0);
 assert((await s.locator('#studentFile').innerText()).includes('0.5'));
 for(const width of [390,768,1280]){await s.setViewportSize({width,height:900});assert(await s.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Overflow '+width);}

 await t.locator('#assignmentForm [name="memorization"]').fill('البقرة من الآية 1 إلى 5');
 await t.locator('#assignmentForm [name="revision"]').fill('سورة الفاتحة');
 const assigned=t.waitForResponse(r=>r.url().endsWith('/assignments')&&r.request().method()==='POST');
 await t.locator('#assignmentForm button').click();assert((await assigned).ok());
 await t.locator('.assignment-result').waitFor();
 await t.locator('.assignment-result [name="status"]').selectOption('completed');
 const assessed=t.waitForResponse(r=>r.url().includes('/assignments/')&&r.request().method()==='PUT');
 await t.locator('.assignment-result button').click();assert((await assessed).ok());
 await t.locator('#halaqatStatus').filter({hasText:'تم الحفظ بنجاح'}).waitFor();
 await t.locator('#profileForm [name="school_grade"]').fill('الصف الخامس');
 const edited=t.waitForResponse(r=>r.url().endsWith('/profile')&&r.request().method()==='PUT');
 await t.locator('#profileForm button').click();assert((await edited).ok());
 await t.locator('#halaqatStatus').filter({hasText:'تم الحفظ بنجاح'}).waitFor();
 await page.reload();await page.locator('#batchRows select').first().waitFor();
 await page.locator('[data-all-present]').click();
 const batched=page.waitForResponse(r=>r.url().endsWith('/attendance/batch')&&r.request().method()==='POST');
 await page.locator('#batchForm button:not([type="button"])').click();assert((await batched).ok());
 await page.locator('#halaqatStatus').filter({hasText:'تم حفظ التحضير'}).waitFor();
 await page.locator('[name="portalView"]').selectOption('student');
 await page.getByRole('heading',{name:'ملفي كطالب',exact:true}).waitFor();
 assert.equal(await page.locator('#studentRequestForm').count(),0);
 assert.equal(await page.getByRole('button',{name:'ملف الطالب',exact:true}).count(),0);
 await page.locator('[name="portalView"]').selectOption('supervisor');
 await page.locator('#studentRequestForm').waitFor();assert.equal(await page.locator('#featuresForm').count(),0);
 await page.locator('[name="portalView"]').selectOption('owner');
 await page.locator('#featuresForm').waitFor();
 await s.locator('[data-back]').click();await s.getByRole('button',{name:'ملف الطالب',exact:true}).first().click();
 await s.locator('#monthlyDownload').waitFor();
 const pdf=await student.request.get(base+await s.locator('#monthlyDownload').getAttribute('href'));assert(pdf.ok());assert.equal(pdf.headers()['content-type'],'application/pdf');
 assert.equal(await s.locator('#assignmentForm,.assignment-result,#profileForm').count(),0);
 assert((await s.locator('#studentFile').innerText()).includes('البقرة من الآية 1 إلى 5'));
 // Version 15 visible workflows.
 async function openDetails(p,form){const details=p.locator(form).locator('xpath=ancestor::details[1]');if(await details.count()&&!(await details.getAttribute('open')!==null))await details.locator('summary').first().click();}
 async function saveForm(p,form,suffix,method='POST'){const response=p.waitForResponse(r=>r.url().endsWith(suffix)&&r.request().method()===method);await p.locator(form+' button:not([type="button"])').last().click();const r=await response;assert(r.ok(),await r.text());await p.locator('#halaqatStatus').filter({hasText:'تم الحفظ بنجاح'}).waitFor();}
 async function reopen(p){await p.locator('[data-back]').click();await p.locator('#halaqatStatus').filter({hasText:'تم تحديث البيانات'}).waitFor();await p.getByRole('button',{name:'ملف الطالب',exact:true}).first().click();await p.locator('#messageRows').waitFor();}
 await openDetails(t,'#quranForm');await t.locator('#quranForm [name="surah"]').selectOption('1');await t.locator('#quranForm [name="status"]').selectOption('memorized');await saveForm(t,'#quranForm','/quran/1','PUT');
 await reopen(s);assert((await s.locator('#studentFile').innerText()).includes('محفوظ: 1'));
 await s.locator('#messageForm [name="body"]').fill('هل نراجع الفاتحة اليوم؟');await saveForm(s,'#messageForm','/messages');
 await reopen(t);assert((await t.locator('#messageRows').innerText()).includes('هل نراجع الفاتحة اليوم؟'));
 await t.locator('#messageForm [name="body"]').fill('نعم، نراجع الفاتحة');await saveForm(t,'#messageForm','/messages');
 await openDetails(t,'#organizedExamForm');await t.locator('#organizedExamForm [name="title"]').fill('اختبار شهري');await t.locator('#organizedExamForm [name="syllabus"]').fill('سورة الفاتحة');await t.locator('#organizedExamForm [name="repeat_days"]').fill('30');await saveForm(t,'#organizedExamForm','/organized-exams');
 const resultForm=t.locator('[data-kind="organizedResult"]').first();const resultId=await resultForm.getAttribute('id');await openDetails(t,'#'+resultId);await resultForm.locator('[name="score_0"]').fill('58');await resultForm.locator('[name="score_1"]').fill('39');await saveForm(t,'#'+resultId,'/result','PUT');
 await page.reload();await page.locator('#calendarForm'+ring.id).waitFor({state:'attached'});await openDetails(page,'#calendarForm'+ring.id);
 const dayText=await page.locator('#exceptionForm'+ring.id+' [name="day"]').inputValue();const next=new Date(dayText+'T12:00:00Z');next.setUTCDate(next.getUTCDate()+1);const nextDay=next.toISOString().slice(0,10);
 await page.locator('#calendarForm'+ring.id+' [name="weekdays"]').first().check();await saveForm(page,'#calendarForm'+ring.id,'/calendar','PUT');
 await openDetails(page,'#exceptionForm'+ring.id);await page.locator('#exceptionForm'+ring.id+' [name="day"]').fill(nextDay);await page.locator('#exceptionForm'+ring.id+' [name="held"]').selectOption('true');await saveForm(page,'#exceptionForm'+ring.id,'/calendar-exception','PUT');
 await s.locator('#excuseForm [name="day"]').fill(nextDay);await s.locator('#excuseForm [name="reason"]').fill('موعد عائلي');await saveForm(s,'#excuseForm','/excuses');
 await page.reload();await page.getByRole('button',{name:'مراجعة العذر',exact:true}).first().click();await page.locator('[data-kind="excuseReview"]').waitFor();const reviewId=await page.locator('[data-kind="excuseReview"]').first().getAttribute('id');const excuseId=await page.locator('#'+reviewId).getAttribute('data-id');await saveForm(page,'#'+reviewId,'/excuses/'+excuseId,'PUT');
 await page.locator('[data-back]').click();await page.locator('#halaqatStatus').filter({hasText:'تم تحديث البيانات'}).waitFor();await page.locator('#announcementForm').waitFor({state:'attached'});await openDetails(page,'#announcementForm');await page.locator('#announcementForm [name="title"]').fill('موعد الحلقة');await page.locator('#announcementForm [name="body"]').fill('نلتقي بعد العصر');await saveForm(page,'#announcementForm','/announcements');
 await page.locator('[data-audit-load="0"]').click();await page.locator('#auditRows .halaqat-card').first().waitFor();
 // Download the genuine Excel template and populate it as an administrator would.
 const tpl=await owner.request.get(base+b+'/imports/template.xlsx');assert(tpl.ok());const xl=path.join(temp,'students.xlsx');fs.writeFileSync(xl,await tpl.body());
 require('child_process').execFileSync(process.env.PYTHON_EXE||'python',['-c',"from openpyxl import load_workbook;import sys;w=load_workbook(sys.argv[1]);s=w['الطلاب'];s['A2']='طالب من إكسل';s['B2']='الطالب';w.save(sys.argv[1])",xl]);
 await openDetails(page,'#importForm');await page.locator('#importForm [name="halaqa_id"]').selectOption(String(ring.id));await page.locator('#importForm [name="file"]').setInputFiles(xl);await page.locator('#importForm button').click();await page.locator('#importCommitForm').waitFor();assert((await page.locator('#importPreview').innerText()).includes('طالب من إكسل'));
 const committed=page.waitForResponse(r=>r.url().endsWith('/imports/commit'));await page.locator('#importCommitForm button').click();assert((await committed).ok());await page.locator('#halaqatStatus').filter({hasText:'تم رفع 1 طلبات'}).waitFor();
 // Archive and restore the real first student's profile; retain its Quran map and conversation.
 const target=(await (await owner.request.get(base+b+'/dashboard')).json()).students.find(x=>x.name==='طالب التحقق');
 page.on('dialog',d=>d.accept('اختبار الأرشفة والاستعادة'));
 await page.locator('button[data-file="'+target.id+'"]').first().click();await page.locator('[data-student-archive="'+target.id+'"]').click();await page.locator('#halaqatWorkspace').waitFor();
 const restore=page.locator('[data-student-archive="'+target.id+'"][data-active="true"]');await restore.waitFor({state:'attached'});await restore.locator('xpath=ancestor::details[1]').locator('summary').click();await restore.click();await page.locator('#halaqatStatus').filter({hasText:'تم تحديث البيانات'}).waitFor();
 await openDetails(page,'#mosqueCreateForm');await page.locator('#mosqueCreateForm [name="name"]').fill('مسجد اختبار ثان');await saveForm(page,'#mosqueCreateForm','/organizations');assert.equal(await page.locator('#halaqatMosque option').count(),2);
 await page.locator('#halaqatMosque').selectOption('1');await page.getByRole('button',{name:'ملف الطالب',exact:true}).first().waitFor();
 await reopen(s);assert((await s.locator('#studentFile').innerText()).includes('محفوظ: 1'));assert((await s.locator('#messageRows').innerText()).includes('نعم، نراجع الفاتحة'));
 for(const width of [390,768,1280]){await s.setViewportSize({width,height:900});assert(await s.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'v15 overflow '+width);}

 // v16: owner can add teachers manually; management changes preserve other circles.
 await page.locator('#halaqatStatus').filter({hasText:'تم تحديث البيانات'}).waitFor();
 await page.locator('#teacherRequestForm [name="full_name"]').fill('مدرس إضافي من المالك');await page.locator('#teacherRequestForm [name="halaqa_id"]').selectOption(String(ring.id));await saveForm(page,'#teacherRequestForm','/requests/teacher');
 const ringForm='form[data-manage="ring"][data-id="'+ring.id+'"]';await openDetails(page,ringForm);await page.locator(ringForm+' [name="name"]').fill('حلقة بعد تعديل الاسم');await saveForm(page,ringForm,'/rings/'+ring.id,'PUT');
 const teacherForm=page.locator('form[data-manage="teacher"]').first();const teacherId=await teacherForm.getAttribute('data-id');const teacherSelector='form[data-manage="teacher"][data-id="'+teacherId+'"]';await openDetails(page,teacherSelector);await teacherForm.locator('[name="full_name"]').fill('اسم المدرس المعدل');await teacherForm.locator('[name="phone"]').fill('0500000000');await saveForm(page,teacherSelector,'/teachers/'+teacherId+'/profile','PUT');
 await openDetails(page,'#rosterForm');assert.equal(await page.locator('#rosterForm fieldset').count(),3);
 for(let i=0;i<3;i++){await page.locator('#rosterForm [name="ring_'+i+'"]').fill('حلقة الاستيراد '+i);await page.locator('#rosterForm [name="teacher_'+i+'"]').fill('مدرس الاستيراد '+i);await page.locator('#rosterForm [name="students_'+i+'"]').fill('طالب الاستيراد '+i);}
 await page.locator('#rosterForm [name="reviewed"]').check();await saveForm(page,'#rosterForm','/roster/import');
 const imported=(await (await owner.request.get(base+b+'/dashboard')).json()).rings.find(r=>r.name==='حلقة الاستيراد 0');
 const newRingForm='form[data-manage="ring"][data-id="'+imported.id+'"]';await openDetails(page,newRingForm);await page.locator('[data-delete-ring="'+imported.id+'"]').click();await page.locator('#deleteRing'+imported.id+' form').waitFor();await page.locator('#deleteRing'+imported.id+' [name="confirm_name"]').fill(imported.name);await saveForm(page,'#deleteRing'+imported.id+' form','/rings/'+imported.id,'DELETE');
 assert(!(await (await owner.request.get(base+b+'/dashboard')).json()).rings.some(r=>r.id===imported.id));
 const importedStudent=(await (await owner.request.get(base+b+'/dashboard')).json()).students.find(x=>x.name==='طالب الاستيراد 1');await page.locator('[data-file="'+importedStudent.id+'"]').first().click();await page.locator('#profileForm [name="national_id"]').fill('1234567890');await saveForm(page,'#profileForm','/profile','PUT');assert.equal(await page.locator('#profileForm [name="national_id"]').inputValue(),'1234567890');

 // v18: supervisor sees every mosque circle including imports with no assignment.
 const sp=await sup.newPage();sp.on('pageerror',e=>errors.push(e.message));await sp.goto(base+'/halaqat');await sp.getByRole('button',{name:'ملف الطالب',exact:true}).first().waitFor();
 const ownerDashboard=(await (await owner.request.get(base+b+'/dashboard')).json());assert.equal(await sp.getByRole('button',{name:'ملف الطالب',exact:true}).count(),ownerDashboard.students.length);
 await sp.locator('[data-file="'+importedStudent.id+'"]').first().click();await sp.locator('#profileForm').waitFor();assert.equal(await sp.locator('#profileForm [name="national_id"]').inputValue(),'1234567890');assert.equal(await sp.locator('[data-manage="ring"],[data-manage="supervisor"],.approval-form').count(),0);
 const su=(await (await sup.request.get(base+'/api/halaqat/context')).json()).user;
 await page.locator('[data-back]').click();await page.locator('#halaqatStatus').filter({hasText:'تم تحديث البيانات'}).waitFor();
 const sf='form[data-manage="supervisor"][data-id="'+su.id+'"]';await openDetails(page,sf);await page.locator(sf+' [name="full_name"]').fill('المشرف العام');await page.locator(sf+' [name="phone"]').fill('0501234567');await saveForm(page,sf,'/supervisors/'+su.id+'/profile','PUT');
 const rf='form[data-manage="remove-supervisor"][data-id="'+su.id+'"]';await openDetails(page,rf);await page.locator(rf+' [name="confirm_name"]').fill('المشرف العام');await saveForm(page,rf,'/supervisors/'+su.id,'DELETE');assert.equal((await sup.request.get(base+'/api/halaqat/context')).status(),401);
 assert.equal((await (await owner.request.get(base+b+'/dashboard')).json()).students.length,ownerDashboard.students.length);

 // v19: goal, mistake log, guardian practice and term comparison from real forms.
 await reopen(t);await openDetails(t,'#goalForm');await t.locator('#goalForm [name="title"]').fill('هدف ختم تجريبي');await t.locator('#goalForm [name="target"]').fill('20');await t.locator('#goalForm [name="completed"]').fill('6');await saveForm(t,'#goalForm','/completion-goal','PUT');
 await t.locator('#mistakeForm [name="surah"]').selectOption('1');await t.locator('#mistakeForm [name="ayah"]').fill('7');await t.locator('#mistakeForm [name="kind"]').selectOption('tajweed');await saveForm(t,'#mistakeForm','/mistakes');
 await reopen(s);assert((await s.locator('#studentFile').innerText()).includes('هدف ختم تجريبي'));assert.equal(await s.locator('#goalForm,#mistakeForm').count(),0);
 const practiceAid=await s.locator('#homePracticeForm [name="assignment_id"] option').nth(1).getAttribute('value');await s.locator('#homePracticeForm [name="assignment_id"]').selectOption(practiceAid);await saveForm(s,'#homePracticeForm','/home-practice');assert((await s.locator('#studentFile').innerText()).includes('15 دقيقة'));
 await s.locator('#termReportForm button').click();await s.locator('#termReportResult table').waitFor();assert((await s.locator('#termReportResult').innerText()).includes('متوسط التجويد'));
 await t.locator('[data-back]').click();await t.locator('#halaqatStatus').filter({hasText:'تم تحديث البيانات'}).waitFor();await t.locator('#queueViewForm [name="halaqa_id"]').selectOption(String(ring.id));await t.locator('#queueViewForm button').click();await t.locator('#halaqatStatus').filter({hasText:'تم تحديث الدور'}).waitFor();await openDetails(t,'#queueSetForm');await t.locator('#queueSetForm button:not([type="button"])').click();await t.locator('#halaqatStatus').filter({hasText:'تم حفظ الترتيب'}).waitFor();await t.locator('[data-next-turn]').click();await t.locator('#halaqatStatus').filter({hasText:'تم تحديث الدور'}).waitFor();assert((await t.locator('#queueResult').innerText()).includes('الدور الحالي: 2'));
 // Activate a teacher in another circle, then grant/revoke a dated substitute assignment.
 const pendingTeacher=ownerDashboard.requests.find(q=>q.type==='teacher'&&q.status==='pending'&&q.halaqa_id!==ring.id);const tempTeacher=await activate(await post(owner,b+'/requests/'+pendingTeacher.id+'/approve',{}));const tempUid=(await (await tempTeacher.request.get(base+'/api/halaqat/context')).json()).user.id;
 await page.reload();await page.locator('#substituteForm').waitFor();await page.locator('#substituteForm [name="halaqa_id"]').selectOption(String(ring.id));await page.locator('#substituteForm [name="user_id"]').selectOption(String(tempUid));await saveForm(page,'#substituteForm','/substitutes');assert((await (await tempTeacher.request.get(base+b+'/dashboard')).json()).rings.some(r=>r.id===ring.id));
 await page.locator('[data-revoke-sub]').first().click();await page.locator('#halaqatStatus').filter({hasText:'تم تحديث البيانات'}).waitFor();assert(!(await (await tempTeacher.request.get(base+b+'/dashboard')).json()).rings.some(r=>r.id===ring.id));
 assert(await page.locator('[data-missing-name]').count()>0);
 await openDetails(page,'#competitionForm');await page.locator('#competitionForm [name="halaqa_id"]').selectOption(String(ring.id));await page.locator('#competitionForm [name="title"]').fill('مسابقة الاختبار');await page.locator('#competitionForm [name="mode"]').selectOption('team');await saveForm(page,'#competitionForm','/competitions');
 const contest=(await (await owner.request.get(base+b+'/competitions')).json()).competitions[0];
 for(const entry of contest.entries){const form='#contestScore'+entry.id;await openDetails(page,form);await page.locator(form+' [name="value"]').fill('10');await saveForm(page,form,'/entries/'+entry.id,'PUT');await openDetails(page,form);await page.locator('[data-review-entry="'+entry.id+'"][data-state="approved"]').click();await page.locator('#halaqatStatus').filter({hasText:'تم تحديث البيانات'}).waitFor();}
 await openDetails(page,'#contestScore'+contest.entries[0].id);await page.locator('[data-award-contest="'+contest.id+'"][data-awarded="true"]').click();await page.locator('#halaqatStatus').filter({hasText:'تم تحديث البيانات'}).waitFor();assert((await (await owner.request.get(base+b+'/competitions')).json()).competitions[0].entries.every(e=>e.awarded));
 for(const width of [390,768,1280]){await s.setViewportSize({width,height:900});assert(await s.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'v19 overflow '+width);}

 await s.setViewportSize({width:390,height:844});await s.screenshot({path:path.join(temp,'student-mobile.png'),fullPage:true});
 await t.screenshot({path:path.join(temp,'teacher-mobile.png'),fullPage:true});
 assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,screenshots:temp,checks:['owner setup','role accounts','teacher edits half-page plan','seven-ayah revision','student read-only','responsive 390/768/1280','next assignment and assessment','profile edit','batch attendance','owner view switching','monthly PDF','Quran map','messages','organized exams','calendar exceptions','excuse approval','announcements','audit log','Excel preview and commit','archive and restore','multiple mosques','owner adds teacher','ring editing','teacher contact editing','reviewed roster import','permanent ring deletion','student identity','supervisor sees all circles','supervisor edit and removal','completion goals','mistake log','home practice','term comparison','recitation queue','temporary teacher','missing data','competition awards','no JS errors']}));
})().catch(e=>{console.error(e);console.error(logs.slice(-1500));process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill();});
