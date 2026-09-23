(()=>{
'use strict';
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const roles={owner:'المالك',halaqa_supervisor:'مشرف الحلقات',halaqa_teacher:'المدرس',halaqa_student:'الطالب / ولي الأمر'};
const states={pending:'بانتظار المالك',approved:'تم التفعيل',rejected:'مرفوض',returned:'مُعاد للاستكمال'},attendance={present:'حاضر',absent:'غائب',excused:'مستأذن'};
const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Riyadh'}).format(new Date());
let mid=0,data=null,file=null,sid=0,busy=false,portalView='owner',monitor=null,follow=null;
const status=t=>$('#halaqatStatus').textContent=t,base=()=>'/api/halaqat/mosques/'+mid;
async function api(path,body,method='POST'){
 const r=await fetch(path,{cache:'no-store',headers:{'X-Portal-View':portalView},...(body!==undefined?{method,headers:{'Content-Type':'application/json','X-Portal-View':portalView},body:JSON.stringify(body)}:{})}),d=await r.json();
 if(!r.ok){if(d.redirect)location.assign(d.redirect);throw Error(typeof d.detail==='string'?d.detail:Array.isArray(d.detail)?d.detail.map(x=>x.msg).join('، '):'تعذر إتمام الطلب');}return d;
}
async function run(fn){if(busy)return;busy=true;status('جارٍ التنفيذ…');document.querySelectorAll('button').forEach(x=>x.disabled=true);try{await fn();}catch(e){status(e.message);}finally{busy=false;document.querySelectorAll('button').forEach(x=>x.disabled=false);}}
const button=(label,attr)=>'<button type="button" class="halaqat-btn" '+attr+'>'+label+'</button>';
const panel=(title,body)=>'<article class="halaqat-panel"><h2>'+title+'</h2>'+body+'</article>';
const input=(name,label,value='',type='text',required=true,attrs='')=>'<label>'+label+'<input name="'+name+'" type="'+type+'" value="'+esc(value)+'" '+(required?'required':'')+' '+attrs+'></label>';
const select=(name,label,options,value='',required=true)=>'<label>'+label+'<select name="'+name+'" '+(required?'required':'')+'>'+options.map(([v,t])=>'<option value="'+esc(v)+'" '+(String(value)===String(v)?'selected':'')+'>'+esc(t)+'</option>').join('')+'</select></label>';
const multiSelect=(name,label,options)=>'<label>'+label+'<select name="'+name+'" multiple required size="'+Math.min(Math.max(options.length,2),6)+'">'+options.map(([v,t])=>'<option value="'+esc(v)+'">'+esc(t)+'</option>').join('')+'</select><small>يمكن اختيار أكثر من مشرف.</small></label>';
const empty=t=>'<p class="empty">'+t+'</p>',unit=u=>u==='ayah'?'آية':'وجه',ringOpts=()=>[['','اختر الحلقة'],...data.rings.map(r=>[r.id,r.name])];
function credentials(d){$('#halaqatCredentials').hidden=false;$('#halaqatCredentials').innerHTML=d.linked_existing?'<strong>تم اعتماد الطالب وربطه بالحساب المحدد</strong><p>'+esc(d.user?.name)+'</p>'+button('إخفاء','data-hide-credentials'):'<strong>بيانات الدخول — احفظها وسلّمها لصاحب الحساب</strong><p>اسم المستخدم: <code>'+esc(d.user?.username||d.username)+'</code></p><p>الرمز المؤقت: <code>'+esc(d.temporary_password)+'</code></p><p>يجب تغييره عند أول دخول.</p>'+button('إخفاء الرمز','data-hide-credentials');window.scrollTo({top:0,behavior:'smooth'});}
function familyOptions(){return (data.accounts||[]).filter(u=>u.role==='halaqa_student').map(u=>[u.id,u.name+' — '+u.username+(u.children?.length?' — الأبناء: '+u.children.map(c=>c.name).join('، '):'')]);}
function requestDetails(r){if(r.type!=='student')return '';return '<p>ولي الأمر: '+esc(r.guardian_name||'—')+' · '+esc(r.guardian_relation||'—')+' · '+esc(r.guardian_phone||'—')+'</p><p>الميلاد: '+esc(r.birth_date||'—')+' · الصف: '+esc(r.school_grade||'—')+'</p><p>الحفظ الحالي: '+esc(r.current_memorization||'—')+'</p>';}
function students(){return data.students.length?'<label>بحث عن طالب<input id="studentSearch" type="search"></label><div>'+data.students.map(s=>'<div class="student-row" data-student-name="'+esc(s.name)+'"><div><strong>'+esc(s.name)+'</strong><small>'+esc(data.rings.find(r=>r.id===s.halaqa_id)?.name)+'</small></div>'+button('ملف الطالب','data-file="'+s.id+'"')+'</div>').join('')+'</div>':empty('لا يوجد طلاب معتمدون بعد.');}
function rings(){return data.rings.length?data.rings.map(r=>'<div class="halaqat-card"><h3>'+esc(r.name)+'</h3><p>'+esc(r.schedule)+'</p><p>المشرفون: '+esc((r.supervisors||[]).map(s=>s.name).join('، ')||'غير محدد')+' · المدرسون: '+esc((r.teachers||[]).map(t=>t.name).join('، ')||'بانتظار إصدار الحساب')+' · الطلاب: '+r.student_count+'</p></div>').join(''):empty('أنشئ الحلقة واربطها بمشرف قبل طلب حساب المدرس.');}
function recentAbsences(){const since=new Date();since.setDate(since.getDate()-29);const cutoff=since.toISOString().slice(0,10),rows=data.students.map(s=>({...s,absences:data.progress.filter(p=>p.student_id===s.id&&p.attendance==='absent'&&p.day>=cutoff).length})).filter(s=>s.absences>=3);return rows.length?rows.map(s=>'<div class="student-row"><span>'+esc(s.name)+' · '+s.absences+' أيام غياب</span>'+button('متابعة الملف','data-file="'+s.id+'"')+'</div>').join(''):empty('لا يوجد طالب سجل 3 أيام غياب أو أكثر خلال آخر 30 يومًا.');}
function renderBaseDashboard(){
 const role=data.user.role;$('#halaqatStats').innerHTML=[['الحلقات',data.stats.rings],['الطلاب',data.stats.students],['طلبات معلقة',data.stats.pending_requests]].map(([t,v])=>'<div class="halaqat-stat"><span>'+t+'</span><b>'+v+'</b></div>').join('');
 if(role==='halaqa_student'){$('#halaqatWorkspace').innerHTML='<div class="halaqat-grid family-dashboard">'+panel(data.user.account_type==='guardian'?'أبنائي وملفاتهم':'ملفي كطالب',students())+'</div>';return;}let s='';
 if(role==='owner'){
 s+=panel('حسابات المشرفين','<form id="supervisorForm" class="halaqat-form">'+input('full_name','اسم المشرف','','text',true,'minlength="2" maxlength="180"')+input('username','اسم المستخدم (عربي أو إنجليزي)','','text',true,'minlength="3" maxlength="30"')+'<small>يمكنك إضافة العدد الذي تحتاجه من المشرفين.</small><button>إنشاء حساب مشرف</button></form>');
 s+=panel('إدارة الحسابات',data.accounts.map(u=>'<div class="student-row"><div><strong>'+esc(u.name)+'</strong><small>'+esc(u.username)+' · '+roles[u.role]+'</small>'+(u.children?.length?'<small class="children-line">الأبناء: '+u.children.map(c=>esc(c.name)).join('، ')+'</small>':'')+'</div>'+button('رمز مؤقت جديد','data-reset="'+u.id+'"')+'</div>').join('')||empty('ابدأ بإنشاء حسابات المشرفين.'));
 }
 if(role==='owner'||role==='halaqa_supervisor')s+=panel('إنشاء حلقة','<form id="ringForm" class="halaqat-form">'+input('name','اسم الحلقة','','text',true,'minlength="2" maxlength="180"')+input('schedule','أيام الحلقة ووقتها','','text',false)+(role==='owner'?multiSelect('supervisor_ids','مشرفو الحلقة',data.supervisors.map(s=>[s.id,s.name])):'')+'<button>حفظ الحلقة</button></form>');
 if(role==='halaqa_supervisor'||role==='owner')s+=panel(role==='owner'?'إضافة مدرس وطلب حسابه':'طلب حساب مدرس','<form id="teacherRequestForm" class="halaqat-form">'+accountFields()+'<button>رفع الطلب للمالك</button></form>');
 if(['owner','halaqa_supervisor','halaqa_teacher'].includes(role))s+=panel(role==='owner'?'إضافة ملف طالب':'رفع ملف طالب للمالك','<form id="studentRequestForm" class="halaqat-form">'+accountFields(true)+'<button>'+(role==='owner'?'تجهيز ملف الطالب':'رفع الملف للمالك')+'</button></form>');
 s+=panel('ملفات الطلاب',students())+panel('الحلقات',rings())+panel('طلبات الحسابات',requests())+panel('متابعة الغياب خلال 30 يومًا',recentAbsences());
 $('#halaqatWorkspace').innerHTML='<div class="halaqat-grid">'+s+'</div>';
}
async function load(){data=await api(base()+'/dashboard');monitor=await api(base()+'/monitor');development=await api(base()+'/development');orgOverview=data.user.role==='owner'?await api('/api/halaqat/organizations/overview'):null;managementTeachers=data.user.role==='owner'?(await api(base()+'/teachers/manage')).teachers:[];managementSupervisors=data.user.role==='owner'?(await api(base()+'/supervisors/manage')).supervisors:[];learningData=await api(base()+'/learning-dashboard');contestData=(await api(base()+'/competitions')).competitions;$('#halaqatWorkspace').hidden=false;renderDashboard();renderManagement();renderLearningDashboard();$('#studentFile').hidden=true;status(roles[data.user.role]+' · '+data.user.name+' · تم تحديث البيانات');}
function quantity(prefix,title,u='page',amount=1){const preset=u==='ayah'?'ayah':[.5,1,2].includes(Number(amount))?String(amount):'custom';return '<fieldset class="quantity"><legend>'+title+'</legend>'+select(prefix+'_preset','المقدار',[['0.5','نصف وجه'],['1','وجه واحد'],['2','وجهان'],['custom','عدد أوجه مخصص'],['ayah','عدد آيات محدد']],preset)+input(prefix+'_amount','العدد',amount,'number',true,'min="0.5" max="1000" step="0.5"')+'</fieldset>';}
function planEditor(){const p=file.plan||{memorization_unit:'page',memorization_amount:1,revision_unit:'page',revision_amount:2,sessions_per_week:5};return '<form id="planForm" class="halaqat-form"><div class="halaqat-form-grid">'+quantity('memorization','الحفظ لكل لقاء',p.memorization_unit,p.memorization_amount)+quantity('revision','المراجعة لكل لقاء',p.revision_unit,p.revision_amount)+input('sessions_per_week','عدد اللقاءات أسبوعيًا',p.sessions_per_week,'number',true,'min="1" max="7"')+input('start_surah','سورة البداية',p.start_surah||'','text',false)+input('start_ayah','آية البداية',p.start_ayah||'','number',false,'min="1" max="286"')+input('end_surah','سورة النهاية',p.end_surah||'','text',false)+input('end_ayah','آية النهاية',p.end_ayah||'','number',false,'min="1" max="286"')+input('notes','تعليمات الخطة',p.notes||'','text',false)+'</div><button>حفظ خطة الطالب</button></form>';}
function planSummary(){const p=file.plan;if(!p)return empty('لم يحدد المدرس خطة بعد.');return '<p>الحفظ: <strong>'+p.memorization_amount+' '+unit(p.memorization_unit)+'</strong> لكل لقاء</p><p>المراجعة: <strong>'+p.revision_amount+' '+unit(p.revision_unit)+'</strong> لكل لقاء</p><p>'+p.sessions_per_week+' لقاءات أسبوعيًا</p><p>'+esc(p.start_surah)+' '+esc(p.start_ayah??'')+' — '+esc(p.end_surah)+' '+esc(p.end_ayah??'')+'</p><p>'+esc(p.notes)+'</p>';}
function progressForm(){const p=file.plan||{memorization_unit:'page',revision_unit:'page'};return '<form id="progressForm" class="halaqat-form"><div class="halaqat-form-grid">'+input('day','اليوم',today(),'date',true,'max="'+today()+'"')+select('attendance','الحضور',Object.entries(attendance),'present')+input('memorized','ما تم حفظه (السورة والآيات)','','text',false)+input('memorized_amount','مقدار الحفظ المنجز',0,'number',true,'min="0" max="1000" step="0.5"')+select('memorized_unit','وحدة الحفظ',[['page','وجه'],['ayah','آية']],p.memorization_unit)+input('revision','ما تمت مراجعته','','text',false)+input('revision_amount','مقدار المراجعة المنجز',0,'number',true,'min="0" max="1000" step="0.5"')+select('revision_unit','وحدة المراجعة',[['page','وجه'],['ayah','آية']],p.revision_unit)+input('memorization_score','درجة الحفظ من 10','','number',false,'min="0" max="10"')+input('tajweed_score','درجة التجويد من 10','','number',false,'min="0" max="10"')+input('mistakes','عدد الأخطاء',0,'number',true,'min="0" max="1000"')+input('notes','ملاحظات تظهر لولي الأمر','','text',false)+'</div><p class="small-note">سجل واحد لكل يوم. استخدم «تعديل» من السجل لتصحيح اليوم السابق.</p><button>حفظ التسميع والحضور</button></form>';}
function history(){return file.progress.length?file.progress.map(p=>'<article class="halaqat-card"><h3>'+esc(p.day)+' · '+attendance[p.attendance]+'</h3><p>الحفظ: '+esc(p.memorized||'—')+' ('+p.memorized_amount+' '+unit(p.memorized_unit)+')</p><p>المراجعة: '+esc(p.revision||'—')+' ('+p.revision_amount+' '+unit(p.revision_unit)+')</p><p>الحفظ: '+(p.memorization_score??'—')+'/10 · التجويد: '+(p.tajweed_score??'—')+'/10 · الأخطاء: '+p.mistakes+'</p><p>'+esc(p.notes)+'</p>'+(file.can_edit?button('تعديل','data-progress="'+p.id+'"'):'')+'</article>').join(''):empty('لا توجد سجلات حتى الآن.');}
function exams(){let h=file.exams.map(x=>'<article class="halaqat-card"><h3>'+esc(x.title)+' · '+x.score+'/'+x.total+'</h3><p>'+x.day+(x.next_level?' · المستوى: '+esc(x.next_level):'')+'</p><p>'+esc(x.notes)+'</p></article>').join('')||empty('لا توجد اختبارات مسجلة.');if(file.can_edit)h+='<details><summary>تسجيل اختبار وترقية مستوى</summary><form id="examForm" class="halaqat-form">'+input('title','اسم الاختبار')+input('day','التاريخ',today(),'date',true,'max="'+today()+'"')+input('score','الدرجة','','number',true,'min="0" step="0.5"')+input('total','الدرجة الكاملة',100,'number',true,'min="1" max="1000" step="0.5"')+input('next_level','المستوى الجديد (اختياري)','','text',false)+input('notes','ملاحظات','','text',false)+'<button>حفظ الاختبار</button></form></details>';return h;}
function certificates(){let h=file.certificates.map(c=>'<article class="halaqat-card"><h3>'+esc(c.title)+'</h3><p>'+esc(c.achievement)+'</p><p>'+esc(c.issued_on)+'</p><a class="halaqat-btn" href="'+esc(c.url)+'" target="_blank" rel="noopener">عرض وطباعة الشهادة</a></article>').join('')||empty('لا توجد شهادات بعد.');if(file.can_certify)h+='<details><summary>إصدار شهادة إنجاز</summary><form id="certificateForm" class="halaqat-form">'+input('title','عنوان الشهادة','شهادة إنجاز')+input('achievement','الإنجاز المستحق للشهادة')+'<button>إصدار الشهادة</button></form></details>';return h;}
function renderBaseFile(){
 const s=file.student,w=file.weekly,weekly=w?'<p>الحفظ المنجز: '+w.memorization_done+' '+unit(w.memorization_unit)+'، والمستهدف: '+w.memorization_target+'</p><p>المراجعة المنجزة: '+w.revision_done+' '+unit(w.revision_unit)+'، والمستهدف: '+w.revision_target+'</p><small>من '+w.from+'؛ تُجمع المقادير المسجلة بوحدة الخطة نفسها، دون تحويل تلقائي بين الأوجه والآيات.</small>':empty('حدّد الخطة لعرض الهدف الأسبوعي.');
 $('#studentFile').hidden=false;$('#studentFile').innerHTML='<header class="student-file-head"><div><small>ملف الطالب</small><h1>'+esc(s.name)+'</h1><p>'+esc(s.ring)+' · '+esc(s.level)+'</p></div><div class="actions">'+button(data.user.account_type==='guardian'?'العودة للأبناء':'العودة للطلاب','data-back')+'<a class="halaqat-btn secondary" href="'+base()+'/students/'+sid+'/report.csv">تصدير التقرير CSV</a></div></header><div class="halaqat-grid">'+panel('بيانات الطالب','<p>ولي الأمر: '+esc(s.guardian_name||'غير مسجل')+' · '+esc(s.guardian_relation||'')+'</p><p>الجوال: '+esc(s.guardian_phone||'غير مسجل')+'</p><p>تاريخ الميلاد: '+esc(s.birth_date||'غير مسجل')+' · الصف: '+esc(s.school_grade||'غير مسجل')+'</p><p>الحفظ عند التسجيل: '+esc(s.current_memorization||'غير مسجل')+'</p><p>موعد الحلقة: '+esc(s.schedule)+'</p><p class="'+(file.absence_alert?'absence-alert':'')+'">الغياب المسجل خلال 30 يومًا: '+file.absences_30_days+(file.absence_alert?' · يحتاج متابعة':'')+'</p>')+panel('خطة الحفظ والمراجعة',planSummary()+(file.can_edit?'<details><summary>تعديل خطة الطالب</summary>'+planEditor()+'</details>':''))+panel('الإنجاز الأسبوعي',weekly)+(file.can_edit?panel('تسجيل التسميع والتقييم',progressForm()):'')+panel('سجل الحضور والتسميع',history())+panel('الاختبارات والمستوى',exams())+panel('الشهادات',certificates())+'</div>';
 document.querySelectorAll('#planForm [name$="_preset"]').forEach(syncQuantity);
}
async function openFile(id,scroll=true){sid=Number(id);file=await api(base()+'/students/'+sid+'/file');follow=await api(base()+'/students/'+sid+'/followup');studentDev=await api(base()+'/students/'+sid+'/development');studentLearning=await api(base()+'/students/'+sid+'/learning');thread=await api(base()+'/students/'+sid+'/messages');if(thread.messages.length)await api(base()+'/students/'+sid+'/messages/read',{last_id:thread.messages.at(-1).id});$('#halaqatWorkspace').hidden=true;renderFile();status('ملف '+file.student.name);if(scroll)$('#studentFile').scrollIntoView({behavior:'smooth',block:'start'});}
function syncQuantity(el){const prefix=el.name.replace('_preset',''),amount=el.form.elements[prefix+'_amount'],fixed=['0.5','1','2'].includes(el.value);amount.readOnly=fixed;amount.min=el.value==='ayah'?'1':'0.5';amount.step=el.value==='ayah'?'1':'0.5';if(fixed)amount.value=el.value;if(el.value==='ayah'&&(!Number.isInteger(Number(amount.value))||Number(amount.value)<1))amount.value=1;}
async function submit(f){
 const formData=new FormData(f),p=Object.fromEntries(formData.entries()),b=base();
 if(await submitExtra(f,p))return;
 if(f.id==='supervisorForm'){credentials(await api(b+'/supervisors',p));await load();}
 else if(f.id==='ringForm'){p.supervisor_ids=formData.getAll('supervisor_ids').map(Number);await api(b+'/rings',p);await load();}
 else if(['teacherRequestForm','studentRequestForm'].includes(f.id)){p.halaqa_id=Number(p.halaqa_id);if('birth_date' in p&&!p.birth_date)p.birth_date=null;await api(b+'/requests/'+(f.dataset.editId|| (f.id==='teacherRequestForm'?'teacher':'student')),p,f.dataset.editId?'PUT':'POST');await load();}
 else if(f.matches('.approval-form')){p.existing_user_id=p.existing_user_id?Number(p.existing_user_id):null;if(!p.existing_user_id&&!p.username.trim())throw Error('اكتب اسم المستخدم للحساب الجديد');credentials(await api(b+'/requests/'+f.dataset.requestId+'/approve',p));await load();}
 else if(f.id==='planForm'){
 for(const prefix of ['memorization','revision']){p[prefix+'_unit']=p[prefix+'_preset']==='ayah'?'ayah':'page';delete p[prefix+'_preset'];p[prefix+'_amount']=Number(p[prefix+'_amount']);}
 p.sessions_per_week=Number(p.sessions_per_week);p.start_ayah=p.start_ayah?Number(p.start_ayah):null;p.end_ayah=p.end_ayah?Number(p.end_ayah):null;
 await api(b+'/students/'+sid+'/plan',p,'PUT');await openFile(sid,false);
 }else if(f.id==='progressForm'){
 for(const k of ['memorized_amount','revision_amount','mistakes'])p[k]=Number(p[k]);for(const k of ['memorization_score','tajweed_score'])p[k]=p[k]===''?null:Number(p[k]);
 if(file.progress.some(x=>x.day===p.day)&&!confirm('يوجد سجل لهذا اليوم. هل تريد حفظ التعديلات عليه؟'))return;
 await api(b+'/students/'+sid+'/progress',p);await openFile(sid,false);
 }else if(f.id==='examForm'){p.score=Number(p.score);p.total=Number(p.total);await api(b+'/students/'+sid+'/exams',p);await openFile(sid,false);}
 else if(f.id==='certificateForm'){await api(b+'/students/'+sid+'/certificates',p);await openFile(sid,false);}
 status('تم الحفظ بنجاح');
}
document.addEventListener('submit',e=>{if(['supervisorForm','ringForm','teacherRequestForm','studentRequestForm','planForm','progressForm','examForm','certificateForm','profileForm','recipientForm','transferForm','batchForm','assignmentForm','appointmentForm','featuresForm'].includes(e.target.id)||e.target.matches('.approval-form,.assignment-result')){e.preventDefault();run(()=>submit(e.target));}});
document.addEventListener('change',e=>{if(e.target.name?.endsWith('_preset'))syncQuantity(e.target);});
document.addEventListener('input',e=>{if(e.target.id==='studentSearch')document.querySelectorAll('[data-student-name]').forEach(x=>x.hidden=!x.dataset.studentName.includes(e.target.value));});
document.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.hasAttribute('data-hide-credentials')){$('#halaqatCredentials').hidden=true;$('#halaqatCredentials').textContent='';return;}
 if(b.hasAttribute('data-back')){$('#studentFile').hidden=true;$('#halaqatWorkspace').hidden=false;run(load);return;}
 if(b.dataset.file){run(()=>openFile(b.dataset.file));return;}
 if(b.dataset.progress){const p=file.progress.find(x=>x.id===Number(b.dataset.progress)),f=$('#progressForm');for(const [k,v] of Object.entries(p))if(f.elements[k])f.elements[k].value=v??'';f.scrollIntoView({behavior:'smooth'});return;}
 if(b.dataset.reject)run(async()=>{const note=prompt('سبب الرفض:','');if(note===null)return;await api(base()+'/requests/'+b.dataset.reject+'/reject',{note});await load();});
 if(b.dataset.reset)run(async()=>{if(!confirm('إصدار رمز جديد يلغي جلسات الدخول الحالية للحساب. متابعة؟'))return;credentials(await api(base()+'/users/'+b.dataset.reset+'/reset',{}));await load();});
});
// Version 14: owner views, reviewed enrollment and student follow-up.
const recipientOptions=[['student','الطالب نفسه'],['guardian','ولي الأمر']];
const featureNames={assignments:'الورد القادم',notifications:'التنبيهات داخل النظام',rewards:'النقاط والشارات',monthly_reports:'التقارير الشهرية PDF'};
const wardStates={pending:'بانتظار التسميع',completed:'مكتمل',partial:'جزئي',not_done:'لم ينجز'};
function accountFields(student=false){
 return input('full_name',student?'اسم الطالب الرباعي':'اسم المدرس','','text',true,'minlength="2" maxlength="180"')+select('halaqa_id','الحلقة',ringOpts())+(student?select('recipient_type','من يتابع التقارير؟',recipientOptions,'student')+input('national_id','رقم الهوية (اختياري)','','text',false,'maxlength="30" inputmode="numeric"')+input('birth_date','تاريخ الميلاد','','date',false)+input('school_grade','الصف الدراسي','','text',false,'maxlength="120"')+input('current_memorization','الحفظ الحالي','','text',false,'maxlength="250"')+'<div class="guardian-fields" hidden>'+input('guardian_name','اسم ولي الأمر','','text',false,'maxlength="180"')+input('guardian_relation','صلة القرابة','الأب','text',false,'maxlength="60"')+input('guardian_phone','جوال ولي الأمر','','tel',false,'maxlength="40"')+'</div><small>يراجع المالك الملف ويختار حساب ولي الأمر الموجود أو ينشئ حسابًا جديدًا عند الاعتماد.</small>':'')+input('notes','ملاحظات داخلية','','text',false,'maxlength="1000"');
}
function recipientAccounts(type,currentId=0){return (monitor?.recipients||[]).filter(u=>type==='guardian'?u.account_type==='guardian':u.account_type!=='guardian'&&(!u.children?.length||u.id===currentId)).map(u=>[u.id,u.name+' — '+u.username+(u.role==='owner'?' (حسابي الشخصي)':u.children?.length?' — '+u.children.map(c=>c.name).join('، '):'')]);}
function approvalForm(r){return '<form class="halaqat-form approval-form" data-request-id="'+r.id+'">'+(r.type==='student'?select('existing_user_id',r.recipient_type==='guardian'?'حساب ولي الأمر':'حساب الطالب',[['','إنشاء حساب جديد'],...recipientAccounts(r.recipient_type)],'',false):'')+input('username','اسم المستخدم للحساب الجديد','','text',false,'maxlength="30"')+input('temporary_password','كلمة المرور المؤقتة (فارغة = توليد آمن)','','password',false,'minlength="8" maxlength="128" autocomplete="new-password"')+'<div class="actions"><button>اعتماد الملف</button>'+(r.type==='student'?button('إرجاع للاستكمال','data-return="'+r.id+'"'):'')+button('رفض','data-reject="'+r.id+'"')+'</div></form>';}
function requests(){return data.requests.length?data.requests.map(r=>'<article class="halaqat-card"><span class="halaqat-badge">'+esc(states[r.status])+'</span><h3>'+esc(r.full_name)+'</h3><p>'+(r.type==='teacher'?'مدرس':'طالب · المتابع: '+(r.recipient_type==='guardian'?'ولي الأمر':'الطالب نفسه'))+' · '+esc(r.ring)+'</p>'+requestDetails(r)+'<p>مقدم الطلب: '+esc(r.requested_by?.name)+'</p><p>'+esc(r.notes)+'</p>'+(r.review_note?'<p class="review-note">ملاحظة المراجعة: '+esc(r.review_note)+'</p>':'')+(r.type==='student'&&['pending','returned'].includes(r.status)&&(data.user.role==='owner'||r.requested_by?.id===data.user.id)?button('تعديل واستكمال الملف','data-amend="'+r.id+'"'):'')+(data.user.role==='owner'&&r.status==='pending'?approvalForm(r):'')+'</article>').join(''):empty('لا توجد طلبات.');}
function syncRecipient(form){const box=form.querySelector('.guardian-fields');if(box){const isGuardian=form.elements.recipient_type.value==='guardian';box.hidden=!isGuardian;form.elements.guardian_name.required=isGuardian;}}
function batchRows(){const f=$('#batchForm');if(!f)return;const rid=Number(f.elements.ring.value),day=f.elements.day.value;$('#batchRows').innerHTML=data.students.filter(s=>s.halaqa_id===rid).map(s=>{const old=data.progress.find(p=>p.student_id===s.id&&p.day===day);return select('attendance_'+s.id,s.name,[['','دون تغيير'],...Object.entries(attendance)],old?.attendance||'',false);}).join('')||empty('لا يوجد طلاب في هذه الحلقة.');}
function renderDashboard(){
 renderBaseDashboard();let extra='';
 let view=$('#portalViewBox');if(!view){view=document.createElement('div');view.id='portalViewBox';$('.halaqat-toolbar').prepend(view);}view.innerHTML=data.user.original_role==='owner'?select('portalView','واجهتي',[['owner','المطور والمالك'],['supervisor','المشرف'],['student','ملفي كطالب']],portalView):'';
 if(data.user.role==='owner')extra+=panel('إدارة الميزات','<form id="featuresForm" class="halaqat-form">'+Object.entries(featureNames).map(([k,v])=>'<label class="toggle-label"><input type="checkbox" name="'+k+'" '+(monitor.features[k]?'checked':'')+'> '+v+'</label>').join('')+'<button>حفظ إعدادات الميزات</button></form><p>لإضافة نفسك طالبًا: جهّز ملف طالب، اختر «الطالب نفسه»، ثم اربطه بحسابك الشخصي عند الاعتماد.</p>');
 if(monitor.features.notifications)extra+=panel('التنبيهات',monitor.alerts.length?monitor.alerts.map(a=>'<div class="notice '+(a.read?'is-read':'')+'"><strong>'+esc(a.student)+'</strong><p>'+esc(a.message)+'</p><div class="actions">'+button('فتح الملف','data-file="'+a.student_id+'"')+(a.read?'<small>تم الاطلاع</small>':button('تم الاطلاع','data-read="'+esc(a.key)+'"'))+'</div></div>').join(''):empty('لا توجد تنبيهات حاليًا.'));
 if(data.user.role!=='halaqa_student'){
 extra+=panel('لوحة المتابعة','<h3>طلاب يحتاجون متابعة</h3>'+(monitor.struggling.map(s=>'<div class="student-row"><span>'+esc(s.name)+' · '+esc(s.reason)+'</span>'+button('متابعة','data-file="'+s.id+'"')+'</div>').join('')||empty('لا يوجد طلاب ضمن مؤشرات المتابعة حاليًا.'))+'<h3>سجلات حضور غير مكتملة اليوم</h3>'+(monitor.missing_attendance.map(r=>'<p>'+esc(r.name)+': '+r.missing+' طالب دون سجل</p>').join('')||empty('لا توجد سجلات ناقصة.'))+'<small>تظهر الحلقات ذات اللقاء المحدد اليوم فقط. حدّد جدول اللقاءات أدناه؛ الأيام غير المسجلة لا تحتسب غيابًا.</small><p>طلبات بانتظار المراجعة: '+data.stats.pending_requests+'</p>');
 extra+=panel('التحضير الجماعي','<form id="batchForm" class="halaqat-form">'+select('ring','الحلقة',data.rings.map(r=>[r.id,r.name]))+input('day','التاريخ',today(),'date',true,'max="'+today()+'"')+button('تحديد الجميع حاضرًا','data-all-present')+'<div id="batchRows"></div><button>حفظ التحضير</button><small>يُحفظ الحضور مع بقاء بيانات التسميع السابقة.</small></form>');
 }
 $('#halaqatWorkspace .halaqat-grid').insertAdjacentHTML('afterbegin',extra);batchRows();
 const sf=$('#studentRequestForm');if(sf)syncRecipient(sf);renderDevelopmentDashboard();
}
function renderFile(){
 renderBaseFile();const s=file.student;let extra='';
 if(follow.features.assignments){
  extra+=panel('الورد القادم وسجل الأوراد',follow.assignments.map(a=>'<article class="halaqat-card"><h3>'+esc(a.due)+' · '+wardStates[a.status]+'</h3><p>الحفظ: '+esc(a.memorization||'—')+'</p><p>المراجعة: '+esc(a.revision||'—')+'</p><p>'+esc(a.instructions)+'</p><p>'+esc(a.result_note)+'</p>'+(file.can_edit?'<form class="halaqat-form assignment-result" data-id="'+a.id+'">'+select('status','نتيجة التسميع',Object.entries(wardStates),a.status)+input('result_note','ملاحظة الشيخ',a.result_note,'text',false,'maxlength="1000"')+'<button>حفظ نتيجة الورد</button></form>':'')+'</article>').join('')||empty('لم يُحدد الورد القادم بعد.'));
  if(file.can_edit)extra+=panel('تحديد ورد جديد','<form id="assignmentForm" class="halaqat-form">'+input('due','موعد التسميع',today(),'date')+input('memorization','ورد الحفظ: السورة والآيات أو الصفحات','','text',false,'maxlength="1000" placeholder="مثال: البقرة، الآيات 1–5"')+input('revision','ورد المراجعة: السورة والآيات أو الصفحات','','text',false,'maxlength="1000"')+input('instructions','تعليمات للطالب وولي الأمر','','text',false,'maxlength="1000"')+'<button>حفظ الورد القادم</button><small>حدد الحفظ أو المراجعة على الأقل. يُسجل الإنجاز الكمي من نموذج التسميع.</small></form>');
 }
 if(follow.rewards)extra+=panel('النقاط والشارات','<p class="points">'+follow.rewards.points+' نقطة</p><p>'+follow.rewards.badges.map(b=>'<span class="reward-badge">'+esc(b)+'</span>').join(' ')+'</p><small>نقطتان لكل يوم حضور و5 نقاط لكل ورد مكتمل. تصحيح السجل يصحح النقاط تلقائيًا.</small>');
 extra+=panel('الاختبارات القادمة',follow.appointments.map(a=>'<p><strong>'+esc(a.title)+'</strong> · '+esc(a.due)+'<br>'+esc(a.notes)+'</p>').join('')||empty('لا يوجد اختبار قادم محدد.'));
 if(file.can_edit)extra+=panel('تحديد موعد اختبار','<form id="appointmentForm" class="halaqat-form">'+input('title','عنوان الاختبار','','text',true,'minlength="2" maxlength="180"')+input('due','موعد الاختبار',today(),'date',true,'min="'+today()+'"')+input('notes','تعليمات الاختبار','','text',false,'maxlength="1000"')+'<button>حفظ الموعد</button></form>');
 if(follow.features.monthly_reports)extra+=panel('التقرير الشهري PDF',input('reportMonth','الشهر',today().slice(0,7),'month',true,'id="reportMonth"')+'<a id="monthlyDownload" class="halaqat-btn">تنزيل تقرير الشهر</a>');
 if(file.can_edit)extra+=panel('تعديل بيانات الطالب','<form id="profileForm" class="halaqat-form">'+input('full_name','اسم الطالب',s.name,'text',true,'minlength="2" maxlength="180"')+input('national_id','رقم الهوية',s.national_id||'','text',false,'maxlength="30" inputmode="numeric"')+input('birth_date','تاريخ الميلاد',s.birth_date||'','date',false)+input('school_grade','الصف الدراسي',s.school_grade,'text',false,'maxlength="120"')+input('current_memorization','الحفظ عند التسجيل',s.current_memorization,'text',false,'maxlength="250"')+input('guardian_name','اسم ولي الأمر',s.guardian_name,'text',s.recipient_type==='guardian','maxlength="180"')+input('guardian_phone','جوال ولي الأمر',s.guardian_phone,'tel',false,'maxlength="40"')+input('guardian_relation','صلة القرابة',s.guardian_relation,'text',false,'maxlength="60"')+input('notes','ملاحظات داخلية',s.notes,'text',false,'maxlength="1000"')+'<button>حفظ بيانات الطالب</button></form>');
 if(data.user.role==='owner'&&s.active)extra+=panel('إدارة ربط الحساب','<form id="recipientForm" class="halaqat-form">'+select('recipient_type','متابع التقارير',recipientOptions,s.recipient_type)+select('user_id','الحساب المرتبط',recipientAccounts(s.recipient_type,s.user_id),s.user_id)+'<button>حفظ ربط الحساب</button><small>تنتقل صلاحية الاطلاع للحساب المحدد. لإصدار حساب جديد استخدم النموذج أدناه؛ المالك وحده يصدر بيانات الدخول.</small></form><details><summary>إصدار حساب جديد لهذا الطالب أو ولي أمره</summary><form id="newRecipientForm" class="halaqat-form">'+select('recipient_type','نوع الحساب',recipientOptions,s.recipient_type)+input('full_name','اسم صاحب الحساب',s.recipient_type==='guardian'?s.guardian_name:s.name,'text',true,'minlength="2" maxlength="180"')+input('username','اسم المستخدم','','text',true,'minlength="3" maxlength="30"')+input('temporary_password','كلمة المرور المؤقتة (اختياري)','','password',false,'minlength="8" maxlength="128"')+'<button>إصدار الحساب وربط الطالب</button></form></details>');
 if(s.active&&['owner','halaqa_supervisor'].includes(data.user.role))extra+=panel('نقل الطالب إلى حلقة أخرى','<form id="transferForm" class="halaqat-form">'+select('halaqa_id','الحلقة',data.rings.map(r=>[r.id,r.name]),s.halaqa_id)+'<button>نقل مع الاحتفاظ بالسجل</button></form>');
 $('#studentFile .halaqat-grid').insertAdjacentHTML('afterbegin',extra);
 $('#studentFile').querySelectorAll('a[href]').forEach(a=>{const u=new URL(a.href);u.searchParams.set('view',portalView);a.href=u.pathname+u.search;});syncMonthly();renderDevelopmentFile();renderLearningFile();
}
function syncMonthly(){if($('#monthlyDownload'))$('#monthlyDownload').href=base()+'/students/'+sid+'/monthly.pdf?month='+encodeURIComponent($('#reportMonth').value)+'&view='+portalView;}
async function submitExtra(f,p){
 const url=base()+'/students/'+sid;let handled=true;
 if(f.id==='profileForm'){p.birth_date=p.birth_date||null;await api(url+'/profile',p,'PUT');}
 else if(f.id==='recipientForm'){p.user_id=Number(p.user_id);await api(url+'/recipient',p,'PUT');}
 else if(f.id==='newRecipientForm'){credentials(await api(url+'/recipient-account',p));}
 else if(f.id==='transferForm'){p.halaqa_id=Number(p.halaqa_id);await api(url+'/transfer',p);}
 else if(f.id==='assignmentForm')await api(url+'/assignments',p);
 else if(f.matches('.assignment-result'))await api(url+'/assignments/'+f.dataset.id,p,'PUT');
 else if(f.id==='appointmentForm')await api(url+'/exam-appointments',p);
 else if(f.id==='batchForm'){const rows=Object.entries(p).filter(([k,v])=>k.startsWith('attendance_')&&v).map(([k,v])=>({student_id:Number(k.slice(11)),attendance:v}));if(!rows.length)throw Error('حدد حضور طالب واحد على الأقل');await api(base()+'/attendance/batch',{day:p.day,rows});await load();status('تم حفظ التحضير');return true;}
 else if(f.id==='featuresForm'){await api(base()+'/features',Object.fromEntries(Object.keys(featureNames).map(k=>[k,f.elements[k].checked])),'PUT');await load();status('تم حفظ إعدادات الميزات');return true;}
 else handled=false;
 if(handled){monitor=await api(base()+'/monitor');await openFile(sid,false);status('تم الحفظ بنجاح');}return handled;
}
document.addEventListener('submit',e=>{if(e.target.id==='newRecipientForm'){e.preventDefault();run(()=>submit(e.target));}});
document.addEventListener('change',e=>{
 if(e.target.name==='portalView')run(async()=>{portalView=e.target.value;$('#halaqatCredentials').hidden=true;$('#halaqatCredentials').textContent='';await load();});
 if(e.target.name==='recipient_type'){
  if(e.target.form?.id==='studentRequestForm')syncRecipient(e.target.form);
  if(e.target.form?.id==='recipientForm'){const el=e.target.form.elements.user_id;el.innerHTML=recipientAccounts(e.target.value,file.student.user_id).map(([v,t])=>'<option value="'+v+'">'+esc(t)+'</option>').join('');}
 }
 if(e.target.form?.id==='batchForm'&&['day','ring'].includes(e.target.name))batchRows();
 if(e.target.id==='reportMonth')syncMonthly();
});
document.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.hasAttribute('data-all-present'))$('#batchRows').querySelectorAll('select').forEach(s=>s.value='present');
 if(b.dataset.return)run(async()=>{const note=prompt('ما المعلومات المطلوب استكمالها؟');if(note===null)return;await api(base()+'/requests/'+b.dataset.return+'/return',{note});await load();});
 if(b.dataset.read)run(async()=>{await api(base()+'/alerts/read',{key:b.dataset.read});await load();});
 if(b.dataset.amend){const r=data.requests.find(r=>r.id===Number(b.dataset.amend)),f=$('#studentRequestForm');f.dataset.editId=r.id;for(const [k,v] of Object.entries(r))if(f.elements[k])f.elements[k].value=v??'';syncRecipient(f);f.querySelector('button').textContent='حفظ وإعادة رفع الطلب';f.scrollIntoView({behavior:'smooth'});}
});

