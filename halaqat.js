(()=>{
'use strict';
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const roles={owner:'المالك',halaqa_supervisor:'مشرف الحلقات',halaqa_teacher:'المدرس',halaqa_student:'الطالب / ولي الأمر'};
const states={pending:'بانتظار المالك',approved:'تم التفعيل',rejected:'مرفوض',returned:'مُعاد للاستكمال'},attendance={present:'حاضر',absent:'غائب',excused:'مستأذن'};
const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Riyadh'}).format(new Date());
let mid=0,data=null,file=null,sid=0,busy=false,portalView='owner',monitor=null,follow=null,accessOverview=null;
const status=t=>$('#halaqatStatus').textContent=t,base=()=>'/api/halaqat/mosques/'+mid;
async function api(path,body,method='POST'){
 const r=await fetch(path,{cache:'no-store',headers:{'X-Portal-View':portalView},...(body!==undefined?{method,headers:{'Content-Type':'application/json','X-Portal-View':portalView},body:JSON.stringify(body)}:{})}),d=await r.json();
 if(!r.ok){if(d.redirect)location.assign(d.redirect);throw Error(typeof d.detail==='string'?d.detail:Array.isArray(d.detail)?d.detail.map(x=>x.msg).join('، '):'تعذر إتمام الطلب');}return d;
}
async function run(fn){if(busy)return;busy=true;$('#toast20')?.remove();status('جارٍ التنفيذ…');document.querySelectorAll('button').forEach(x=>x.disabled=true);try{await fn();}catch(e){status(e.message);showError20(e.message);}finally{busy=false;document.querySelectorAll('button').forEach(x=>x.disabled=false);}}
const button=(label,attr)=>'<button type="button" class="halaqat-btn" '+attr+'>'+label+'</button>';
const panel=(title,body)=>'<article class="halaqat-panel"><h2>'+title+'</h2>'+body+'</article>';
const input=(name,label,value='',type='text',required=true,attrs='')=>'<label>'+label+'<input name="'+name+'" type="'+type+'" value="'+esc(value)+'" '+(required?'required':'')+' '+attrs+'></label>';
const select=(name,label,options,value='',required=true)=>'<label>'+label+'<select name="'+name+'" '+(required?'required':'')+'>'+options.map(([v,t])=>'<option value="'+esc(v)+'" '+(String(value)===String(v)?'selected':'')+'>'+esc(t)+'</option>').join('')+'</select></label>';
const multiSelect=(name,label,options)=>'<label>'+label+'<select name="'+name+'" multiple required size="'+Math.min(Math.max(options.length,2),6)+'">'+options.map(([v,t])=>'<option value="'+esc(v)+'">'+esc(t)+'</option>').join('')+'</select><small>يمكن اختيار أكثر من مشرف.</small></label>';
const empty=t=>'<p class="empty">'+t+'</p>',unit=u=>u==='ayah'?'آية':'وجه',ringOpts=()=>[['','اختر الحلقة'],...data.rings.map(r=>[r.id,r.name])];
function credentials(d){$('#halaqatCredentials').hidden=false;$('#halaqatCredentials').innerHTML=d.linked_existing?'<strong>تم اعتماد الطالب وربطه بالحساب المحدد</strong><p>'+esc(d.user?.name)+'</p>'+button('إخفاء','data-hide-credentials'):'<strong>بيانات الدخول — احفظها وسلّمها لصاحب الحساب</strong><p>اسم المستخدم: <code>'+esc(d.user?.username||d.username)+'</code></p><p>الرمز المؤقت: <code>'+esc(d.temporary_password)+'</code></p><p>يجب تغييره عند أول دخول.</p>'+button('إخفاء الرمز','data-hide-credentials');window.scrollTo({top:0,behavior:'smooth'});}
function familyOptions(){return (data.accounts||[]).filter(u=>u.role==='halaqa_student').map(u=>[u.id,u.name+' — '+u.username+(u.children?.length?' — الأبناء: '+u.children.map(c=>c.name).join('، '):'')]);}
function requestDetails(r){if(r.type!=='student')return '';return '<p>ولي الأمر: '+esc(r.guardian_name||'—')+' · '+esc(r.guardian_relation||'—')+' · '+esc(r.guardian_phone||'—')+'</p><p>الحفظ الحالي: '+esc(r.current_memorization||'—')+'</p>';}
let selectedStudentRing='',studentFilterMode='all';
function students(){
 if(!data.rings.length)return empty('لا توجد حلقات متاحة بعد.');
 if(!data.rings.some(r=>String(r.id)===selectedStudentRing))selectedStudentRing='';
 const cards=data.students.map(s=>{
  const optional=[!s.has_national_id?'رقم الهوية':'',!s.birth_date?'تاريخ الميلاد':'',!s.school_grade?'الصف الدراسي':''].filter(Boolean);
  const phone=s.guardian_phone||'';
  return '<div class="student-row" data-student-ring="'+s.halaqa_id+'" data-student-name="'+esc(s.name)+'" data-high-absence="'+(s.absences_30_days>=3)+'" data-low-rating="'+Boolean(s.low_rating)+'" data-repeated-notes="'+Boolean(s.repeated_notes)+'" hidden><div><strong>'+esc(s.name)+'</strong><small>'+esc(s.recipient_type==='guardian'?'ولي الأمر: '+(s.guardian_name||'غير مسجل'):'الحساب للطالب')+'</small><small>جوال التواصل: '+(phone?'<bdi>'+esc(phone)+'</bdi>':'غير مسجل')+'</small>'+(s.avg_score!=null?'<small>متوسط التقييم: '+esc(s.avg_score)+'/10</small>':'')+(optional.length?'<small class="optional-note">بيانات اختيارية غير مسجلة: '+esc(optional.join('، '))+'</small>':'')+'</div>'+button('ملف الطالب','data-file="'+s.id+'"')+'</div>';
 }).join('');
 return '<label>اختر الحلقة<select id="studentRingFilter"><option value="">اختر الحلقة لعرض طلابها</option>'+data.rings.map(r=>'<option value="'+r.id+'" '+(selectedStudentRing===String(r.id)?'selected':'')+'>'+esc(r.name)+'</option>').join('')+'</select></label><div id="selectedRingWorkspace"></div><div class="student-filters">'+button('جميع الطلاب','data-student-filter="all"')+button('ملاحظات متكررة','data-student-filter="notes"')+button('تقييم منخفض','data-student-filter="low"')+button('كثيرو الغياب','data-student-filter="absence"')+'</div><label>بحث داخل الحلقة<input id="studentSearch" type="search"></label><p id="studentListHint">اختر الحلقة لعرض طلابها.</p><div>'+cards+'</div>';
}
function filterStudentList(){
 const select=$('#studentRingFilter');if(!select)return;selectedStudentRing=select.value;
 const overview=$('#selectedRingWorkspace');if(overview&&overview.dataset.ring!==selectedStudentRing){overview.dataset.ring=selectedStudentRing;renderSelectedRing();}
 const query=($('#studentSearch')?.value||'').trim();let count=0;
 document.querySelectorAll('[data-student-ring]').forEach(row=>{const flag=studentFilterMode==='all'||(studentFilterMode==='notes'&&row.dataset.repeatedNotes==='true')||(studentFilterMode==='low'&&row.dataset.lowRating==='true')||(studentFilterMode==='absence'&&row.dataset.highAbsence==='true');row.hidden=!selectedStudentRing||row.dataset.studentRing!==selectedStudentRing||!row.dataset.studentName.includes(query)||!flag;if(!row.hidden)count++;});
 $('#studentListHint').textContent=selectedStudentRing?(count?'عدد الطلاب: '+count:'لا يوجد طلاب مطابقون في هذه الحلقة.'):'اختر الحلقة لعرض طلابها.';
}

function circleCalendar(rows){const manager=['owner','halaqa_supervisor'].includes(data.user.role);return rows.map(c=>'<article class="halaqat-card"><h3>'+esc(c.name)+'</h3><p>'+(c.configured?c.weekdays.map(d=>dayNames[d]).join('، ')||'لا توجد لقاءات أسبوعية':'لم يحدد الجدول بعد')+' · '+esc(c.time_text)+'</p><p>اليوم: '+(c.today_held?'يوجد لقاء':'لا يوجد لقاء محدد')+'</p>'+c.exceptions.map(x=>'<p>'+x.day+' · '+(x.held?'لقاء استثنائي':'إجازة / إلغاء')+' · '+esc(x.reason)+(manager?button('إزالة الاستثناء','data-calendar-remove="'+c.id+'" data-day="'+x.day+'"'):'')+'</p>').join('')+(manager?fold('تعديل الجدول والإجازات',form15('calendarForm'+c.id,'<fieldset><legend>أيام اللقاءات</legend>'+dayNames.map((d,i)=>'<label class="toggle-label"><input name="weekdays" type="checkbox" value="'+i+'" '+(c.weekdays.includes(i)?'checked':'')+'>'+d+'</label>').join('')+'</fieldset>'+input('time_text','وقت الحلقة',c.time_text,'text',false,'maxlength="100"')+'<button>حفظ الجدول</button>','data-kind="calendar" data-ring="'+c.id+'"')+form15('exceptionForm'+c.id,input('day','تاريخ الاستثناء',today(),'date')+select('held','نوع الاستثناء',[['false','إجازة أو إلغاء اللقاء'],['true','إضافة لقاء استثنائي']])+input('reason','السبب','','text',false,'maxlength="500"')+'<button>حفظ الاستثناء</button>','data-kind="exception" data-ring="'+c.id+'"')):'')+'</article>').join('')||empty('لا توجد حلقات متاحة.');}
function renderSelectedRing(){
 const box=$('#selectedRingWorkspace'),ring=data.rings.find(r=>String(r.id)===selectedStudentRing);if(!box)return;
 if(!ring||data.user.role==='halaqa_student'){box.innerHTML='';return;}
 const announcements=development.announcements.filter(a=>a.halaqa_id===ring.id||a.halaqa_id===null);
 box.innerHTML='<section class="ring-overview"><h3>'+esc(ring.name)+'</h3><p>المشرفون: '+esc((ring.supervisors||[]).map(x=>x.name).join('، ')||'غير محدد')+'</p><p>المعلمون: '+esc((ring.teachers||[]).map(x=>x.name).join('، ')||'بانتظار إصدار الحساب')+' · عدد الطلاب: '+ring.student_count+'</p><div class="ring-metrics"><span>الإنجاز آخر 30 يومًا <b>'+Number(ring.completion_rate||0)+'%</b></span><span>نسبة الغياب <b>'+Number(ring.absence_rate||0)+'%</b></span></div><div class="actions"><a class="halaqat-btn secondary" target="_blank" href="'+base()+'/rings/'+ring.id+'/roster">طباعة كشف الطلاب</a><a class="halaqat-btn secondary" href="'+base()+'/rings/'+ring.id+'/roster.csv">تصدير CSV</a></div>'+fold('جدول الحلقة وإجازاتها',circleCalendar(development.calendars.filter(c=>c.id===ring.id)))+'<h3>إعلانات الحلقة</h3>'+(announcements.map(a=>'<article class="halaqat-card"><strong>'+esc(a.title)+'</strong><small>'+esc(a.ring)+(a.expires?' · حتى '+esc(a.expires):'')+'</small><p class="preserve-lines">'+esc(a.body)+'</p>'+(a.can_archive?button('أرشفة الإعلان','data-announcement-archive="'+a.id+'"'):'')+'</article>').join('')||empty('لا توجد إعلانات حالية لهذه الحلقة.'))+fold('إضافة إعلان لهذه الحلقة',form15('ringAnnouncementForm','<p>سينشر الإعلان في: <strong>'+esc(ring.name)+'</strong></p><input type="hidden" name="halaqa_id" value="'+ring.id+'">'+input('title','عنوان الإعلان','','text',true,'minlength="2" maxlength="180"')+textArea('body','نص الإعلان')+input('expires','ينتهي في (اختياري)','','date',false)+'<button>نشر إعلان الحلقة</button>'))+'</section><h3>طلاب الحلقة</h3>';
}
function rings(){return data.rings.length?data.rings.map(r=>'<div class="halaqat-card"><h3>'+esc(r.name)+'</h3><p>'+esc(r.schedule)+'</p><p>المشرفون: '+esc((r.supervisors||[]).map(s=>s.name).join('، ')||'غير محدد')+' · المدرسون: '+esc((r.teachers||[]).map(t=>t.name).join('، ')||'بانتظار إصدار الحساب')+'</p><p>الطلاب: '+r.student_count+' · الإنجاز: '+Number(r.completion_rate||0)+'% · الغياب: '+Number(r.absence_rate||0)+'%</p>'+button('عرض طلاب الحلقة','data-open-ring="'+r.id+'"')+'</div>').join(''):empty('أنشئ الحلقة واربطها بمشرف قبل طلب حساب المدرس.');}
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
 s+=panel('الحلقة وطلابها',students())+panel('طلبات الحسابات',requests())+panel('متابعة الغياب خلال 30 يومًا',recentAbsences());
 $('#halaqatWorkspace').innerHTML='<div class="halaqat-grid">'+s+'</div>';
}
function applyV22RoleUI(isFile=false){
 const role=data?.user?.role;if(!role)return;
 let allow=null;
 if(role==='halaqa_teacher')allow=isFile?[/بيانات الطالب/,/تسجيل التسميع/,/سجل الحضور/,/الورد القادم/,/تحديد ورد جديد/]:[/الحلقة وطلابها/,/التحضير الجماعي/,/لوحة المتابعة/];
 if(role==='halaqa_student')allow=isFile?[/بيانات الطالب/,/سجل الحضور/,/الورد القادم/]:[/أبنائي/,/ملفي كطالب/];
 if(!allow)return;
 const root=$(isFile?'#studentFile':'#halaqatWorkspace');if(!root)return;
 root.querySelectorAll('.halaqat-panel').forEach(p=>{const title=(p.querySelector('h2')?.textContent||'').trim();p.hidden=!allow.some(rx=>rx.test(title));});
}

async function load(){$('#halaqatApp').classList.remove('file-open');data=await api(base()+'/dashboard');monitor=await api(base()+'/monitor');development=await api(base()+'/development');orgOverview=data.user.role==='owner'?await api('/api/halaqat/organizations/overview'):null;managementTeachers=data.user.role==='owner'?(await api(base()+'/teachers/manage')).teachers:[];managementSupervisors=data.user.role==='owner'?(await api(base()+'/supervisors/manage')).supervisors:[];accessOverview=['owner','halaqa_supervisor'].includes(data.user.role)?await api('/api/access/mosques/'+mid+'/overview'):null;learningData=await api(base()+'/learning-dashboard');contestData=(await api(base()+'/competitions')).competitions;$('#halaqatWorkspace').hidden=false;renderDashboard();renderManagement();renderAccessManagement();renderLearningDashboard();await renderAdvancedDashboard();applyV22RoleUI(false);organize20('halaqatWorkspace',false);filterStudentList();$('#studentFile').hidden=true;const accountLabel=data.user.role==='halaqa_student'?(data.user.account_type==='guardian'?'ولي الأمر':'الطالب'):roles[data.user.role];status(accountLabel+' · '+data.user.name+' · تم تحديث البيانات');}
function quantity(prefix,title,u='page',amount=1){const preset=u==='ayah'?'ayah':[.5,1,2].includes(Number(amount))?String(amount):'custom';return '<fieldset class="quantity"><legend>'+title+'</legend>'+select(prefix+'_preset','المقدار',[['0.5','نصف وجه'],['1','وجه واحد'],['2','وجهان'],['custom','عدد أوجه مخصص'],['ayah','عدد آيات محدد']],preset)+input(prefix+'_amount','العدد',amount,'number',true,'min="0.5" max="1000" step="0.5"')+'</fieldset>';}
function planEditor(){const p=file.plan||{memorization_unit:'page',memorization_amount:1,revision_unit:'page',revision_amount:2,sessions_per_week:5};return '<form id="planForm" class="halaqat-form"><div class="halaqat-form-grid">'+quantity('memorization','الحفظ لكل لقاء',p.memorization_unit,p.memorization_amount)+quantity('revision','المراجعة لكل لقاء',p.revision_unit,p.revision_amount)+input('sessions_per_week','عدد اللقاءات أسبوعيًا',p.sessions_per_week,'number',true,'min="1" max="7"')+input('start_surah','سورة البداية',p.start_surah||'','text',false)+input('start_ayah','آية البداية',p.start_ayah||'','number',false,'min="1" max="286"')+input('end_surah','سورة النهاية',p.end_surah||'','text',false)+input('end_ayah','آية النهاية',p.end_ayah||'','number',false,'min="1" max="286"')+input('notes','تعليمات الخطة',p.notes||'','text',false)+'</div><button>حفظ خطة الطالب</button></form>';}
function planSummary(){const p=file.plan;if(!p)return empty('لم يحدد المدرس خطة بعد.');return '<p>الحفظ: <strong>'+p.memorization_amount+' '+unit(p.memorization_unit)+'</strong> لكل لقاء</p><p>المراجعة: <strong>'+p.revision_amount+' '+unit(p.revision_unit)+'</strong> لكل لقاء</p><p>'+p.sessions_per_week+' لقاءات أسبوعيًا</p><p>'+esc(p.start_surah)+' '+esc(p.start_ayah??'')+' — '+esc(p.end_surah)+' '+esc(p.end_ayah??'')+'</p><p>'+esc(p.notes)+'</p>';}
function progressForm(){const p=file.plan||{memorization_unit:'page',revision_unit:'page'};return '<form id="progressForm" class="halaqat-form"><div class="halaqat-form-grid">'+input('day','اليوم',today(),'date',true,'max="'+today()+'"')+select('attendance','الحضور',Object.entries(attendance),'present')+input('memorized','ما تم حفظه (السورة والآيات)','','text',false)+input('memorized_amount','مقدار الحفظ المنجز',0,'number',true,'min="0" max="1000" step="0.5"')+select('memorized_unit','وحدة الحفظ',[['page','وجه'],['ayah','آية']],p.memorization_unit)+input('revision','ما تمت مراجعته','','text',false)+input('revision_amount','مقدار المراجعة المنجز',0,'number',true,'min="0" max="1000" step="0.5"')+select('revision_unit','وحدة المراجعة',[['page','وجه'],['ayah','آية']],p.revision_unit)+input('memorization_score','درجة الحفظ من 10','','number',false,'min="0" max="10"')+input('tajweed_score','درجة التجويد من 10','','number',false,'min="0" max="10"')+input('mistakes','عدد الأخطاء',0,'number',true,'min="0" max="1000"')+input('notes','ملاحظات تظهر لولي الأمر','','text',false)+'</div><p class="small-note">سجل واحد لكل يوم. استخدم «تعديل» من السجل لتصحيح اليوم السابق.</p><button>حفظ التسميع والحضور</button></form>';}
function history(){return file.progress.length?file.progress.map(p=>'<article class="halaqat-card"><h3>'+esc(p.day)+' · '+attendance[p.attendance]+'</h3><p>الحفظ: '+esc(p.memorized||'—')+' ('+p.memorized_amount+' '+unit(p.memorized_unit)+')</p><p>المراجعة: '+esc(p.revision||'—')+' ('+p.revision_amount+' '+unit(p.revision_unit)+')</p><p>الحفظ: '+(p.memorization_score??'—')+'/10 · التجويد: '+(p.tajweed_score??'—')+'/10 · الأخطاء: '+p.mistakes+'</p><p>'+esc(p.notes)+'</p>'+(file.can_edit?button('تعديل','data-progress="'+p.id+'"'):'')+'</article>').join(''):empty('لا توجد سجلات حتى الآن.');}
function exams(){let h=file.exams.map(x=>'<article class="halaqat-card"><h3>'+esc(x.title)+' · '+x.score+'/'+x.total+'</h3><p>'+x.day+(x.next_level?' · المستوى: '+esc(x.next_level):'')+'</p><p>'+esc(x.notes)+'</p></article>').join('')||empty('لا توجد اختبارات مسجلة.');if(file.can_edit)h+='<details><summary>تسجيل اختبار وترقية مستوى</summary><form id="examForm" class="halaqat-form">'+input('title','اسم الاختبار')+input('day','التاريخ',today(),'date',true,'max="'+today()+'"')+input('score','الدرجة','','number',true,'min="0" step="0.5"')+input('total','الدرجة الكاملة',100,'number',true,'min="1" max="1000" step="0.5"')+input('next_level','المستوى الجديد (اختياري)','','text',false)+input('notes','ملاحظات','','text',false)+'<button>حفظ الاختبار</button></form></details>';return h;}
function certificates(){let h=file.certificates.map(c=>'<article class="halaqat-card"><h3>'+esc(c.title)+'</h3><p>'+esc(c.achievement)+'</p><p>'+esc(c.issued_on)+'</p><a class="halaqat-btn" href="'+esc(c.url)+'" target="_blank" rel="noopener">عرض وطباعة الشهادة</a></article>').join('')||empty('لا توجد شهادات بعد.');if(file.can_certify)h+='<details><summary>إصدار شهادة إنجاز</summary><form id="certificateForm" class="halaqat-form">'+input('title','عنوان الشهادة','شهادة إتمام حفظ')+input('memorization_scope','أكمل حفظ إلى جزء / سورة','','text',true,'maxlength="250" placeholder="مثال: جزء عم أو سورة البقرة"')+input('mastery_percent','نسبة الإتقان %','','number',true,'min="0" max="100" step="0.1"')+'<small>رقم الهوية يؤخذ من ملف الطالب إن سُجّل، وهو اختياري.</small>'+'<button>إصدار الشهادة</button></form></details>';return h;}
function renderBaseFile(){
 const s=file.student,w=file.weekly,weekly=w?'<p>الحفظ المنجز: '+w.memorization_done+' '+unit(w.memorization_unit)+'، والمستهدف: '+w.memorization_target+'</p><p>المراجعة المنجزة: '+w.revision_done+' '+unit(w.revision_unit)+'، والمستهدف: '+w.revision_target+'</p><small>من '+w.from+'؛ تُجمع المقادير المسجلة بوحدة الخطة نفسها، دون تحويل تلقائي بين الأوجه والآيات.</small>':empty('حدّد الخطة لعرض الهدف الأسبوعي.');
 $('#studentFile').hidden=false;$('#studentFile').innerHTML='<header class="student-file-head"><div><small>ملف الطالب</small><h1>'+esc(s.name)+'</h1><p>'+esc(s.ring)+' · '+esc(s.level)+'</p></div><div class="actions">'+button(data.user.account_type==='guardian'?'العودة للأبناء':'العودة للطلاب','data-back')+'<a class="halaqat-btn secondary" href="'+base()+'/students/'+sid+'/report.csv">تصدير التقرير CSV</a></div></header><div class="halaqat-grid">'+panel('بيانات الطالب','<p>ولي الأمر: '+esc(s.guardian_name||'غير مسجل')+' · '+esc(s.guardian_relation||'')+'</p><p>الجوال: '+esc(s.guardian_phone||'غير مسجل')+'</p><p>الحفظ عند التسجيل: '+esc(s.current_memorization||'غير مسجل')+'</p><p>موعد الحلقة: '+esc(s.schedule)+'</p><p class="'+(file.absence_alert?'absence-alert':'')+'">الغياب المسجل خلال 30 يومًا: '+file.absences_30_days+(file.absence_alert?' · يحتاج متابعة':'')+'</p>')+panel('خطة الحفظ والمراجعة',planSummary()+(file.can_edit?'<details><summary>تعديل خطة الطالب</summary>'+planEditor()+'</details>':''))+panel('الإنجاز الأسبوعي',weekly)+(file.can_edit?panel('تسجيل التسميع والتقييم',progressForm()):'')+panel('سجل الحضور والتسميع',history())+panel('الاختبارات والمستوى',exams())+panel('الشهادات',certificates())+'</div>';
 document.querySelectorAll('#planForm [name$="_preset"]').forEach(syncQuantity);
}
async function openFile(id,scroll=true){$('#halaqatApp').classList.add('file-open');sid=Number(id);file=await api(base()+'/students/'+sid+'/file');follow=await api(base()+'/students/'+sid+'/followup');studentDev=await api(base()+'/students/'+sid+'/development');studentLearning=await api(base()+'/students/'+sid+'/learning');thread=await api(base()+'/students/'+sid+'/messages');advanced=await api(base()+'/students/'+sid+'/advancement');$('#halaqatWorkspace').hidden=true;renderFile();renderAdvancedFile();applyV22RoleUI(true);organize20('studentFile',true);status('ملف '+file.student.name);if(scroll)$('#studentFile').scrollIntoView({behavior:'smooth',block:'start'});}
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
 else if(f.id==='certificateForm'){p.mastery_percent=Number(p.mastery_percent);await api(b+'/students/'+sid+'/certificates',p);await openFile(sid,false);}
 status('تم الحفظ بنجاح');
}
document.addEventListener('submit',e=>{if(['supervisorForm','ringForm','teacherRequestForm','studentRequestForm','planForm','progressForm','examForm','certificateForm','profileForm','recipientForm','transferForm','batchForm','assignmentForm','appointmentForm','featuresForm'].includes(e.target.id)||e.target.matches('.approval-form,.assignment-result')){e.preventDefault();run(()=>submit(e.target));}});
document.addEventListener('change',e=>{if(e.target.id==='studentRingFilter')filterStudentList();if(e.target.name?.endsWith('_preset'))syncQuantity(e.target);});
document.addEventListener('input',e=>{if(e.target.id==='studentSearch')filterStudentList();});
document.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.hasAttribute('data-hide-credentials')){$('#halaqatCredentials').hidden=true;$('#halaqatCredentials').textContent='';return;}
 if(b.hasAttribute('data-back')){$('#studentFile').hidden=true;$('#halaqatWorkspace').hidden=false;run(load);return;}
 if(b.dataset.file){run(()=>openFile(b.dataset.file));return;}
 if(b.dataset.openRing){selectedStudentRing=String(b.dataset.openRing);studentFilterMode='all';const sel=$('#studentRingFilter');if(sel)sel.value=selectedStudentRing;filterStudentList();document.querySelector('#studentRingFilter')?.scrollIntoView({behavior:'smooth',block:'center'});return;}
 if(b.dataset.studentFilter){studentFilterMode=b.dataset.studentFilter;filterStudentList();return;}
 if(b.dataset.deleteStudent){run(async()=>{const preview=await api(base()+'/students/'+b.dataset.deleteStudent+'/deletion-preview');const typed=prompt('حذف نهائي لا يمكن التراجع عنه. اكتب اسم الطالب كاملًا للتأكيد: \n'+preview.name,'');if(typed===null)return;if(typed.trim()!==preview.name)throw Error('الاسم لا يطابق اسم الطالب');await api(base()+'/students/'+b.dataset.deleteStudent,{confirm_name:typed.trim(),token:preview.token},'DELETE');$('#studentFile').hidden=true;$('#halaqatWorkspace').hidden=false;await load();status('تم حذف الطالب نهائيًا');});return;}
 if(b.dataset.progress){const p=file.progress.find(x=>x.id===Number(b.dataset.progress)),f=$('#progressForm');for(const [k,v] of Object.entries(p))if(f.elements[k])f.elements[k].value=v??'';f.scrollIntoView({behavior:'smooth'});return;}
 if(b.dataset.reject)run(async()=>{const note=prompt('سبب الرفض:','');if(note===null)return;await api(base()+'/requests/'+b.dataset.reject+'/reject',{note});await load();});
 if(b.dataset.reset)run(async()=>{if(!confirm('إصدار رمز جديد يلغي جلسات الدخول الحالية للحساب. متابعة؟'))return;credentials(await api(base()+'/users/'+b.dataset.reset+'/reset',{}));await load();});
});
// Version 14: owner views, reviewed enrollment and student follow-up.
const recipientOptions=[['student','الطالب نفسه'],['guardian','ولي الأمر']];
const featureNames={assignments:'الورد القادم',notifications:'التنبيهات داخل النظام',rewards:'النقاط والشارات',monthly_reports:'التقارير الشهرية PDF'};
const wardStates={pending:'بانتظار التسميع',completed:'مكتمل',partial:'جزئي',not_done:'لم ينجز'};
function accountFields(student=false){
 return input('full_name',student?'اسم الطالب الرباعي':'اسم المدرس','','text',true,'minlength="2" maxlength="180"')+select('halaqa_id','الحلقة',ringOpts())+(student?select('recipient_type','من يتابع التقارير؟',recipientOptions,'student')+'<details><summary>بيانات إضافية اختيارية</summary>'+input('national_id','رقم الهوية (اختياري)','','text',false,'maxlength="30" inputmode="numeric"')+input('birth_date','تاريخ الميلاد (اختياري)','','date',false)+input('school_grade','الصف الدراسي (اختياري)','','text',false,'maxlength="120"')+'</details>'+input('current_memorization','الحفظ الحالي','','text',false,'maxlength="250"')+'<div class="guardian-fields" hidden>'+input('guardian_name','اسم ولي الأمر','','text',false,'maxlength="180"')+input('guardian_relation','صلة القرابة','الأب','text',false,'maxlength="60"')+'</div>'+input('guardian_phone','جوال الطالب أو ولي الأمر','','tel',false,'maxlength="40"')+'<small>يراجع المالك الملف ويختار حساب ولي الأمر الموجود أو ينشئ حسابًا جديدًا عند الاعتماد.</small>':'')+input('notes','ملاحظات داخلية','','text',false,'maxlength="1000"');
}
function recipientAccounts(type,currentId=0){return (monitor?.recipients||[]).filter(u=>type==='guardian'?u.account_type==='guardian':u.account_type!=='guardian'&&(!u.children?.length||u.id===currentId)).map(u=>[u.id,u.name+' — '+u.username+(u.role==='owner'?' (حسابي الشخصي)':u.children?.length?' — '+u.children.map(c=>c.name).join('، '):'')]);}
function approvalForm(r){return '<form class="halaqat-form approval-form" data-request-id="'+r.id+'">'+(r.type==='student'?select('existing_user_id',r.recipient_type==='guardian'?'حساب ولي الأمر':'حساب الطالب',[['','إنشاء حساب جديد'],...recipientAccounts(r.recipient_type)],'',false):'')+input('username','اسم المستخدم للحساب الجديد','','text',false,'maxlength="30"')+input('temporary_password','كلمة المرور المؤقتة (فارغة = توليد آمن)','','password',false,'minlength="8" maxlength="128" autocomplete="new-password"')+'<div class="actions"><button>اعتماد الملف</button>'+(r.type==='student'?button('إرجاع للاستكمال','data-return="'+r.id+'"'):'')+button('رفض','data-reject="'+r.id+'"')+'</div></form>';}
function requests(){return data.requests.length?data.requests.map(r=>'<article class="halaqat-card"><span class="halaqat-badge">'+esc(states[r.status])+'</span><h3>'+esc(r.full_name)+'</h3><p>'+(r.type==='teacher'?'مدرس':'طالب · المتابع: '+(r.recipient_type==='guardian'?'ولي الأمر':'الطالب نفسه'))+' · '+esc(r.ring)+'</p>'+requestDetails(r)+'<p>مقدم الطلب: '+esc(r.requested_by?.name)+'</p><p>'+esc(r.notes)+'</p>'+(r.review_note?'<p class="review-note">ملاحظة المراجعة: '+esc(r.review_note)+'</p>':'')+(r.type==='student'&&['pending','returned'].includes(r.status)&&(data.user.role==='owner'||r.requested_by?.id===data.user.id)?button('تعديل واستكمال الملف','data-amend="'+r.id+'"'):'')+(data.user.role==='owner'&&r.status==='pending'?approvalForm(r):'')+'</article>').join(''):empty('لا توجد طلبات.');}
function syncRecipient(form){const box=form.querySelector('.guardian-fields');if(box){const isGuardian=form.elements.recipient_type.value==='guardian';box.hidden=!isGuardian;form.elements.guardian_name.required=isGuardian;}}
function batchRows(){const f=$('#batchForm');if(!f)return;const rid=Number(f.elements.ring.value),day=f.elements.day.value;$('#batchRows').innerHTML=data.students.filter(s=>s.halaqa_id===rid).map(s=>{const old=data.progress.find(p=>p.student_id===s.id&&p.day===day);return select('attendance_'+s.id,s.name,[['','دون تغيير'],...Object.entries(attendance)],old?.attendance||'',false);}).join('')||empty('لا يوجد طلاب في هذه الحلقة.');}
function renderDashboard(){
 renderBaseDashboard();let extra='';
 let view=$('#portalViewBox');if(!view){view=document.createElement('div');view.id='portalViewBox';$('.halaqat-toolbar').prepend(view);}view.innerHTML=data.user.original_role==='owner'?select('portalView','واجهتي',[['owner','المدير العام'],['supervisor','المشرف']],portalView):'';
 if(data.user.role==='owner')extra+=panel('إدارة الميزات','<form id="featuresForm" class="halaqat-form">'+Object.entries(featureNames).map(([k,v])=>'<label class="toggle-label"><input type="checkbox" name="'+k+'" '+(monitor.features[k]?'checked':'')+'> '+v+'</label>').join('')+'<button>حفظ إعدادات الميزات</button></form>');
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
 if(['owner','halaqa_supervisor'].includes(data.user.role))extra+=panel('تعديل بيانات الطالب','<form id="profileForm" class="halaqat-form">'+input('full_name','اسم الطالب',s.name,'text',true,'minlength="2" maxlength="180"')+'<details><summary>بيانات إضافية اختيارية</summary>'+input('national_id','رقم الهوية (اختياري)',s.national_id||'','text',false,'maxlength="30" inputmode="numeric"')+input('birth_date','تاريخ الميلاد (اختياري)',s.birth_date||'','date',false)+input('school_grade','الصف الدراسي (اختياري)',s.school_grade,'text',false,'maxlength="120"')+'</details>'+input('current_memorization','الحفظ عند التسجيل',s.current_memorization,'text',false,'maxlength="250"')+input('guardian_name','اسم ولي الأمر',s.guardian_name,'text',s.recipient_type==='guardian','maxlength="180"')+input('guardian_phone','جوال الطالب أو ولي الأمر',s.guardian_phone,'tel',false,'maxlength="40"')+input('guardian_relation','صلة القرابة',s.guardian_relation,'text',false,'maxlength="60"')+input('notes','ملاحظات داخلية',s.notes,'text',false,'maxlength="1000"')+'<button>حفظ بيانات الطالب</button></form>');
 if(data.user.role==='owner'&&s.active)extra+=panel('إدارة ربط الحساب','<form id="recipientForm" class="halaqat-form">'+select('recipient_type','متابع التقارير',recipientOptions,s.recipient_type)+select('user_id','الحساب المرتبط',recipientAccounts(s.recipient_type,s.user_id),s.user_id)+'<button>حفظ ربط الحساب</button><small>تنتقل صلاحية الاطلاع للحساب المحدد. لإصدار حساب جديد استخدم النموذج أدناه؛ المالك وحده يصدر بيانات الدخول.</small></form><details><summary>إصدار حساب جديد لهذا الطالب أو ولي أمره</summary><form id="newRecipientForm" class="halaqat-form">'+select('recipient_type','نوع الحساب',recipientOptions,s.recipient_type)+input('full_name','اسم صاحب الحساب',s.recipient_type==='guardian'?s.guardian_name:s.name,'text',true,'minlength="2" maxlength="180"')+input('username','اسم المستخدم','','text',true,'minlength="3" maxlength="30" autocomplete="off"')+'<small>دون مسافات، مثل: عبد_الخالق_الشهري. إصدار الحساب ينقل ارتباط هذا الطالب إليه ويحفظ سجل الطالب.</small>'+input('temporary_password','كلمة المرور المؤقتة (اختياري)','','password',false,'minlength="8" maxlength="128"')+'<button>إصدار الحساب وربط الطالب</button></form></details>');
 if(s.active&&['owner','halaqa_supervisor'].includes(data.user.role))extra+=panel('نقل الطالب إلى حلقة أخرى','<form id="transferForm" class="halaqat-form">'+select('halaqa_id','الحلقة',data.rings.map(r=>[r.id,r.name]),s.halaqa_id)+'<button>نقل مع الاحتفاظ بالسجل</button></form>');
 if(['owner','halaqa_supervisor'].includes(data.user.role))extra+=panel('حذف الطالب نهائيًا','<p class="small-note">يحذف ملف الطالب وسجلاته نهائيًا. حساب الدخول المرتبط يبقى محفوظًا حتى لا يتأثر ولي الأمر أو أي أبناء آخرين.</p>'+button('حذف نهائي','data-delete-student="'+s.id+'"'));
 $('#studentFile .halaqat-grid').insertAdjacentHTML('afterbegin',extra);
 $('#studentFile').querySelectorAll('a[href]').forEach(a=>{const u=new URL(a.href);u.searchParams.set('view',portalView);a.href=u.pathname+u.search;});syncMonthly();renderDevelopmentFile();renderLearningFile();
}
function syncMonthly(){if($('#monthlyDownload'))$('#monthlyDownload').href=base()+'/students/'+sid+'/monthly.pdf?month='+encodeURIComponent($('#reportMonth').value)+'&view='+portalView;}
async function submitExtra(f,p){
 const url=base()+'/students/'+sid;let handled=true;
 if(f.id==='profileForm'){p.birth_date=p.birth_date||null;await api(url+'/profile',p,'PUT');}
 else if(f.id==='recipientForm'){p.user_id=Number(p.user_id);await api(url+'/recipient',p,'PUT');}
 else if(f.id==='newRecipientForm'){
  p.username=p.username.normalize('NFKC').trim();
  if(/\s/u.test(p.username))throw Error('اسم المستخدم لا يقبل المسافات. استخدم: '+p.username.replace(/\s+/gu,'_'));
  credentials(await api(url+'/recipient-account',p));
 }
 else if(f.id==='transferForm'){p.halaqa_id=Number(p.halaqa_id);const d=await api(url+'/transfer',p);if(d.pending_approval){await openFile(sid,false);status(d.message||'تم رفع طلب النقل للمدير العام');return;}}
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
 if(!staff)html+=panel('إعلانات الحلقة',development.announcements.map(a=>'<article class="halaqat-card"><h3>'+esc(a.title)+'</h3><small>'+esc(a.ring)+(a.expires?' · حتى '+esc(a.expires):'')+'</small><p class="preserve-lines">'+esc(a.body)+'</p>'+(a.can_archive?button('أرشفة الإعلان','data-announcement-archive="'+a.id+'"'):'')+'</article>').join('')||empty('لا توجد إعلانات حالية.'));
 if(role==='owner')html+=panel('نشر إعلان عام أو لحلقة',fold('كتابة إعلان للحلقة',form15('announcementForm',select('halaqa_id','نطاق الإعلان',[(role==='owner'?['','جميع حلقات المسجد']:['','اختر الحلقة']),...data.rings.map(r=>[r.id,r.name])],'',role!=='owner')+input('title','العنوان','','text',true,'minlength="2" maxlength="180"')+textArea('body','نص الإعلان')+input('expires','ينتهي في (اختياري)','','date',false)+'<button>نشر الإعلان داخل النظام</button>')));
 if(!staff)html+=panel('جدول اللقاءات والإجازات',circleCalendar(development.calendars));
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
 else if(['announcementForm','ringAnnouncementForm'].includes(f.id)){p.halaqa_id=p.halaqa_id?Number(p.halaqa_id):null;p.expires=p.expires||null;await api(base()+'/announcements',p);dashboard=true;}
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
 if(b.dataset.studentArchive||b.dataset.accountArchive)run(async()=>{const reason=prompt(b.dataset.active==='true'?'سبب الاستعادة:':'سبب الأرشفة:');if(reason===null)return;const path=b.dataset.studentArchive?'/students/'+b.dataset.studentArchive:'/users/'+b.dataset.accountArchive;const d=await api(base()+path+'/archive',{active:b.dataset.active==='true',reason},'PUT');await load();if(d.pending_approval)status(d.message||'تم رفع الطلب للمدير العام للموافقة');});
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
 out+=panel('إضافة الحلقات الثلاث — 20 طالبًا','<details><summary>مراجعة الأسماء وإضافتها دفعة واحدة</summary><p>الأسماء مطابقة للقائمة النصية التي قدمها المالك: 3 حلقات و20 طالبًا. استكمل رقم جوال الطالب أو ولي أمره واربط حساب المتابعة. بقية البيانات الإضافية اختيارية.</p><a class="halaqat-btn secondary" target="_blank" rel="noopener" href="'+base()+'/roster/source">عرض الورقة الأصلية</a><form id="rosterForm" data-manage="roster" class="halaqat-form">'+rosterDraft.map((g,i)=>'<fieldset><legend>المجموعة '+(i+1)+'</legend>'+input('ring_'+i,'اسم الحلقة (قابل للتعديل)',g.name)+input('teacher_'+i,'اسم المدرس — راجعه',g.teacher)+'<label>الطلاب — اسم كامل في كل سطر<textarea name="students_'+i+'" rows="10" required>'+esc(g.students.join('\n'))+'</textarea></label></fieldset>').join('')+'<label><input type="checkbox" name="reviewed" required checked> أؤكد إضافة القائمة إلى المسجد المحدد</label><p>تضاف ملفات الطلاب بلا حسابات. تحدد لاحقًا الطالب أو ولي الأمر من ملفه وتصدر بيانات الدخول. أسماء المدرسين ترفع كطلبات اعتماد لك. لا تضف المجموعة مرة ثانية.</p><button>إضافة الحلقات والطلاب بعد المراجعة</button></form></details>');
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

// v22: role/account administration and supervisor -> owner approval workflow.
function accessRequestCard(r,owner=false){
 const details=(r.details||[]).map(x=>'<p>'+esc(x)+'</p>').join('');
 const review=r.review_note?'<p><strong>ملاحظة المدير:</strong> '+esc(r.review_note)+'</p>':'';
 const actions=owner&&r.status==='pending'?'<div class="actions">'+button('موافقة','data-change-approve="'+r.id+'"')+button('رفض','data-change-reject="'+r.id+'"')+'</div>':'';
 return '<article class="halaqat-card"><span class="halaqat-badge '+esc(r.status)+'">'+esc(r.status_label)+'</span><h3>'+esc(r.action_label)+'</h3>'+details+'<p><strong>السبب:</strong> '+esc(r.reason||'—')+'</p><small>رفع الطلب: '+esc(r.requested_by||'—')+'</small>'+review+actions+'</article>';
}
function renderAccessManagement(){
 if(!accessOverview||!$('#halaqatWorkspace .halaqat-grid'))return;
 let out='';
 if(data.user.role==='owner'){
  const roleOpts=[['supervisor','مشرف فرع'],['teacher','معلم'],['guardian','ولي أمر'],['student','طالب']];
  const ringOptions=[['','بدون ربط الآن'],...accessOverview.rings.map(x=>[x.id,x.name])];
  const studentOptions=[['','بدون ربط الآن'],...accessOverview.unlinked_students.map(x=>[x.id,x.name])];
  out+=panel('إصدار حساب مستخدم','<form class="halaqat-form" data-access="create-user">'+input('full_name','الاسم الكامل','','text',true,'minlength="2" maxlength="180"')+input('username','اسم المستخدم','','text',true,'minlength="3" maxlength="30"')+select('role','نوع الحساب',roleOpts)+input('email','البريد الإلكتروني (اختياري)','','email',false,'maxlength="200"')+select('halaqa_id','الحلقة للمعلم أو المشرف (اختياري)',ringOptions,'',false)+select('student_id','ملف الطالب للطالب أو ولي الأمر (اختياري)',studentOptions,'',false)+'<small>يصدر النظام رمزًا مؤقتًا ويطلب تغييره عند أول دخول. القوائم تعرض الأسماء بدل الأرقام.</small><button>إصدار الحساب</button></form>');
  out+=panel('إدارة أسماء المستخدمين',accessOverview.users.map(u=>'<details><summary>'+esc(u.name)+' · '+esc(u.role_label)+(u.active?'':' · موقوف')+'</summary><form class="halaqat-form" data-access="edit-user" data-id="'+u.id+'">'+input('full_name','الاسم الكامل',u.name)+input('username','اسم المستخدم',u.username,'text',true,'minlength="3" maxlength="30"')+input('email','البريد الإلكتروني',u.email,'email',false)+select('active','حالة الحساب',[['true','فعال'],['false','موقوف']],String(u.active))+'<small>يمنع تكرار اسم المستخدم. تغييره يلغي جلسات الدخول الحالية للحساب فقط.</small><button>حفظ بيانات الحساب</button></form></details>').join('')||empty('لا توجد حسابات.'));
  out+=panel('طلبات التعديلات الكبيرة · المعلقة '+accessOverview.pending_count,(accessOverview.change_requests.length?accessOverview.change_requests.map(r=>accessRequestCard(r,true)).join(''):empty('لا توجد طلبات تعديل.')));
 }else if(data.user.role==='halaqa_supervisor'){
  out+=panel('رفع تعديل كبير للمدير العام','<details><summary>تعديل اسم أو موعد حلقة</summary><form class="halaqat-form" data-access="change-ring">'+select('ring_id','الحلقة',accessOverview.rings.map(x=>[x.id,x.name]))+input('name','الاسم الجديد')+input('schedule','الموعد / الوصف الجديد','','text',false)+input('reason','سبب التعديل')+'<button>رفع طلب الموافقة</button></form></details><details><summary>تغيير معلمي حلقة</summary><form class="halaqat-form" data-access="change-teachers">'+select('ring_id','الحلقة',accessOverview.rings.map(x=>[x.id,x.name]))+multiSelect('teacher_ids','المعلمون',accessOverview.teachers.map(x=>[x.id,x.name]))+input('reason','سبب التعديل')+'<button>رفع طلب الموافقة</button></form></details><small>نقل الطالب وأرشفته من ملف الطالب يرفعان طلب موافقة أيضًا ولا ينفذان مباشرة.</small>');
  out+=panel('طلبات التعديل المرفوعة',accessOverview.change_requests.length?accessOverview.change_requests.map(r=>accessRequestCard(r,false)).join(''):empty('لم ترفع طلبات تعديل كبيرة بعد.'));
 }
 if(out)$('#halaqatWorkspace .halaqat-grid').insertAdjacentHTML('beforeend',out);
}
document.addEventListener('submit',e=>{
 const f=e.target;if(!f.dataset.access)return;e.preventDefault();run(async()=>{
  const fd=new FormData(f),p=Object.fromEntries(fd),kind=f.dataset.access;
  if(kind==='create-user'){
   p.halaqa_id=p.halaqa_id?Number(p.halaqa_id):null;p.student_id=p.student_id?Number(p.student_id):null;
   credentials(await api('/api/access/mosques/'+mid+'/users',p));
  }else if(kind==='edit-user'){
   p.active=p.active==='true';await api('/api/access/mosques/'+mid+'/users/'+f.dataset.id,p,'PUT');
  }else if(kind==='change-ring'){
   p.action_type='ring_update';p.ring_id=Number(p.ring_id);await api('/api/access/mosques/'+mid+'/change-requests',p);
  }else if(kind==='change-teachers'){
   p.action_type='teacher_assignment';p.ring_id=Number(p.ring_id);p.teacher_ids=fd.getAll('teacher_ids').map(Number);await api('/api/access/mosques/'+mid+'/change-requests',p);
  }
  await load();status(kind.startsWith('change-')?'تم رفع الطلب للمدير العام للموافقة':'تم الحفظ بنجاح');
 });
});
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-change-approve],[data-change-reject]');if(!b)return;run(async()=>{
  const approve=b.hasAttribute('data-change-approve'),id=b.dataset.changeApprove||b.dataset.changeReject;
  const note=prompt(approve?'ملاحظة الموافقة (اختياري):':'سبب الرفض (اختياري):','');if(note===null)return;
  await api('/api/access/mosques/'+mid+'/change-requests/'+id+'/'+(approve?'approve':'reject'),{note});await load();status(approve?'تم اعتماد التعديل وتنفيذه':'تم رفض طلب التعديل');
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
 h+=panel('كشف البيانات الناقصة','<p>يعرض فقط الطلاب الذين لم تُصدر لهم حسابات بأسماء مستخدمين. نقص رقم الجوال أو البيانات الاختيارية لا يُظهر الطالب هنا. إصدار الحساب وربطه من صلاحية المالك.</p><label>بحث<input id="missingSearch" type="search"></label>'+learningData.missing.map(x=>'<div class="halaqat-card" data-missing-name="'+esc(x.name)+'"><strong>'+esc(x.name)+'</strong><p>'+esc(x.ring)+' · '+esc(x.fields.join('، '))+'</p>'+button('استكمال الملف','data-file="'+x.student_id+'"')+'</div>').join('')+(learningData.missing.length?'':empty('جميع الطلاب مرتبطون بحسابات بأسماء مستخدمين.')));
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
 h+=panel('سجل أخطاء التسميع',l.mistakes.map(m=>'<div class="halaqat-card"><strong>'+esc(m.surah_name)+' — آية '+m.ayah+'</strong><p>'+esc(l.kinds[m.kind])+' · '+esc(supportLabels[m.support]||'مراجعة')+' · '+m.day+' · تكرر '+m.repetitions+' مرة · '+(m.resolved?'تمت المعالجة':'يحتاج مراجعة')+'</p><p>'+esc(m.notes)+'</p>'+(editable?button('تعديل / معالجة الخطأ','data-edit-mistake="'+m.id+'"'):'')+'</div>').join('')||empty('لا توجد أخطاء مسجلة.'));
 if(editable)h+=panel('تسجيل موضع خطأ',form19('mistakeForm',input('day','اليوم',today(),'date',true,'max="'+today()+'"')+select('surah','السورة',l.surahs.map((n,i)=>[i+1,n]))+select('ayah','الآية',Array.from({length:studentLearning.ayah_counts[0]},(_,i)=>[i+1,'آية '+(i+1)]))+select('kind','نوع الخطأ',Object.entries(l.kinds))+select('support','مستوى المتابعة',Object.entries(supportLabels))+select('resolved','الحالة',[['false','يحتاج مراجعة'],['true','تمت المعالجة']])+input('notes','وصف الخطأ','','text',false)+'<button>حفظ الخطأ</button>'+button('إلغاء التعديل / خطأ جديد','data-reset-mistake')));
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
 if(b.dataset.editMistake){const m=studentLearning.mistakes.find(m=>m.id===Number(b.dataset.editMistake)),f=$('#mistakeForm');f.dataset.editId=m.id;syncVerse20(m.surah);for(const k of ['day','surah','ayah','kind','support','notes','resolved'])f.elements[k].value=String(m[k]);f.scrollIntoView({behavior:'smooth'});return;}
 if(b.hasAttribute('data-reset-mistake')){const f=$('#mistakeForm');delete f.dataset.editId;f.reset();return;}
 if(b.hasAttribute('data-next-turn'))run(async()=>{await api(base()+'/rings/'+queueState.rid+'/queue/next',{day:queueState.day,current_id:queueState.current_id});renderQueue(await api(base()+'/rings/'+queueState.rid+'/queue?day='+queueState.day),queueState.rid);status('تم تحديث الدور');});
 if(b.dataset.revokeSub)run(async()=>{await api(base()+'/rings/'+b.dataset.ring+'/substitutes/'+b.dataset.revokeSub,{},'DELETE');await load();});
 if(b.dataset.reviewEntry)run(async()=>{await api(base()+'/competitions/'+b.dataset.contest+'/entries/'+b.dataset.reviewEntry+'/review',{status:b.dataset.state},'PUT');await load();});
 if(b.dataset.awardContest)run(async()=>{await api(base()+'/competitions/'+b.dataset.awardContest+'/award',{awarded:b.dataset.awarded==='true'},'PUT');await load();});
 if(b.dataset.activeContest)run(async()=>{await api(base()+'/competitions/'+b.dataset.activeContest+'/active',{awarded:b.dataset.active==='true'},'PUT');await load();});
});
// Version 20: grouped workspace, support plans, live threads and device notifications.
let advanced=null,notificationSettings=null;
const supportLabels={strong:'تثبيت قوي',light:'تثبيت خفيف',review:'مراجعة'};
const activeTabs20={};
const form20=(id,body,attrs='')=>'<form id="'+id+'" data-advanced class="halaqat-form" '+attrs+'>'+body+'</form>';
function showError20(message){let el=$('#toast20');if(!el){el=document.createElement('div');el.id='toast20';el.className='toast20';el.setAttribute('role','alert');document.body.append(el);}el.innerHTML='<span>'+esc(message)+'</span>'+button('إغلاق','data-close-toast');}
function syncVerse20(surah){const f=$('#mistakeForm');if(!f)return;const n=Number(surah||f.elements.surah.value),old=f.elements.ayah.value;f.elements.ayah.innerHTML=Array.from({length:studentLearning.ayah_counts[n-1]},(_,i)=>'<option value="'+(i+1)+'">آية '+(i+1)+'</option>').join('');if(Number(old)<=studentLearning.ayah_counts[n-1])f.elements.ayah.value=old;}
function organize20(id,isFile){
 const root=$('#'+id),grid=root.querySelector('.halaqat-grid');if(!grid)return;
 const groups=isFile?['ملخص الطالب','التسميع والأوراد','الخريطة والخطط','الاختبارات والتقارير','المحادثة','البيانات والحساب']:['اليوم والمتابعة','الطلاب والحلقات','التواصل والمواعيد','الإدارة'];
 const choose=title=>isFile?(/مراسلات|محادث/.test(title)?4:/بيانات الطالب|ملف الطالب|حالة ملف|حساب|نقل الطالب/.test(title)?5:/خريطة|خطة|هدف|علاجية|متباعدة|الإنجاز الأسبوعي/.test(title)?2:/اختبار|تقرير|شهاد/.test(title)?3:/تسميع|ورد|خطأ|أخطاء|منزلية|اعتذار/.test(title)?1:0):(/حساب|مشرف|مدرس|إدارة|مساجد|تعديل|أرشفة|أرشيف|استيراد|إنشاء|إضافة|ميزات|ناقصة/.test(title)?3:/مراسلات|إعلان|اختبار|جدول|اعتذار/.test(title)?2:/طلاب|حلقات|طلبات/.test(title)?1:0);
 const articles=[...grid.children],containers=groups.map((name,i)=>{const e=document.createElement('section');e.className='tab-content';e.id=id+'-group-'+i;e.setAttribute('role','tabpanel');e.setAttribute('aria-label',name);return e;});
 for(const a of articles){const group=choose(a.querySelector('h2')?.textContent||'');containers[group].append(a);if(!isFile&&group===3){const heading=a.querySelector('h2');if(heading){const fold=document.createElement('details'),summary=document.createElement('summary');summary.append(heading);fold.append(summary,...a.childNodes);a.append(fold);a.classList.add('admin-section');}}}
 grid.replaceChildren(...containers);
 root.querySelector('.workspace-tabs')?.remove();const nav=document.createElement('nav');nav.className='workspace-tabs';nav.setAttribute('role','tablist');nav.setAttribute('aria-label',isFile?'أقسام الطالب':'أقسام الحلقة');nav.innerHTML=groups.map((g,i)=>containers[i].children.length?button(g,'role="tab" aria-controls="'+containers[i].id+'" data-tab-root="'+id+'" data-tab="'+i+'"'):'').join('');grid.before(nav);
 const preferred=activeTabs20[id]??0;activate20(id,containers[preferred]?.children.length?preferred:containers.findIndex(x=>x.children.length));
}
function activate20(id,index){activeTabs20[id]=Number(index);const r=$('#'+id);r.querySelectorAll('.tab-content').forEach((p,i)=>p.hidden=i!==Number(index));r.querySelectorAll('[data-tab]').forEach(b=>{const selected=Number(b.dataset.tab)===Number(index);b.setAttribute('aria-selected',String(selected));b.tabIndex=selected?0:-1;});}
function reveal20(target){const g=target?.closest('.tab-content');if(g){const id=g.closest('#studentFile,#halaqatWorkspace').id;activate20(id,Number(g.id.split('-').at(-1)));}for(let p=target?.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;}
async function renderAdvancedDashboard(){
 $('.halaqat-header h1').textContent=data.user.role==='halaqa_student'?(data.user.account_type==='guardian'?'متابعة أبنائك':'رحلتك مع القرآن'):'إدارة حلقات القرآن';
 $('.halaqat-header p').textContent=data.user.role==='halaqa_student'?'الحفظ والمراجعة والتواصل مع معلم الحلقة.':'متابعة الحلقات والطلاب من مكان واحد.';
 let h='';if(data.user.role!=='halaqa_student'){
 const d=await api(base()+'/support-dashboard');h+=panel('التنبيه المبكر للتعثر','<p>مؤشرات متابعة من السجلات، وليست حكمًا على الطالب. الأيام غير المسجلة لا تحتسب غيابًا.</p>'+d.risks.map(r=>'<div class="risk-note"><strong>'+esc(r.name)+'</strong><p>'+esc(r.reasons.join(' · '))+'</p>'+button('فتح الخطة والمتابعة','data-file="'+r.student_id+'"')+'</div>').join('')+(d.risks.length?'':empty('لا توجد مؤشرات تعثر وفق البيانات المسجلة.')));
 h+=panel('دفتر المعلم دون إنترنت','<p>جهّز قائمة اليوم قبل انقطاع الاتصال، ثم سجل الحضور والتسميع وزامن المسودات عند العودة.</p><a class="halaqat-btn" href="/offline?mid='+mid+'">فتح دفتر اليوم</a>');}
 if(data.user.role==='owner'){
 const overview=await api('/api/halaqat/organizations/learning-overview');h+=panel('متابعة الجوامع والجهات',overview.mosques.map(m=>'<div class="student-row"><strong>'+esc(m.name)+'</strong><span>'+m.students+' طالب · '+m.at_risk+' بحاجة متابعة · '+m.active_plans+' خطة علاجية · الحضور '+(m.attendance??'—')+'%</span>'+button('فتح الجهة','data-open-mosque="'+m.id+'"')+'</div>').join('')+'<small>الحضور محسوب من الحضور والغياب المسجلين خلال 30 يومًا. بيانات كل جامع معزولة عن فرق الجوامع الأخرى.</small>');
 h+=panel('تعديل أسماء المستخدمين',form20('renameUsernameForm',select('uid','الحساب',[['','اختر الحساب'],...data.accounts.map(u=>[u.id,u.name+' — '+u.username])])+input('username','اسم المستخدم الجديد','','text',true,'minlength="3" maxlength="30" autocomplete="off"')+'<small>عربي أو إنجليزي أو أرقام و _ أو - دون مسافات. تغيير الاسم ينهي جلسات الحساب؛ أبلغ صاحبه بالاسم الجديد.</small><button>حفظ اسم المستخدم</button>'));}
 $('#halaqatWorkspace .halaqat-grid').insertAdjacentHTML('beforeend',h);
 await renderNotificationSettings();
}
function renderAdvancedFile(){
 const a=advanced,edit=file.can_edit,manager=['owner','halaqa_supervisor'].includes(data.user.role);let h='';
 h+=panel('ملخص المتابعة',a.risk.reasons.length?'<div class="risk-note">'+esc(a.risk.reasons.join(' · '))+'</div>':empty('لا توجد مؤشرات تعثر حاليًا حسب السجلات.') );
 h+=panel('خريطة الأجزاء الثلاثين','<p>حالة الجزء يعتمدها الشيخ مستقلًا عن حالة السور، لتجنب احتساب سورة جزئية كجزء كامل.</p><div class="juz-grid">'+a.juz.map(j=>'<div class="quran-cell state-'+j.status+'"><strong>الجزء '+j.juz+'</strong><span>'+esc(studentDev.quran_states[j.status])+'</span><small>'+esc(j.notes)+'</small></div>').join('')+'</div>'+(edit?fold('تحديث جزء',form20('juzForm',select('juz','الجزء',a.juz.map(j=>[j.juz,'الجزء '+j.juz]))+select('status','حالة الإتقان',Object.entries(studentDev.quran_states))+input('notes','ملاحظات','','text',false)+'<button>اعتماد الجزء</button>')):''));
 h+=panel('المراجعة المتباعدة','<p>مقترحات من أخطاء الطالب وسجل المراجعات المعتمدة، ولا تتحول إلى ورد إلا بعد اعتماد الشيخ.</p>'+a.suggestions.map(r=>'<details><summary>'+esc(r.name)+' · '+r.due+'</summary><p>'+esc(r.reason)+' · '+esc(supportLabels[r.support])+' · آخر مراجعة: '+esc(r.last_review||'غير مسجلة')+'</p>'+(edit?form20('reviewApprove'+r.surah,input('due','موعد المراجعة',r.due<today()?today():r.due,'date')+input('notes','تعليمات ونطاق الآيات','','text',false)+'<button>اعتماد ورد المراجعة</button>','data-kind="reviewApprove" data-surah="'+r.surah+'"')+(r.assignment_id?form20('reviewResult'+r.surah,input('day','يوم التسميع',today(),'date')+input('score','درجة الإتقان / 10',8,'number',true,'min="0" max="10"')+'<button>تسجيل النتيجة وحساب الموعد التالي</button>','data-kind="reviewResult" data-surah="'+r.surah+'"'):''):'')+'</details>').join('')+(a.suggestions.length?'':empty('ابدأ بتحديث خريطة السور أو تسجيل مواضع الأخطاء.')));
 h+=panel('الخطط العلاجية',a.plans.map(p=>'<details open><summary>'+esc(p.title)+' · '+({active:'نشطة',completed:'مكتملة',cancelled:'ملغاة'}[p.status])+'</summary><p>'+p.start+' — '+p.end+'</p>'+p.tasks.map((t,i)=>'<label><input type="checkbox" data-plan-task="'+p.id+'" data-index="'+i+'" '+(t.done?'checked':'')+' '+(!edit?'disabled':'')+'> '+esc(t.text)+'</label>').join('')+'<p>'+esc(p.outcome)+'</p>'+(edit?form20('planUpdate'+p.id,select('status','الحالة',[['active','نشطة'],['completed','مكتملة'],['cancelled','ملغاة']],p.status)+input('outcome','النتيجة والملاحظات',p.outcome,'text',false)+'<button>حفظ متابعة الخطة</button>','data-kind="planUpdate" data-id="'+p.id+'"'):'')+'</details>').join('')+(edit?fold('إنشاء خطة قصيرة',form20('supportPlanForm',input('title','هدف الخطة')+input('start','البداية',today(),'date')+input('end','النهاية',today(),'date')+textArea('tasks','المهام: كل مهمة في سطر مستقل','',6000)+'<button>إنشاء الخطة</button>')):'')+(a.plans.length?'':empty('لا توجد خطة علاجية بعد.')));
 h+=panel('حجز مختبر واعتماد الانتقال',a.bookings.map(b=>'<div class="halaqat-card"><strong>'+esc(b.title)+'</strong><p>'+esc(b.examiner)+' · '+b.due+' الساعة '+b.time+' بتوقيت الرياض</p><p>المستوى التالي: '+esc(b.next_level||'غير محدد')+' · '+(b.approved?'الانتقال معتمد':'لم يعتمد الانتقال')+'</p>'+(manager&&!b.approved?button('اعتماد الانتقال بعد الاجتياز','data-promote="'+b.exam_id+'"'):'')+'</div>').join('')+(manager?fold('تعيين المختبر والموعد',form20('bookingForm',select('exam_id','الاختبار القادم',[['','اختر الاختبار'],...studentDev.exams.filter(e=>e.status==='scheduled').map(e=>[e.id,e.title+' — '+e.due])])+select('examiner_id','المختبر',[['','اختر المختبر'],...a.teachers.map(t=>[t.id,t.name])])+input('time','الساعة بتوقيت الرياض','16:00','time')+input('next_level','المستوى بعد الاجتياز','','text',false)+'<button>حفظ الحجز</button>')):''));
 $('#studentFile .halaqat-grid').insertAdjacentHTML('beforeend',h);
 const chat=$('#messageRows');if(chat){chat.classList.add('chat-thread');chat.setAttribute('aria-live','polite');chat.closest('.halaqat-panel').querySelector('h2').textContent='المحادثة المباشرة';}
 syncVerse20();
}
async function renderNotificationSettings(){
 notificationSettings=await api('/api/notifications/settings');const n=notificationSettings;
 let box=$('#notificationBox');if(!box){box=document.createElement('details');box.id='notificationBox';box.className='notification-settings';$('.halaqat-toolbar').after(box);}
 box.innerHTML='<summary>إشعارات الجوال والبريد</summary><p>على الآيفون: أضف الموقع للشاشة الرئيسية، افتحه من أيقونته ثم اضغط تفعيل الإشعارات واسمح بها. يتطلب جهازًا ومتصفحًا يدعمان Web Push.</p><div class="actions">'+button('تفعيل إشعارات هذا الجهاز','data-enable-push')+button('إيقاف إشعارات هذا الجهاز','data-disable-push')+button('إرسال تنبيه تجريبي','data-test-push')+button('تحديث حالة التسليم','data-refresh-push')+'</div>'+form20('notificationPrefs','<label><input type="checkbox" name="push_enabled" '+(n.push_enabled?'checked':'')+'> إشعارات الأجهزة</label><label><input type="checkbox" name="email_enabled" '+(n.email_enabled?'checked':'')+'> التنبيهات بالبريد الموثق</label>'+Object.entries(n.labels).map(([k,v])=>'<label><input type="checkbox" name="category" value="'+k+'" '+(n.categories.includes(k)?'checked':'')+'> '+v+'</label>').join('')+'<button>حفظ اختيارات التنبيهات</button>')+'<p>البريد: '+esc(n.email||'غير مسجل')+' · '+(n.verified?'موثق':'غير موثق')+'</p>'+(n.smtp_ready?form20('notificationEmail',input('email','بريدك الإلكتروني',n.email,'email')+'<button>إرسال رمز التوثيق</button>')+(!n.verified?form20('notificationVerify',input('code','رمز التوثيق','','text',true,'inputmode="numeric" pattern="[0-9]{6}" maxlength="6"')+'<button>توثيق البريد</button>'):''):'<p>إرسال البريد لم يُفعّل على الخادم بعد؛ يمكن استخدام إشعارات الجهاز.</p>')+'<p>حالة الإرسال: '+Object.entries(n.delivery).map(([k,v])=>esc(({pending:'بانتظار الإرسال',sending:'جارٍ الإرسال',sent:'سُلّم لمزوّد الإرسال',failed:'تعذر الإرسال',expired:'اشتراك منتهٍ',cancelled:'ملغى'}[k]||k))+': '+v).join(' · ')+'</p><small>التسليم لمزوّد الإرسال لا يضمن ظهور الإشعار إذا منعته إعدادات الجهاز.</small>';
 if('serviceWorker'in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
}
document.addEventListener('submit',e=>{const f=e.target;if(!f.hasAttribute('data-advanced'))return;e.preventDefault();run(async()=>{
 const fd=new FormData(f),p=Object.fromEntries(fd),url=base()+'/students/'+sid;let settings=false;
 if(f.id==='juzForm'){const j=p.juz;delete p.juz;await api(url+'/juz/'+j,p,'PUT');}
 else if(f.dataset.kind==='reviewApprove')await api(url+'/review/'+f.dataset.surah+'/approve',p);
 else if(f.dataset.kind==='reviewResult'){p.score=Number(p.score);await api(url+'/review/'+f.dataset.surah+'/result',p);}
 else if(f.id==='supportPlanForm'){p.tasks=p.tasks.split('\n').map(x=>x.trim()).filter(Boolean).map(text=>({text,done:false}));await api(url+'/support-plans',p);}
 else if(f.dataset.kind==='planUpdate'){const original=advanced.plans.find(x=>x.id===Number(f.dataset.id));const tasks=original.tasks.map((t,i)=>({...t,done:!!document.querySelector('[data-plan-task="'+original.id+'"][data-index="'+i+'"]').checked}));await api(url+'/support-plans/'+original.id,{title:original.title,start:original.start,end:original.end,tasks,status:p.status,outcome:p.outcome},'PUT');}
 else if(f.id==='bookingForm'){const id=p.exam_id;delete p.exam_id;p.examiner_id=Number(p.examiner_id);await api(url+'/organized-exams/'+id+'/booking',p,'PUT');}
 else if(f.id==='renameUsernameForm'){const r=await api(base()+'/accounts/'+p.uid+'/username',{username:p.username},'PUT');if(r.self_changed){location.assign('/login');return;}await load();status('تم تغيير اسم المستخدم وإنهاء جلساته السابقة');return;}
 else if(f.id==='notificationPrefs'){await api('/api/notifications/settings',{push_enabled:fd.has('push_enabled'),email_enabled:fd.has('email_enabled'),categories:fd.getAll('category')},'PUT');settings=true;}
 else if(f.id==='notificationEmail'){await api('/api/notifications/email',p);settings=true;}
 else if(f.id==='notificationVerify'){await api('/api/notifications/email/verify',p);settings=true;}
 if(settings){await renderNotificationSettings();$('#notificationBox').open=true;}else await openFile(sid,false);status('تم الحفظ بنجاح');
});});
document.addEventListener('change',e=>{if(e.target.form?.id==='mistakeForm'&&e.target.name==='surah')syncVerse20();if(e.target.form?.id==='juzForm'&&e.target.name==='juz'){const j=advanced.juz.find(x=>x.juz===Number(e.target.value));e.target.form.elements.status.value=j.status;e.target.form.elements.notes.value=j.notes;}});
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
 if(b.hasAttribute('data-close-toast'))$('#toast20')?.remove();
 if(b.dataset.tab!==undefined)activate20(b.dataset.tabRoot,Number(b.dataset.tab));
 if(b.dataset.promote)run(async()=>{await api(base()+'/students/'+sid+'/organized-exams/'+b.dataset.promote+'/promote',{});await openFile(sid,false);status('تم اعتماد انتقال المستوى');});
 if(b.hasAttribute('data-enable-push'))run(async()=>{
  if(!('serviceWorker'in navigator)||!('PushManager'in window)||!('Notification'in window))throw Error('المتصفح لا يدعم الإشعارات. على الآيفون افتح الموقع من الشاشة الرئيسية.');
  const permission=await Notification.requestPermission();if(permission!=='granted')throw Error('لم تمنح إذن الإشعارات؛ عدّل إعدادات الموقع في جهازك');
  await navigator.serviceWorker.register('/sw.js');const reg=await navigator.serviceWorker.ready;
  const raw=notificationSettings.public_key.replace(/-/g,'+').replace(/_/g,'/'),key=Uint8Array.from(atob(raw+'='.repeat((4-raw.length%4)%4)),c=>c.charCodeAt(0));
  const sub=await reg.pushManager.getSubscription()||await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:key});const j=sub.toJSON();await api('/api/notifications/subscribe',{endpoint:j.endpoint,keys:j.keys});status('تم تفعيل إشعارات هذا الجهاز');
 });
 if(b.hasAttribute('data-disable-push'))run(async()=>{const reg=await navigator.serviceWorker.getRegistration('/');const sub=await reg?.pushManager.getSubscription();if(sub){await api('/api/notifications/unsubscribe',{endpoint:sub.endpoint});await sub.unsubscribe();}status('تم إيقاف إشعارات هذا الجهاز');});
 if(b.hasAttribute('data-test-push'))run(async()=>{const r=await api('/api/notifications/test',{});status(r.message);await renderNotificationSettings();$('#notificationBox').open=true;});
 if(b.hasAttribute('data-refresh-push'))run(async()=>{await renderNotificationSettings();$('#notificationBox').open=true;status('تم تحديث حالة التسليم');});
 // Existing cross-section actions still reveal their target after tab grouping.
 if(b.dataset.progress||b.dataset.editMistake||b.dataset.amend)setTimeout(()=>{const target=b.dataset.progress?$('#progressForm'):b.dataset.editMistake?$('#mistakeForm'):$('#studentRequestForm');reveal20(target);target?.scrollIntoView({behavior:'smooth'});},0);
});
document.addEventListener('keydown',e=>{const nav=e.target.closest('.workspace-tabs');if(!nav||!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const buttons=[...nav.querySelectorAll('button')],at=buttons.indexOf(e.target);const next=e.key==='Home'?0:e.key==='End'?buttons.length-1:(at+(e.key==='ArrowLeft'?1:-1)+buttons.length)%buttons.length;buttons[next].click();buttons[next].focus();});
// Update the visible thread without replacing the user's draft. No public chat channels.
let polling20=false;
setInterval(async()=>{if(polling20||busy||document.hidden||!sid||$('#studentFile').hidden||activeTabs20.studentFile!==4)return;polling20=true;const current=sid;
 try{const t=await api(base()+'/students/'+current+'/messages');if(current!==sid)return;const rows=$('#messageRows');if(rows&&JSON.stringify(t.messages)!==JSON.stringify(thread.messages)){thread=t;rows.innerHTML=messageRows(t.messages);rows.scrollTop=rows.scrollHeight;}if(t.messages.length)await api(base()+'/students/'+current+'/messages/read',{last_id:t.messages.at(-1).id});}catch{}finally{polling20=false;}
},8000);
document.addEventListener('submit',e=>{if(e.target.matches('form[action="/logout"]')){const req=indexedDB.open('halaqat-offline',1);req.onsuccess=()=>{const db=req.result;if(db.objectStoreNames.contains('records'))db.transaction('records','readwrite').objectStore('records').clear();db.close();};}});

})();