// Version 15 modules share the established authenticated API and role-scoped views.
let development=null,studentDev=null,thread=null,orgOverview=null,importPreview=null;
const dayNames=['الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت','الأحد'];
const dateTime=x=>new Date(x).toLocaleString('ar-SA',{timeZone:'Asia/Riyadh',dateStyle:'short',timeStyle:'short'});
const fold=(title,body)=>'<details class="development-fold"><summary>'+title+'</summary>'+body+'</details>';
const form15=(id,body,attrs='')=>'<form id="'+id+'" data-v15 class="halaqat-form" '+attrs+'>'+body+'</form>';
const textArea=(name,label,value='',max=3000)=>'<label>'+label+'<textarea name="'+name+'" maxlength="'+max+'" required rows="3">'+esc(value)+'</textarea></label>';
function renderDevelopmentDashboard(){
 let html='';const role=data.user.role,staff=role!=='halaqa_student',manager=['owner','halaqa_supervisor'].includes(role);
 html+=panel('إعلانات الحلقة',development.announcements.map(a=>'<article class="halaqat-card"><h3>'+esc(a.title)+'</h3><small>'+esc(a.ring)+(a.expires?' · حتى '+esc(a.expires):'')+'</small><p class="preserve-lines">'+esc(a.body)+'</p>'+(a.can_archive?button('أرشفة الإعلان','data-announcement-archive="'+a.id+'"'):'')+'</article>').join('')||empty('لا توجد إعلانات حالية.'));
 if(staff)html+=panel('نشر إعلان',fold('كتابة إعلان للحلقة',form15('announcementForm',select('halaqa_id','نطاق الإعلان',[(role==='owner'?['','جميع حلقات المسجد']:['','اختر الحلقة']),...data.rings.map(r=>[r.id,r.name])],'',role!=='owner')+input('title','العنوان','','text',true,'minlength="2" maxlength="180"')+textArea('body','نص الإعلان')+input('expires','ينتهي في (اختياري)','','date',false)+'<button>نشر الإعلان داخل النظام</button>')));
 html+=panel('جدول اللقاءات والإجازات',development.calendars.map(c=>'<article class="halaqat-card"><h3>'+esc(c.name)+'</h3><p>'+(c.configured?c.weekdays.map(d=>dayNames[d]).join('، ')||'لا توجد لقاءات أسبوعية':'لم يحدد الجدول بعد')+' · '+esc(c.time_text)+'</p><p>اليوم: '+(c.today_held?'يوجد لقاء':'لا يوجد لقاء محدد')+'</p>'+c.exceptions.map(x=>'<p>'+x.day+' · '+(x.held?'لقاء استثنائي':'إجازة / إلغاء')+' · '+esc(x.reason)+(manager?button('إزالة الاستثناء','data-calendar-remove="'+c.id+'" data-day="'+x.day+'"'):'')+'</p>').join('')+(manager?fold('تعديل الجدول والإجازات',form15('calendarForm'+c.id,'<fieldset><legend>أيام اللقاءات</legend>'+dayNames.map((d,i)=>'<label class="toggle-label"><input name="weekdays" type="checkbox" value="'+i+'" '+(c.weekdays.includes(i)?'checked':'')+'>'+d+'</label>').join('')+'</fieldset>'+input('time_text','وقت الحلقة',c.time_text,'text',false,'maxlength="100"')+'<button>حفظ الجدول</button>','data-kind="calendar" data-ring="'+c.id+'"')+form15('exceptionForm'+c.id,input('day','تاريخ الاستثناء',today(),'date')+select('held','نوع الاستثناء',[['false','إجازة أو إلغاء اللقاء'],['true','إضافة لقاء استثنائي']])+input('reason','السبب','','text',false,'maxlength="500"')+'<button>حفظ الاستثناء</button>','data-kind="exception" data-ring="'+c.id+'"')):'')+'</article>').join('')||empty('لا توجد حلقات متاحة.'));
 html+=panel('المراسلات الجديدة',development.unread.map(x=>'<div class="student-row"><span>'+esc(x.name)+' · '+x.count+' رسالة</span>'+button('فتح الملف','data-file="'+x.id+'"')+'</div>').join('')||empty('لا توجد رسائل غير مقروءة.'));
 html+=panel('الاختبارات المنظمة القادمة',development.upcoming_exams.map(x=>'<div class="student-row"><span>'+esc(x.name)+' · '+esc(x.title)+' · '+x.due+'</span>'+button('التفاصيل','data-file="'+x.student_id+'"')+'</div>').join('')||empty('لا توجد اختبارات منظمة قادمة.'));
 if(manager){html+=panel('اعتذارات بانتظار المراجعة',development.pending_excuses.map(x=>'<div class="halaqat-card"><strong>'+esc(x.name)+'</strong><p>'+x.day+' · '+esc(x.reason)+'</p>'+button('مراجعة العذر','data-file="'+x.student_id+'"')+'</div>').join('')||empty('لا توجد اعتذارات معلقة.'));
 html+=panel('الطلاب المؤرشفون',fold('عرض الأرشيف ('+development.archived_students.length+')',development.archived_students.map(s=>'<div class="student-row"><span>'+esc(s.name)+'</span><div class="actions">'+button('عرض السجل','data-file="'+s.id+'"')+button('استعادة الطالب','data-student-archive="'+s.id+'" data-active="true"')+'</div></div>').join('')||empty('الأرشيف فارغ.')));}
 if(staff)html+=panel('استيراد الطلاب من Excel',fold('رفع ملف ومعاينته','<a class="halaqat-btn" href="'+base()+'/imports/template.xlsx?view='+portalView+'">تنزيل القالب</a><p>حتى 300 طالب. تظهر الأخطاء والتكرارات قبل الحفظ؛ الصفوف المعتمدة تصبح طلبات يراجعها المالك.</p>'+form15('importForm',select('halaqa_id','الحلقة',ringOpts())+input('file','ملف Excel','','file',true,'accept=".xlsx"')+'<button>معاينة الملف</button>')+'<div id="importPreview"></div>'));
 if(role==='owner'){
 html+=panel('إدارة المساجد',fold('المساجد والإحصاءات',(orgOverview?.mosques||[]).map(m=>'<div class="student-row"><span>'+esc(m.name)+' · '+m.rings+' حلقات · '+m.students+' طلاب · '+m.pending+' طلبات</span>'+button('فتح المسجد','data-open-mosque="'+m.id+'"')+'</div>').join('')+form15('mosqueCreateForm',input('name','اسم مسجد جديد','','text',true,'minlength="2" maxlength="180"')+'<button>إضافة مسجد</button>')+form15('mosqueRenameForm',input('name','اسم المسجد الحالي',data.mosque.name,'text',true,'minlength="2" maxlength="180"')+'<button>حفظ الاسم</button>')));
 html+=panel('أرشفة الحسابات واستعادتها',fold('إدارة دخول المستخدمين',data.accounts.map(u=>'<div class="student-row"><span>'+esc(u.name)+' · '+(u.active?'فعال':'مؤرشف')+'</span>'+button(u.active?'أرشفة الحساب':'استعادة الحساب','data-account-archive="'+u.id+'" data-active="'+!u.active+'"')+'</div>').join('')+'<small>أرشفة الحساب توقف دخوله وتلغي جلساته. أرشفة الطالب إجراء مستقل؛ لا تحذف سجلاته أو ملفات إخوته.</small>'));
 html+=panel('سجل التعديلات',button('عرض أحدث التعديلات','data-audit-load="0"')+'<div id="auditRows"></div>');
 }
 $('#halaqatWorkspace .halaqat-grid').insertAdjacentHTML('beforeend',html);
}
function quranCards(){const filter=$('#quranFilter')?.value||'';$('#quranMap').innerHTML=studentDev.quran.filter(x=>!filter||x.status===filter).map(x=>'<article class="quran-cell state-'+x.status+'"><strong>'+x.number+'. '+esc(x.name)+'</strong><span>'+studentDev.quran_states[x.status]+'</span>'+(x.notes?'<small>'+esc(x.notes)+'</small>':'')+(x.approved_by?'<small>اعتماد: '+esc(x.approved_by)+'</small>':'')+'</article>').join('');}
function renderDevelopmentFile(){
 let html='';const s=file.student,manager=['owner','halaqa_supervisor'].includes(data.user.role);
 const counts=Object.entries(studentDev.quran_states).map(([k,v])=>'<span class="reward-badge">'+v+': '+studentDev.quran.filter(x=>x.status===k).length+'</span>').join('');
 html+=panel('خريطة إنجاز القرآن',counts+'<p>حالة السورة كاملة باعتماد الشيخ؛ يذكر الجزء المحفوظ من السورة في الملاحظات عند «قيد الحفظ».</p>'+fold('عرض السور الـ114',select('quranFilter','تصفية الحالات',[['','جميع السور'],...Object.entries(studentDev.quran_states)],'',false).replace('name="quranFilter"','id="quranFilter"')+'<div id="quranMap" class="quran-grid"></div>')+(file.can_edit?fold('تحديث سورة باعتماد الشيخ',form15('quranForm',select('surah','السورة',studentDev.quran.map(x=>[x.number,x.name]))+select('status','الحالة',Object.entries(studentDev.quran_states))+input('notes','نطاق الحفظ أو ملاحظات','','text',false,'maxlength="1000"')+'<button>اعتماد حالة السورة</button>')):''));
 html+=panel('اعتذارات الغياب',studentDev.excuses.map(x=>'<article class="halaqat-card"><h3>'+x.day+' · '+({pending:'بانتظار المراجعة',approved:'مقبول',rejected:'مرفوض'}[x.status])+'</h3><p>'+esc(x.reason)+'</p><p>'+esc(x.review_note)+'</p>'+(manager&&s.active&&x.status==='pending'?form15('excuseReview'+x.id,select('status','القرار',[['approved','قبول'],['rejected','رفض']])+input('note','ملاحظة المراجعة','','text',false,'maxlength="1000"')+'<button>حفظ القرار</button>','data-kind="excuseReview" data-id="'+x.id+'"'):'')+'</article>').join('')+(data.user.role==='halaqa_student'&&s.active?form15('excuseForm',input('day','يوم الغياب',today(),'date')+textArea('reason','سبب الاعتذار','',1500)+'<button>إرسال العذر للمشرف</button><small>يجب أن يكون اليوم ضمن جدول لقاءات الحلقة. قبول العذر لا يحتسب حضورًا.</small>'):''));
 html+=panel('مراسلات الطالب', '<p>هذه المحادثة مشتركة بين متابع الطالب الحالي وفريق حلقته والمالك، وتبقى ضمن سجل الطالب عند نقله.</p><div id="messageRows">'+messageRows(thread.messages)+'</div>'+(thread.before?button('رسائل أقدم','data-messages-before="'+thread.before+'"'):'')+(s.active?form15('messageForm',textArea('body','رسالتك')+'<button>إرسال الرسالة</button>'):'<p>الطالب مؤرشف؛ المراسلات للقراءة فقط.</p>'));
 html+=panel('الاختبارات الدورية المنظمة',studentDev.exams.map(examCard).join('')||empty('لا توجد اختبارات منظمة بعد.'));
 if(file.can_edit)html+=panel('إنشاء اختبار منظم',fold('المقرر ومعايير التقييم',form15('organizedExamForm',input('title','عنوان الاختبار','','text',true,'minlength="2" maxlength="180"')+textArea('syllabus','المقرر: السور والآيات أو الصفحات','',2000)+input('due','الموعد',today(),'date')+input('repeat_days','يتكرر بعد الاجتياز كل (يوم)، 0 دون تكرار',0,'number',true,'min="0" max="365"')+input('pass_percent','نسبة الاجتياز',70,'number',true,'min="0" max="100" step="0.5"')+'<div id="examCriteria">'+criterionFields('الحفظ',60)+criterionFields('التجويد',40)+'</div>'+button('إضافة معيار','data-add-criterion')+'<button>إنشاء الاختبار</button>')));
 if(manager)html+=panel('حالة ملف الطالب','<p>'+(s.active?'طالب فعال':'طالب مؤرشف — السجل محفوظ')+'</p>'+button(s.active?'أرشفة الطالب':'استعادة الطالب','data-student-archive="'+sid+'" data-active="'+!s.active+'"'));
 $('#studentFile .halaqat-grid').insertAdjacentHTML('beforeend',html);quranCards();syncQuranForm();
}
function criterionFields(name='',maximum=10){return '<div class="criterion-row">'+input('criterion_name','المعيار',name,'text',true,'minlength="2" maxlength="100"')+input('criterion_max','الدرجة الكاملة',maximum,'number',true,'min="0.5" max="1000" step="0.5"')+button('إزالة','data-remove-criterion')+'</div>';}
function examCard(x){return '<article class="halaqat-card"><h3>'+esc(x.title)+'</h3><p>'+x.due+' · '+({scheduled:'قادم',completed:'تم التقييم',cancelled:'ملغى'}[x.status])+'</p><p>'+esc(x.syllabus)+'</p><p>الاجتياز: '+x.pass_percent+'% · التكرار: '+(x.repeat_days?x.repeat_days+' يوم':'دون تكرار')+'</p>'+x.criteria.map((c,i)=>'<p>'+esc(c.name)+': '+(x.result?x.result.scores[i]:'—')+' / '+c.maximum+'</p>').join('')+(x.result?'<strong>'+(x.result.passed?'اجتاز':'يحتاج إعادة')+'</strong><p>'+esc(x.result.notes)+'</p>':'')+(x.next_exam_id?'<p>موعد متابعة مرتبط بالاختبار رقم '+x.next_exam_id+'</p>':'')+(file.can_edit&&x.status!=='cancelled'?fold(x.result?'تصحيح النتيجة':'تسجيل النتيجة',form15('organizedResult'+x.id,input('day','يوم الاختبار',x.result?.day||today(),'date',true,'max="'+today()+'"')+x.criteria.map((c,i)=>input('score_'+i,c.name,x.result?.scores[i]??'','number',true,'min="0" max="'+c.maximum+'" step="0.5"')).join('')+input('notes','ملاحظات',x.result?.notes||'','text',false,'maxlength="2000"')+input('retake_due','موعد الإعادة عند عدم الاجتياز','','date',false)+'<button>حفظ نتيجة الاختبار</button>','data-kind="organizedResult" data-id="'+x.id+'"'))+(x.status==='scheduled'?button('إلغاء الموعد','data-cancel-exam="'+x.id+'"'):''):'')+'</article>';}
function messageRows(rows){return rows.map(m=>'<article class="message '+(m.mine?'mine':'')+'"><strong>'+esc(m.sender)+'</strong><small>'+esc(dateTime(m.created_at))+'</small><p class="preserve-lines">'+esc(m.body)+'</p></article>').join('')||empty('لا توجد رسائل بعد.');}
function syncQuranForm(){const f=$('#quranForm');if(!f)return;const r=studentDev.quran.find(x=>x.number===Number(f.elements.surah.value));f.elements.status.value=r.status;f.elements.notes.value=r.notes;}
async function refreshOrganizations(){const c=await api('/api/halaqat/context');$('#halaqatMosque').innerHTML=c.mosques.map(m=>'<option value="'+m.id+'">'+esc(m.name)+'</option>').join('');$('#halaqatMosque').value=String(mid);}
function showImportPreview(d){importPreview=d;$('#importPreview').innerHTML=form15('importCommitForm','<h3>معاينة الملف</h3>'+d.rows.map(r=>'<article class="halaqat-card"><label class="toggle-label"><input type="checkbox" name="rows" value="'+r.row+'" '+(r.errors.length?'disabled':'checked')+'> الصف '+r.row+' · '+esc(r.data.full_name)+'</label><p>المتابع: '+(r.data.recipient_type==='guardian'?'ولي الأمر':'الطالب')+' · '+esc(r.data.guardian_name)+' · '+esc(r.data.guardian_phone)+'</p><p>'+esc(r.errors.join('، '))+'</p></article>').join('')+'<button>رفع الصفوف المحددة للمراجعة</button><small>لن يتم إنشاء حسابات قبل اعتماد المالك.</small>');}
async function submitDevelopment(f){
 const fd=new FormData(f),p=Object.fromEntries(fd),url=base()+'/students/'+sid;let dashboard=false;
 if(f.id==='quranForm'){const surah=p.surah;delete p.surah;await api(url+'/quran/'+surah,p,'PUT');}
 else if(f.id==='excuseForm')await api(url+'/excuses',p);
 else if(f.dataset.kind==='excuseReview')await api(url+'/excuses/'+f.dataset.id,p,'PUT');
 else if(f.id==='messageForm')await api(url+'/messages',p);
 else if(f.id==='organizedExamForm'){p.repeat_days=Number(p.repeat_days);p.pass_percent=Number(p.pass_percent);p.criteria=Array.from(f.querySelectorAll('.criterion-row')).map(r=>({name:r.querySelector('[name="criterion_name"]').value,maximum:Number(r.querySelector('[name="criterion_max"]').value)}));delete p.criterion_name;delete p.criterion_max;await api(url+'/organized-exams',p);}
 else if(f.dataset.kind==='organizedResult'){const x=studentDev.exams.find(x=>x.id===Number(f.dataset.id));const payload={day:p.day,notes:p.notes,retake_due:p.retake_due||null,scores:x.criteria.map((_,i)=>Number(p['score_'+i]))};await api(url+'/organized-exams/'+x.id+'/result',payload,'PUT');}
 else if(f.dataset.kind==='calendar'){await api(base()+'/rings/'+f.dataset.ring+'/calendar',{weekdays:fd.getAll('weekdays').map(Number),time_text:p.time_text},'PUT');dashboard=true;}
 else if(f.dataset.kind==='exception'){p.held=p.held==='true';await api(base()+'/rings/'+f.dataset.ring+'/calendar-exception',p,'PUT');dashboard=true;}
 else if(f.id==='announcementForm'){p.halaqa_id=p.halaqa_id?Number(p.halaqa_id):null;p.expires=p.expires||null;await api(base()+'/announcements',p);dashboard=true;}
 else if(f.id==='mosqueCreateForm'){const m=await api('/api/halaqat/organizations',p);mid=m.id;await refreshOrganizations();dashboard=true;}
 else if(f.id==='mosqueRenameForm'){await api(base()+'/organization',p,'PUT');await refreshOrganizations();dashboard=true;}
 else if(f.id==='importForm'){const response=await fetch(base()+'/imports/preview',{method:'POST',headers:{'X-Portal-View':portalView},body:fd});const d=await response.json();if(!response.ok)throw Error(typeof d.detail==='string'?d.detail:'تعذر قراءة الملف');showImportPreview(d);status('راجع الصفوف ثم اعتمد السليم منها');return;}
 else if(f.id==='importCommitForm'){const d=await api(base()+'/imports/commit',{token:importPreview.token,rows:fd.getAll('rows').map(Number)});importPreview=null;await load();status('تم رفع '+d.count+' طلبات للمالك');return;}
 if(dashboard)await load();else await openFile(sid,false);status('تم الحفظ بنجاح');
}
document.addEventListener('submit',e=>{if(e.target.matches('[data-v15]')){e.preventDefault();run(()=>submitDevelopment(e.target));}});
document.addEventListener('change',e=>{if(e.target.id==='quranFilter')quranCards();if(e.target.form?.id==='quranForm'&&e.target.name==='surah')syncQuranForm();});
document.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.hasAttribute('data-add-criterion')){if($('#examCriteria').children.length>=10){status('الحد الأقصى 10 معايير');return;}$('#examCriteria').insertAdjacentHTML('beforeend',criterionFields());}
 if(b.hasAttribute('data-remove-criterion'))b.closest('.criterion-row').remove();
 if(b.dataset.openMosque)run(async()=>{mid=Number(b.dataset.openMosque);$('#halaqatMosque').value=String(mid);await load();});
 if(b.dataset.studentArchive||b.dataset.accountArchive)run(async()=>{const reason=prompt(b.dataset.active==='true'?'سبب الاستعادة:':'سبب الأرشفة:');if(reason===null)return;const path=b.dataset.studentArchive?'/students/'+b.dataset.studentArchive:'/users/'+b.dataset.accountArchive;await api(base()+path+'/archive',{active:b.dataset.active==='true',reason},'PUT');await load();});
 if(b.dataset.announcementArchive)run(async()=>{await api(base()+'/announcements/'+b.dataset.announcementArchive+'/archive',{});await load();});
 if(b.dataset.calendarRemove)run(async()=>{await api(base()+'/rings/'+b.dataset.calendarRemove+'/calendar-exception/'+b.dataset.day,{},'DELETE');await load();});
 if(b.dataset.cancelExam)run(async()=>{await api(base()+'/students/'+sid+'/organized-exams/'+b.dataset.cancelExam+'/cancel',{});await openFile(sid,false);});
 if(b.hasAttribute('data-audit-load'))run(async()=>{const d=await api(base()+'/audit?before='+b.dataset.auditLoad);if(b.dataset.auditLoad==='0')$('#auditRows').innerHTML='';else b.remove();$('#auditRows').insertAdjacentHTML('beforeend',d.rows.map(r=>'<article class="halaqat-card"><strong>'+esc(r.actor)+' · '+esc(r.action)+'</strong><small>'+esc(dateTime(r.at))+'</small><pre class="audit-details">'+esc(auditDetails(r.details))+'</pre></article>').join('')+(d.before?button('تعديلات أقدم','data-audit-load="'+d.before+'"'):''));status('تم تحميل سجل التعديلات');});
 if(b.dataset.messagesBefore)run(async()=>{const d=await api(base()+'/students/'+sid+'/messages?before='+b.dataset.messagesBefore);$('#messageRows').insertAdjacentHTML('afterbegin',messageRows(d.messages));if(d.before)b.dataset.messagesBefore=d.before;else b.remove();status('تم تحميل الرسائل السابقة');});
});
function auditDetails(value){try{const x=JSON.parse(value);return JSON.stringify(x,null,2);}catch{return value;}}

$('#halaqatMosque').onchange=()=>run(async()=>{mid=Number($('#halaqatMosque').value);$('#halaqatWorkspace').hidden=false;await load();});
run(async()=>{const c=await api('/api/halaqat/context');$('#halaqatMosque').innerHTML=c.mosques.map(m=>'<option value="'+m.id+'">'+esc(m.name)+'</option>').join('');mid=c.mosques[0]?.id;if(!mid)throw Error('لا توجد جهة مرتبطة بهذا الحساب');await load();});
// Owner management, reviewed roster and irreversible deletion preview (v16).
let managementTeachers=[],managementSupervisors=[];
function renderManagement(){
 if(data.user.role!=='owner')return;
 let out=panel('تعديل الحلقات والمدرسين',data.rings.map(r=>'<details><summary>'+esc(r.name)+'</summary><form data-manage="ring" data-id="'+r.id+'" class="halaqat-form">'+input('name','اسم الحلقة',r.name)+input('schedule','وصف الموعد',r.schedule,'text',false)+'<fieldset><legend>المشرفون المكلفون بالحلقة</legend><small>التكليف للتنظيم؛ جميع مشرفي المسجد يمكنهم متابعة كل حلقاته.</small>'+data.supervisors.map(u=>'<label><input type="checkbox" name="supervisor_ids" value="'+u.id+'" '+(r.supervisor_ids.includes(u.id)?'checked':'')+'> '+esc(u.name)+'</label>').join('')+'</fieldset><fieldset><legend>المدرسون المرتبطون</legend>'+data.accounts.filter(u=>u.role==='halaqa_teacher'&&u.active).map(u=>'<label><input type="checkbox" name="teacher_ids" value="'+u.id+'" '+(r.teacher_ids.includes(u.id)?'checked':'')+'> '+esc(u.name)+'</label>').join('')+'</fieldset><button>حفظ تعديلات الحلقة</button></form>'+button('معاينة حذف الحلقة بالكامل','data-delete-ring="'+r.id+'"')+'<div id="deleteRing'+r.id+'"></div></details>').join('')||empty('لا توجد حلقات'));
 out+=panel('إدارة المشرفين','<p>كل مشرف فعال يتابع جميع حلقات هذا المسجد وطلابها. إزالة المشرف توقف دخوله وتلغي جلساته وتكليفاته، وتبقي سجلات أعماله محفوظة.</p>'+managementSupervisors.map(u=>'<details><summary>'+esc(u.full_name)+(u.active?'':' — موقوف')+'</summary><form data-manage="supervisor" data-id="'+u.id+'" class="halaqat-form">'+input('full_name','اسم المشرف',u.full_name)+input('username','اسم المستخدم',u.username,'text',true,'minlength="3" maxlength="30"')+input('email','البريد',u.email,'email',false)+input('phone','الجوال',u.phone,'tel',false)+input('notes','ملاحظات',u.notes,'text',false)+'<small>تغيير اسم المستخدم يلغي جلساته الحالية؛ كلمة المرور تبقى كما هي.</small><button>حفظ بيانات المشرف</button></form>'+(u.active?'<form data-manage="remove-supervisor" data-id="'+u.id+'" class="halaqat-form">'+input('confirm_name','اكتب اسم المشرف لتأكيد إزالته')+'<button>إزالة المشرف وإيقاف دخوله</button></form>':'<p>يمكن استعادة الحساب من إدارة أرشفة الحسابات عند الحاجة.</p>')+'</details>').join(''));
 out+=panel('بيانات المدرسين','<p>تعديل الاسم ووسائل الاتصال لا يغيّر اسم المستخدم أو كلمة المرور.</p>'+managementTeachers.map(u=>'<details><summary>'+esc(u.full_name)+'</summary><form data-manage="teacher" data-id="'+u.id+'" class="halaqat-form">'+input('full_name','اسم المدرس',u.full_name)+input('email','البريد الإلكتروني',u.email,'email',false)+input('phone','الجوال',u.phone,'tel',false)+input('notes','ملاحظات',u.notes,'text',false)+'<button>حفظ بيانات المدرس</button></form></details>').join('')+data.requests.filter(q=>q.type==='teacher'&&q.status==='pending').map(q=>'<details><summary>طلب لم يصدر حسابه: '+esc(q.full_name)+'</summary><form data-manage="teacher-request" data-id="'+q.id+'" class="halaqat-form">'+input('full_name','اسم المدرس',q.full_name)+input('email','البريد الإلكتروني',q.email,'email',false)+'<button>تصحيح بيانات الطلب</button></form></details>').join(''));
 out+=panel('إضافة الحلقات الثلاث — 20 طالبًا','<details><summary>مراجعة الأسماء وإضافتها دفعة واحدة</summary><p>الأسماء مطابقة للقائمة النصية التي قدمها المالك: 3 حلقات و20 طالبًا. تاريخ الميلاد والهوية وأرقام الجوال تبقى فارغة لاستكمالها لاحقًا.</p><a class="halaqat-btn secondary" target="_blank" rel="noopener" href="'+base()+'/roster/source">عرض الورقة الأصلية</a><form id="rosterForm" data-manage="roster" class="halaqat-form">'+rosterDraft.map((g,i)=>'<fieldset><legend>المجموعة '+(i+1)+'</legend>'+input('ring_'+i,'اسم الحلقة (قابل للتعديل)',g.name)+input('teacher_'+i,'اسم المدرس — راجعه',g.teacher)+'<label>الطلاب — اسم كامل في كل سطر<textarea name="students_'+i+'" rows="10" required>'+esc(g.students.join('\n'))+'</textarea></label></fieldset>').join('')+'<label><input type="checkbox" name="reviewed" required checked> أؤكد إضافة القائمة إلى المسجد المحدد</label><p>تضاف ملفات الطلاب بلا حسابات. تحدد لاحقًا الطالب أو ولي الأمر من ملفه وتصدر بيانات الدخول. أسماء المدرسين ترفع كطلبات اعتماد لك. لا تضف المجموعة مرة ثانية.</p><button>إضافة الحلقات والطلاب بعد المراجعة</button></form></details>');
 $('#halaqatWorkspace .halaqat-grid').insertAdjacentHTML('beforeend',out);
}
const rosterDraft=[
  {
    "teacher": "اسامه البشري",
    "students": [
      "مشعل عوض عسيري",
      "اوس محمد القحطاني",
      "فراس عبدالخالق الشهري",
      "عبدالعزيز موسى الشهري",
      "طلال عبدالله عسيري",
      "مناف عسيري",
      "سيف علي القحطاني"
    ],
    "name": "حلقة اسامه البشري"
  },
  {
    "teacher": "عبدالرحمن الاسلمي",
    "students": [
      "سلطان عامر علي",
      "ريان عامر علي",
      "البراء محمد القحطاني",
      "طلال عبدالله القحطاني",
      "عزام سعيد عسيري",
      "معاذ مسفر المهجري"
    ],
    "name": "حلقة عبدالرحمن الاسلمي"
  },
  {
    "teacher": "عبدالله ال مقبل",
    "students": [
      "محمد عبدالله القحطاني",
      "تميم بدر الشهري",
      "خالد احمد المهدي",
      "خالد موسى الشهراني",
      "رائد حسن عسيري",
      "عبدالله شايع القحطاني",
      "بسام خالد القحطاني"
    ],
    "name": "حلقة عبدالله ال مقبل"
  }
];
document.addEventListener('submit',e=>{
 const f=e.target;if(!f.dataset.manage)return;e.preventDefault();run(async()=>{
  const fd=new FormData(f),p=Object.fromEntries(fd),kind=f.dataset.manage,id=f.dataset.id;
  if(kind==='ring'){p.teacher_ids=fd.getAll('teacher_ids').map(Number);p.supervisor_ids=fd.getAll('supervisor_ids').map(Number);await api(base()+'/rings/'+id,p,'PUT');}
  if(kind==='supervisor')await api(base()+'/supervisors/'+id+'/profile',p,'PUT');
  if(kind==='remove-supervisor')await api(base()+'/supervisors/'+id,p,'DELETE');
  if(kind==='teacher')await api(base()+'/teachers/'+id+'/profile',p,'PUT');
  if(kind==='teacher-request')await api(base()+'/teacher-requests/'+id,p,'PUT');
  if(kind==='delete'){await api(base()+'/rings/'+id,p,'DELETE');}
  if(kind==='roster'){
   const groups=rosterDraft.map((_,i)=>({name:p['ring_'+i].trim(),teacher_name:p['teacher_'+i].trim(),students:p['students_'+i].split('\n').map(x=>x.trim()).filter(Boolean)}));
   if(groups.some(g=>[g.teacher_name,...g.students].some(x=>/[؟?]/.test(x))))throw Error('أكمل الأسماء التي تحمل ؟ أو احذف سطر الطالب غير المؤكد');
   await api(base()+'/roster/import',{reviewed:fd.has('reviewed'),groups});
  }
  await load();status('تم الحفظ بنجاح');
 });
});
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-delete-ring]');if(!b)return;run(async()=>{
  const id=b.dataset.deleteRing,p=await api(base()+'/rings/'+id+'/deletion-preview');
  $('#deleteRing'+id).innerHTML='<div class="absence-alert"><p>حذف نهائي للحلقة وطلابها وسجلاتهم، بما فيها المؤرشفة والحضور والتسميع والاختبارات والأوراد والشهادات والمراسلات والطلبات. لا يمكن التراجع عنه من النظام. يمكنك نقل الطلاب لحلقة أخرى أولًا. تبقى حسابات الدخول وسجل العمليات.</p><p>عدد ملفات الطلاب: '+p.counts.students+' · طلبات الحسابات: '+p.counts.requests+'</p><form data-manage="delete" data-id="'+id+'" class="halaqat-form">'+input('confirm_name','اكتب اسم الحلقة للتأكيد: '+p.name)+input('token','',p.token,'hidden')+'<button>حذف نهائي بكل السجلات</button></form></div>';
 });
});
// v19 learning tools. Student/guardian views only receive their own private records.
let learningData=null,studentLearning=null,contestData=[],queueState=null;
const form19=(id,body,attrs='')=>'<form id="'+id+'" data-learning class="halaqat-form" '+attrs+'>'+body+'</form>';
const dateAgo=n=>{const d=new Date(today()+'T12:00:00Z');d.setUTCDate(d.getUTCDate()-n);return d.toISOString().slice(0,10);};
const staff19=()=>data.user.role!=='halaqa_student',manager19=()=>['owner','halaqa_supervisor'].includes(data.user.role);
function renderLearningDashboard(){
 let h='';
 if(manager19()){
 h+=panel('كشف البيانات الناقصة','<p>استكمل البيانات من ملف الطالب. إصدار الحساب وربطه من صلاحية المالك.</p><label>بحث<input id="missingSearch" type="search"></label>'+learningData.missing.map(x=>'<div class="halaqat-card" data-missing-name="'+esc(x.name)+'"><strong>'+esc(x.name)+'</strong><p>'+esc(x.ring)+' · '+esc(x.fields.join('، '))+'</p>'+button('استكمال الملف','data-file="'+x.student_id+'"')+'</div>').join('')+(learningData.missing.length?'':empty('بيانات الطلاب الفعالين مكتملة.')));
 h+=panel('المدرس البديل المؤقت',form19('substituteForm',select('halaqa_id','الحلقة',ringOpts())+select('user_id','المدرس البديل',[['','اختر مدرسًا'],...learningData.teachers.map(t=>[t.id,t.name])])+input('start','بداية التكليف',today(),'date')+input('end','نهاية التكليف',today(),'date')+'<button>تعيين مدرس بديل</button><small>الصلاحية تشمل أيام البداية والنهاية بتوقيت الرياض وتنتهي تلقائيًا. التكليف الدائم إن وجد يبقى ساريًا.</small>')+learningData.substitutes.map(s=>'<div class="halaqat-card"><strong>'+esc(s.name)+'</strong><p>'+esc(s.ring)+' · '+s.start+' — '+s.end+(s.expired?' · منتهٍ':'')+'</p>'+button('إلغاء التكليف','data-revoke-sub="'+s.id+'" data-ring="'+s.halaqa_id+'"')+'</div>').join(''));
 }
 h+=panel('دور التسميع',form19('queueViewForm',select('halaqa_id','الحلقة',ringOpts())+input('day','اليوم',today(),'date')+'<button>عرض / تحديث الدور</button>')+'<div id="queueResult"></div><small>اضغط تحديث لمعرفة آخر دور. الطالب وولي الأمر يشاهدان أدوارهما فقط.</small>');
 if(manager19())h+=panel('إنشاء مسابقة',fold('هدف فردي أو جماعي',form19('competitionForm',select('halaqa_id','الحلقة',ringOpts())+input('title','عنوان المسابقة')+select('mode','نوع الهدف',[['individual','فردي — الهدف لكل مشارك'],['team','جماعي — مجموع إنجاز المشاركين']])+input('target','المقدار المستهدف',10,'number',true,'min="0.01" step="0.01" max="100000"')+input('unit','وحدة القياس','نقطة')+input('start','البداية',today(),'date')+input('end','النهاية',today(),'date')+input('reward','وصف المكافأة أو التكريم','','text',false)+'<fieldset><legend>المشاركون</legend><div id="competitionMembers">اختر الحلقة أولًا</div></fieldset><button>إنشاء المسابقة</button>')));
 h+=panel('المسابقات والتكريم',contestData.map(contestCard).join('')||empty('لا توجد مسابقات.'));
 $('#halaqatWorkspace .halaqat-grid').insertAdjacentHTML('beforeend',h);
}
function contestCard(c){
 let h='<h3>'+esc(c.title)+'</h3><p>'+esc(c.ring)+' · '+(c.mode==='team'?'هدف جماعي':'هدف فردي')+' · '+c.target+' '+esc(c.unit)+'</p><p>'+c.start+' — '+c.end+(c.active?'':' · مغلقة')+'</p><p>التكريم: '+esc(c.reward||'غير محدد')+'</p>'+(c.mode==='team'?'<p>مجموع الإنجاز المعتمد: '+c.team_total+'</p>':'');
 h+=c.entries.map(e=>'<div class="halaqat-card"><strong>'+esc(e.name)+'</strong><p>'+e.value+' '+esc(c.unit)+' · '+({empty:'لم تسجل نتيجة',pending:'بانتظار اعتماد المشرف',approved:'معتمد',rejected:'مرفوض'}[e.status])+(e.awarded?' · 🏅 تم اعتماد التكريم':'')+'</p><p>'+esc(e.notes)+'</p>'+(staff19()&&c.active?form19('contestScore'+e.id,input('value','الإنجاز الكلي للمسابقة',e.value,'number',true,'min="0" max="100000" step="0.01"')+input('notes','ملاحظات',e.notes,'text',false)+'<button>رفع النتيجة للمراجعة</button>','data-kind="contestScore" data-contest="'+c.id+'" data-entry="'+e.id+'"'):'')+(manager19()&&c.active&&e.status==='pending'?button('اعتماد النتيجة','data-review-entry="'+e.id+'" data-contest="'+c.id+'" data-state="approved"')+button('رفض النتيجة','data-review-entry="'+e.id+'" data-contest="'+c.id+'" data-state="rejected"'):'')+'</div>').join('');
 if(manager19())h+=button('اعتماد التكريم للمستحقين','data-award-contest="'+c.id+'" data-awarded="true"')+button('سحب اعتماد التكريم','data-award-contest="'+c.id+'" data-awarded="false"')+button(c.active?'إغلاق المسابقة':'إعادة فتح المسابقة','data-active-contest="'+c.id+'" data-active="'+!c.active+'"')+'<small>يعتمد التكريم بعد انتهاء الفترة ومراجعة نتائج الجميع. اسحب التكريم أولًا لتصحيح النتائج.</small>';
 return '<details class="halaqat-card"><summary>'+esc(c.title)+'</summary>'+h+'</details>';
}
function renderQueue(q,rid){
 queueState={...q,rid};let h='<p>الدور الحالي: '+(q.current_position??'لا يوجد')+' · إجمالي القائمة: '+q.total+'</p>'+q.rows.map(x=>'<p>'+x.position+' — '+esc(x.name)+' · '+({waiting:'بانتظار الدور',called:'دورك الآن',done:'تم التسميع',skipped:'تجاوز'}[x.status])+'</p>').join('');
 if(staff19()){
 const rows=data.students.filter(s=>s.halaqa_id===rid);const old=q.rows.map(x=>x.student_id);rows.sort((a,b)=>(old.indexOf(a.id)<0?999:old.indexOf(a.id))-(old.indexOf(b.id)<0?999:old.indexOf(b.id)));
 h+=q.current_id?button('إنهاء الدور والانتقال للتالي','data-next-turn'):'';
 h+=fold('تجهيز ترتيب الطلاب',form19('queueSetForm', '<p>اختر المشاركين وحدد ترتيبهم. الحفظ يعيد بدء الدور لهذا اليوم.</p>'+rows.map((s,i)=>'<div class="halaqat-card"><label><input type="checkbox" name="member" value="'+s.id+'" checked> '+esc(s.name)+'</label>'+input('position_'+s.id,'الترتيب',i+1,'number',true,'min="1" max="300"')+'</div>').join('')+'<button>حفظ الترتيب وبدء التسميع</button>'));
 }
 $('#queueResult').innerHTML=h;
}
function renderLearningFile(){
 const l=studentLearning,g=l.goal,editable=file.can_edit;let h='';
 h+=panel('خطة الختم الشخصية',g?'<h3>'+esc(g.title)+'</h3><p>المنجز المعتمد: '+g.completed+' / '+g.target+' '+unit(g.unit)+' · '+g.percent+'%</p><p>المتبقي: '+g.remaining+' · '+(g.overdue?'تجاوز موعد الهدف؛ حدّث الخطة':('المطلوب أسبوعيًا تقريبًا: '+g.weekly+' '+unit(g.unit)))+'</p><p>'+g.start+' — '+g.deadline+'</p><p>'+esc(g.notes)+'</p>':empty('لم توضع خطة ختم بعد.'));
 if(editable)h+=panel('إعداد هدف الختم',fold('تعديل الهدف والمنجز',form19('goalForm',input('title','اسم الهدف',g?.title||'ختم الحفظ')+select('unit','وحدة الخطة',[['page','وجه'],['ayah','آية']],g?.unit||'page')+input('target','المقدار الكلي المستهدف',g?.target||604,'number',true,'min="0.01" max="100000" step="0.01"')+input('completed','المنجز الكلي المعتمد من الشيخ',g?.completed||0,'number',true,'min="0" max="100000" step="0.01"')+input('start','بداية الخطة',g?.start||today(),'date')+input('deadline','موعد إكمال الهدف',g?.deadline||today(),'date')+input('notes','ملاحظات',g?.notes||'','text',false)+'<button>حفظ خطة الختم</button><small>المنجز يدخله الشيخ بعد التحقق؛ لا يجمع تلقائيًا سجلات التسميع لتجنب احتساب تكرار المواضع. الأسبوع مقدر بسبعة أيام تقويمية.</small>')));
 h+=panel('سجل أخطاء التسميع',l.mistakes.map(m=>'<div class="halaqat-card"><strong>'+esc(m.surah_name)+' — آية '+m.ayah+'</strong><p>'+esc(l.kinds[m.kind])+' · '+m.day+' · تكرر '+m.repetitions+' مرة · '+(m.resolved?'تمت المعالجة':'يحتاج مراجعة')+'</p><p>'+esc(m.notes)+'</p>'+(editable?button('تعديل / معالجة الخطأ','data-edit-mistake="'+m.id+'"'):'')+'</div>').join('')||empty('لا توجد أخطاء مسجلة.'));
 if(editable)h+=panel('تسجيل موضع خطأ',form19('mistakeForm',input('day','اليوم',today(),'date',true,'max="'+today()+'"')+select('surah','السورة',l.surahs.map((n,i)=>[i+1,n]))+input('ayah','رقم الآية',1,'number',true,'min="1" max="286"')+select('kind','نوع الخطأ',Object.entries(l.kinds))+select('resolved','الحالة',[['false','يحتاج مراجعة'],['true','تمت المعالجة']])+input('notes','وصف الخطأ','','text',false)+'<button>حفظ الخطأ</button>'+button('إلغاء التعديل / خطأ جديد','data-reset-mistake')));
 h+=panel('المراجعة المنزلية','<p>إقرار ولي الأمر بالمراجعة في المنزل، مستقل عن تسميع الشيخ ودرجاته.</p>'+l.home.map(x=>'<div class="halaqat-card"><strong>'+x.day+' · '+x.minutes+' دقيقة</strong><p>ولي الأمر: '+esc(x.guardian)+' · الورد رقم '+x.assignment_id+'</p><p>'+esc(x.notes)+'</p></div>').join('')+(l.can_practice?form19('homePracticeForm',select('assignment_id','الورد الذي تمت مراجعته',[['','اختر الورد'],...follow.assignments.map(a=>[a.id,a.due+' — '+(a.memorization||a.revision)])])+input('day','يوم المراجعة',today(),'date',true,'max="'+today()+'"')+input('minutes','مدة المراجعة بالدقائق',15,'number',true,'min="1" max="600"')+input('notes','ملاحظتك','','text',false)+'<button>تأكيد المراجعة المنزلية</button><small>حفظ نفس الورد واليوم يصحح تأكيدك السابق ولا يكرره.</small>'):''));
 h+=panel('التقرير الفصلي المقارن',form19('termReportForm',input('start','من',dateAgo(89),'date')+input('end','إلى',today(),'date',true,'max="'+today()+'"')+'<button>مقارنة بالفترة السابقة</button>')+'<div id="termReportResult"></div><small>المقارنة بفترة سابقة مساوية بالمدة. الأوجه والآيات منفصلة. نسبة الحضور من الحضور والغياب المسجلين فقط، ولا تشمل الأعذار أو الأيام غير المسجلة.</small>');
 $('#studentFile .halaqat-grid').insertAdjacentHTML('beforeend',h);
}
function renderTerm(r){const labels={recorded_days:'أيام مسجلة',present:'أيام حضور',absent:'أيام غياب',excused:'أيام بعذر',attendance_percent:'نسبة الحضور %',memorized_pages:'الحفظ بالأوجه',memorized_ayahs:'الحفظ بالآيات',revision_pages:'المراجعة بالأوجه',revision_ayahs:'المراجعة بالآيات',memorization_score:'متوسط الحفظ / 10',tajweed_score:'متوسط التجويد / 10'};$('#termReportResult').innerHTML='<p>الحالية: '+r.current.from+' — '+r.current.to+'</p><p>السابقة: '+r.previous.from+' — '+r.previous.to+'</p><div style="overflow-x:auto"><table class="learning-table"><thead><tr><th>المؤشر</th><th>الحالية</th><th>السابقة</th><th>الفرق</th></tr></thead><tbody>'+Object.entries(labels).map(([k,v])=>'<tr><td>'+v+'</td><td>'+(r.current[k]??'—')+'</td><td>'+(r.previous[k]??'—')+'</td><td>'+(r.current[k]===null||r.previous[k]===null?'—':Math.round((r.current[k]-r.previous[k])*100)/100)+'</td></tr>').join('')+'</tbody></table></div>';}
document.addEventListener('submit',e=>{const f=e.target;if(!f.hasAttribute('data-learning'))return;e.preventDefault();run(async()=>{
 const fd=new FormData(f),p=Object.fromEntries(fd),url=base()+'/students/'+sid;
 if(f.id==='goalForm'){p.target=Number(p.target);p.completed=Number(p.completed);await api(url+'/completion-goal',p,'PUT');}
 else if(f.id==='mistakeForm'){p.surah=Number(p.surah);p.ayah=Number(p.ayah);p.resolved=p.resolved==='true';await api(url+'/mistakes'+(f.dataset.editId?'/'+f.dataset.editId:''),p,f.dataset.editId?'PUT':'POST');}
 else if(f.id==='homePracticeForm'){p.assignment_id=Number(p.assignment_id);p.minutes=Number(p.minutes);await api(url+'/home-practice',p);}
 else if(f.id==='termReportForm'){renderTerm(await api(url+'/term-report?start='+p.start+'&end='+p.end));status('تم تحميل المقارنة');return;}
 else if(f.id==='queueViewForm'){renderQueue(await api(base()+'/rings/'+p.halaqa_id+'/queue?day='+p.day),Number(p.halaqa_id));status('تم تحديث الدور');return;}
 else if(f.id==='queueSetForm'){const ids=fd.getAll('member').map(Number).sort((a,b)=>Number(p['position_'+a])-Number(p['position_'+b]));if(!ids.length)throw Error('اختر طالبًا واحدًا على الأقل');if(new Set(ids.map(id=>Number(p['position_'+id]))).size!==ids.length)throw Error('لا تكرر رقم الترتيب');if(queueState.total&&!confirm('إعادة بدء قائمة التسميع لهذا اليوم؟'))return;await api(base()+'/rings/'+queueState.rid+'/queue',{day:queueState.day,student_ids:ids,reset:!!queueState.total},'PUT');renderQueue(await api(base()+'/rings/'+queueState.rid+'/queue?day='+queueState.day),queueState.rid);status('تم حفظ الترتيب');return;}
 else if(f.id==='substituteForm'){const rid=p.halaqa_id;delete p.halaqa_id;p.user_id=Number(p.user_id);await api(base()+'/rings/'+rid+'/substitutes',p);await load();status('تم الحفظ بنجاح');return;}
 else if(f.id==='competitionForm'){delete p.member;p.halaqa_id=Number(p.halaqa_id);p.target=Number(p.target);p.student_ids=fd.getAll('member').map(Number);await api(base()+'/competitions',p);await load();status('تم الحفظ بنجاح');return;}
 else if(f.dataset.kind==='contestScore'){p.value=Number(p.value);await api(base()+'/competitions/'+f.dataset.contest+'/entries/'+f.dataset.entry,p,'PUT');await load();status('تم الحفظ بنجاح');return;}
 await openFile(sid,false);status('تم الحفظ بنجاح');
});});
document.addEventListener('change',e=>{if(e.target.form?.id==='competitionForm'&&e.target.name==='halaqa_id')$('#competitionMembers').innerHTML=data.students.filter(s=>s.halaqa_id===Number(e.target.value)).map(s=>'<label><input type="checkbox" name="member" value="'+s.id+'" checked> '+esc(s.name)+'</label>').join('')||empty('لا يوجد طلاب فعالون');});
document.addEventListener('input',e=>{if(e.target.id==='missingSearch')document.querySelectorAll('[data-missing-name]').forEach(x=>x.hidden=!x.dataset.missingName.includes(e.target.value));});
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
 if(b.dataset.editMistake){const m=studentLearning.mistakes.find(m=>m.id===Number(b.dataset.editMistake)),f=$('#mistakeForm');f.dataset.editId=m.id;for(const k of ['day','surah','ayah','kind','notes','resolved'])f.elements[k].value=String(m[k]);f.scrollIntoView({behavior:'smooth'});return;}
 if(b.hasAttribute('data-reset-mistake')){const f=$('#mistakeForm');delete f.dataset.editId;f.reset();return;}
 if(b.hasAttribute('data-next-turn'))run(async()=>{await api(base()+'/rings/'+queueState.rid+'/queue/next',{day:queueState.day,current_id:queueState.current_id});renderQueue(await api(base()+'/rings/'+queueState.rid+'/queue?day='+queueState.day),queueState.rid);status('تم تحديث الدور');});
 if(b.dataset.revokeSub)run(async()=>{await api(base()+'/rings/'+b.dataset.ring+'/substitutes/'+b.dataset.revokeSub,{},'DELETE');await load();});
 if(b.dataset.reviewEntry)run(async()=>{await api(base()+'/competitions/'+b.dataset.contest+'/entries/'+b.dataset.reviewEntry+'/review',{status:b.dataset.state},'PUT');await load();});
 if(b.dataset.awardContest)run(async()=>{await api(base()+'/competitions/'+b.dataset.awardContest+'/award',{awarded:b.dataset.awarded==='true'},'PUT');await load();});
 if(b.dataset.activeContest)run(async()=>{await api(base()+'/competitions/'+b.dataset.activeContest+'/active',{awarded:b.dataset.active==='true'},'PUT');await load();});
});
})();
