(()=>{
'use strict';
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const roleCopy={
 owner:['المدير العام','إدارة النظام كاملة، إصدار الحسابات، اعتماد التعديلات ومراجعة السجل.'],
 supervisor:['مشرف الفرع','إدارة حلقات وطلاب الفرع ورفع التعديلات الحساسة للمدير العام.'],
 teacher:['المعلم','متابعة حلقاتك وطلابك والحضور والحفظ والمراجعة والتقييم.'],
 guardian:['ولي الأمر','متابعة الأبناء المرتبطين بحسابك فقط.'],
 student:['الطالب','متابعة حلقتك وحضورك وحفظك ومراجعتك وإنجازك.']
};
const stateLabel={pending:'بانتظار الموافقة',approved:'معتمد',rejected:'مرفوض',cancelled:'ملغي'};
let me=null,mid=0,directory=null,tools=null,busy=false;

async function api(path,body,method='POST'){
 const opt={cache:'no-store',headers:{}};
 if(body!==undefined){opt.method=method;opt.headers['Content-Type']='application/json';opt.body=JSON.stringify(body);}
 const r=await fetch(path,opt);let d={};try{d=await r.json();}catch(_){d={detail:'تعذر قراءة الاستجابة'};}
 if(!r.ok){if(d.redirect)location.assign(d.redirect);throw Error(typeof d.detail==='string'?d.detail:'تعذر إتمام الطلب');}
 return d;
}
function toast(message,ok=true){
 let box=$('#roleToast');if(!box){box=document.createElement('div');box.id='roleToast';box.className='role-toast';document.body.append(box);}
 box.textContent=message;box.classList.toggle('error',!ok);box.hidden=false;clearTimeout(box._timer);box._timer=setTimeout(()=>box.hidden=true,4200);
}
function credentials(d){
 let box=$('#roleCredentialBox');if(!box){box=document.createElement('div');box.id='roleCredentialBox';box.className='credentials role-credentials';tools?.prepend(box);}
 box.hidden=false;box.innerHTML='<strong>بيانات الدخول الجديدة</strong><p>اسم المستخدم: <code>'+esc(d.user?.username||d.username)+'</code></p><p>الرمز المؤقت: <code>'+esc(d.temporary_password||'')+'</code></p><small>احفظ الرمز الآن؛ يجب تغييره عند أول دخول.</small>';
 box.scrollIntoView({behavior:'smooth',block:'center'});
}
function ensureShell(){
 const main=$('#halaqatApp');if(!main||!me)return;
 main.dataset.portalRole=me.portal_role;main.classList.add('portal-role-'+me.portal_role);
 let hero=$('#roleHero');if(!hero){hero=document.createElement('section');hero.id='roleHero';hero.className='role-hero';const toolbar=$('.halaqat-toolbar');toolbar?.insertAdjacentElement('beforebegin',hero);}
 const copy=roleCopy[me.portal_role]||['الحساب',''];
 hero.innerHTML='<div><span class="role-chip">'+esc(copy[0])+'</span><h2>مرحبًا، '+esc(me.name)+'</h2><p>'+esc(copy[1])+'</p></div><nav id="roleNav" class="role-nav" aria-label="تنقل الواجهة"></nav>';
 let t=$('#roleTools');if(!t){t=document.createElement('section');t.id='roleTools';t.className='role-tools';$('#halaqatStats')?.insertAdjacentElement('afterend',t);}tools=t;
 refreshNav();
}
function refreshNav(){
 const nav=$('#roleNav');if(!nav)return;
 const items=[];
 const add=(label,sel)=>{if($(sel))items.push([label,sel]);};
 add('الرئيسية','#halaqatStats');
 if(['owner','supervisor','teacher'].includes(me?.portal_role))add('الحلقات','#halaqatWorkspace');
 if(['owner','supervisor','teacher'].includes(me?.portal_role))add('الطلاب','#studentRingFilter');
 if(me?.portal_role==='owner'||me?.portal_role==='supervisor')add(me.portal_role==='owner'?'الإدارة والموافقات':'طلبات التعديل','#roleTools');
 if(['guardian','student'].includes(me?.portal_role))add(me.portal_role==='guardian'?'الأبناء':'ملفي','#halaqatWorkspace');
 nav.innerHTML=items.map(([l,s])=>'<button type="button" data-scroll="'+esc(s)+'">'+esc(l)+'</button>').join('');
}
function formField(name,label,type='text',attrs=''){return '<label>'+esc(label)+'<input name="'+esc(name)+'" type="'+type+'" '+attrs+'></label>';}
function options(rows,placeholder='اختر'){return '<option value="">'+esc(placeholder)+'</option>'+rows.map(x=>'<option value="'+x.id+'">'+esc(x.name)+'</option>').join('');}
function selectField(name,label,rows,placeholder='اختر',multiple=false){return '<label>'+esc(label)+'<input class="select-search" type="search" placeholder="بحث بالاسم" data-filter="'+esc(name)+'"><select name="'+esc(name)+'" '+(multiple?'multiple size="5"':'')+'>'+options(rows,placeholder)+'</select></label>';}
function roleOptions(){return [['supervisor','مشرف فرع'],['teacher','معلم'],['student','طالب'],['guardian','ولي أمر']].map(([v,t])=>'<option value="'+v+'">'+t+'</option>').join('');}

async function currentMid(){
 for(let i=0;i<40;i++){const s=$('#halaqatMosque');if(s&&s.value)return Number(s.value);await new Promise(r=>setTimeout(r,100));}
 return Number(me?.mosque_id||0);
}
async function loadDirectory(){if(!mid)return;directory=await api('/api/access/mosques/'+mid+'/directory',undefined,'GET');}

function userCard(u){
 return '<details class="role-user-card" data-user-card="'+u.id+'"><summary><span><strong>'+esc(u.name)+'</strong><small>'+esc(u.role_label)+' · '+esc(u.username)+(u.active?'':' · معطل')+'</small></span><span class="status-dot '+(u.active?'active':'')+'"></span></summary><form class="role-form role-user-edit" data-user-id="'+u.id+'">'+formField('full_name','الاسم الكامل','text','value="'+esc(u.name)+'" required minlength="2" maxlength="180"')+formField('username','اسم المستخدم','text','value="'+esc(u.username)+'" required minlength="3" maxlength="30"')+formField('email','البريد الإلكتروني','email','value="'+esc(u.email||'')+'"')+'<label class="toggle-line"><input name="active" type="checkbox" '+(u.active?'checked':'')+'> الحساب فعال</label><div class="role-actions"><button type="submit">حفظ التعديل</button><button type="button" class="secondary" data-issue-password="'+u.id+'">إصدار رمز مؤقت</button></div></form>'+(u.children?.length?'<p class="role-children">الأبناء: '+u.children.map(c=>esc(c.name)).join('، ')+'</p>':'')+'</details>';
}
async function renderOwner(){
 const [ud,cr,al]=await Promise.all([api('/api/access/mosques/'+mid+'/users',undefined,'GET'),api('/api/access/mosques/'+mid+'/change-requests',undefined,'GET'),api('/api/access/mosques/'+mid+'/audit',undefined,'GET')]);
 const pending=cr.requests.filter(x=>x.status==='pending');
 tools.innerHTML='<div id="roleCredentialBox" class="credentials role-credentials" hidden></div><div class="role-tool-grid">'+
 '<article class="role-panel"><div class="role-panel-head"><div><span class="eyebrow">إدارة مركزية</span><h2>إضافة وإصدار المستخدمين</h2></div></div><form id="roleCreateUser" class="role-form">'+formField('full_name','الاسم الكامل','text','required minlength="2" maxlength="180"')+formField('username','اسم المستخدم','text','required minlength="3" maxlength="30"')+formField('email','البريد الإلكتروني (اختياري)','email')+'<label>الدور<select name="role">'+roleOptions()+'</select></label><label class="role-ring-field">الحلقة<select name="halaqa_id">'+options(directory.rings,'اختر الحلقة')+'</select></label>'+formField('temporary_password','رمز مؤقت (اختياري)','password','minlength="8" maxlength="128"')+'<button type="submit">إنشاء الحساب</button><small>المعلم والطالب يرتبطان بحلقة. ولي الأمر يمكن ربط أبنائه لاحقًا من اعتماد ملفات الطلاب.</small></form></article>'+
 '<article class="role-panel approval-panel"><div class="role-panel-head"><div><span class="eyebrow">اعتماد المدير العام</span><h2>طلبات التعديلات الكبيرة <span class="count-badge">'+pending.length+'</span></h2></div></div><div id="approvalList">'+changeCards(cr.requests,true)+'</div></article></div>'+
 '<article class="role-panel user-admin"><div class="role-panel-head"><div><span class="eyebrow">الحسابات</span><h2>المستخدمون</h2></div><input id="roleUserSearch" type="search" placeholder="ابحث بالاسم أو اسم المستخدم"></div><div id="roleUserList">'+(ud.users.map(userCard).join('')||'<p class="empty">لا توجد حسابات بعد.</p>')+'</div></article>'+
 '<article class="role-panel audit-panel"><div class="role-panel-head"><div><span class="eyebrow">الرقابة</span><h2>سجل العمليات</h2></div></div><div class="audit-list">'+auditRows(al.items)+'</div></article>';
 toggleCreateRing();bindSearches();
}
function auditRows(rows){
 if(!rows?.length)return '<p class="empty">لا توجد عمليات مسجلة بعد.</p>';
 return rows.slice(0,80).map(x=>'<div class="audit-row"><div><strong>'+esc(x.action_label)+'</strong><small>'+esc(x.actor)+'</small></div><time>'+esc(String(x.created_at||'').replace('T',' ').replace('Z','').slice(0,16))+'</time></div>').join('');
}
function changeCards(rows,ownerMode=false){
 if(!rows.length)return '<p class="empty">لا توجد طلبات تعديل.</p>';
 return rows.map(r=>'<article class="change-card '+esc(r.status)+'"><div class="change-title"><span class="halaqat-badge '+esc(r.status)+'">'+esc(stateLabel[r.status]||r.status)+'</span><strong>'+esc(r.action_label)+'</strong></div><h3>'+esc(r.target||'')+'</h3><div class="change-diff"><div><small>قبل</small><p>'+esc(r.before_label||'—')+'</p></div><div><small>بعد</small><p>'+esc(r.after_label||'—')+'</p></div></div><p><strong>السبب:</strong> '+esc(r.reason)+'</p><small>مقدم الطلب: '+esc(r.requester)+(r.reviewer?' · المراجع: '+esc(r.reviewer):'')+'</small>'+(r.review_note?'<p class="review-note">ملاحظة الاعتماد: '+esc(r.review_note)+'</p>':'')+(r.status==='pending'?'<div class="role-actions">'+(ownerMode?'<button type="button" data-approve-change="'+r.id+'">موافقة وتنفيذ</button><button type="button" class="danger" data-reject-change="'+r.id+'">رفض</button>':'<button type="button" class="secondary" data-cancel-change="'+r.id+'">إلغاء الطلب</button>')+'</div>':'')+'</article>').join('');
}
function requestForms(){
 const rings=directory.rings||[],students=directory.students||[],teachers=directory.teachers||[],targets=(directory.deactivation_targets||[]).filter(x=>x.active);
 return '<div class="role-tool-grid">'+
 '<article class="role-panel"><span class="eyebrow">يتطلب اعتماد المدير</span><h2>نقل طالب</h2><form class="role-form change-form" data-action="student_transfer">'+selectField('student_id','الطالب',students,'اختر الطالب')+selectField('target_halaqa_id','الحلقة الجديدة',rings,'اختر الحلقة')+formField('reason','سبب النقل','text','required minlength="3" maxlength="1500"')+'<button>رفع طلب النقل</button></form></article>'+
 '<article class="role-panel"><span class="eyebrow">يتطلب اعتماد المدير</span><h2>تعديل حلقة</h2><form class="role-form change-form" data-action="ring_update">'+selectField('ring_id','الحلقة',rings,'اختر الحلقة')+formField('name','الاسم الجديد','text','required minlength="2" maxlength="180"')+formField('schedule','الجدول','text','maxlength="500"')+formField('reason','سبب التعديل','text','required minlength="3" maxlength="1500"')+'<button>رفع طلب التعديل</button></form></article>'+
 '<article class="role-panel"><span class="eyebrow">يتطلب اعتماد المدير</span><h2>تغيير معلمي حلقة</h2><form class="role-form change-form" data-action="teacher_assignment">'+selectField('ring_id','الحلقة',rings,'اختر الحلقة')+selectField('teacher_ids','المعلمون',teachers,'اختر المعلمين',true)+formField('reason','سبب التغيير','text','required minlength="3" maxlength="1500"')+'<button>رفع طلب التغيير</button></form></article>'+
 '<article class="role-panel"><span class="eyebrow">يتطلب اعتماد المدير</span><h2>تعطيل حساب</h2><form class="role-form change-form" data-action="deactivate_user">'+selectField('user_id','المستخدم',targets,'اختر المستخدم')+formField('reason','سبب التعطيل','text','required minlength="3" maxlength="1500"')+'<button>رفع طلب التعطيل</button></form></article></div>';
}
async function renderSupervisor(){
 const cr=await api('/api/access/mosques/'+mid+'/change-requests',undefined,'GET');
 tools.innerHTML='<div class="role-supervisor-intro"><h2>طلبات التعديلات الكبيرة</h2><p>التغييرات الحساسة لا تُطبق مباشرة. تُرسل للمدير العام ويظهر له الفرق قبل وبعد للموافقة أو الرفض.</p></div>'+requestForms()+'<article class="role-panel"><h2>طلباتي السابقة</h2>'+changeCards(cr.requests,false)+'</article>';bindSearches();
}
function renderSimple(){
 const text={teacher:'واجهة المعلم تعرض فقط حلقاتك وطلابك والأدوات المسموحة لك.',guardian:'يعرض حسابك الأبناء المرتبطين بك فقط، ولا يمكن الوصول إلى بيانات أسر أخرى.',student:'يعرض حسابك ملفك الدراسي فقط، ولا يمكن الوصول إلى ملفات طلاب آخرين.'}[me.portal_role];
 tools.innerHTML='<article class="role-panel role-scope-note"><h2>نطاق حسابك</h2><p>'+esc(text||'')+'</p></article>';
}
async function renderTools(){
 if(!me||!mid)return;tools.innerHTML='<p class="empty">جارٍ تجهيز واجهتك…</p>';
 await loadDirectory();
 if(me.portal_role==='owner')await renderOwner();else if(me.portal_role==='supervisor')await renderSupervisor();else renderSimple();
 refreshNav();
}
function bindSearches(){
 $$('.select-search',tools).forEach(inp=>{if(inp.dataset.bound)return;inp.dataset.bound='1';inp.addEventListener('input',()=>{const sel=$('select[name="'+inp.dataset.filter+'"]',inp.parentElement);if(!sel)return;const q=inp.value.trim();[...sel.options].forEach((o,i)=>o.hidden=i>0&&q&&!o.textContent.includes(q));});});
}
function toggleCreateRing(){const f=$('#roleCreateUser');if(!f)return;const role=f.elements.role.value;const wrap=$('.role-ring-field',f);if(wrap){wrap.hidden=!['teacher','student'].includes(role);f.elements.halaqa_id.required=['teacher','student'].includes(role);}}
function formJSON(form){const fd=new FormData(form),o=Object.fromEntries(fd.entries());return o;}
async function onSubmit(form){
 if(busy)return;busy=true;try{
  if(form.id==='roleCreateUser'){
   const p=formJSON(form);p.halaqa_id=p.halaqa_id?Number(p.halaqa_id):null;const d=await api('/api/access/mosques/'+mid+'/users',p);await renderTools();credentials(d);toast('تم إنشاء الحساب');return;
  }
  if(form.matches('.role-user-edit')){
   const p=formJSON(form);p.active=form.elements.active.checked;const uid=form.dataset.userId;await api('/api/access/mosques/'+mid+'/users/'+uid,p,'PUT');toast('تم حفظ بيانات المستخدم');await renderTools();return;
  }
  if(form.matches('.change-form')){
   const p=formJSON(form);p.action_type=form.dataset.action;
   for(const k of ['student_id','target_halaqa_id','ring_id','user_id'])p[k]=p[k]?Number(p[k]):null;
   if(form.dataset.action==='teacher_assignment')p.teacher_ids=[...form.elements.teacher_ids.selectedOptions].map(o=>Number(o.value)).filter(Boolean);else p.teacher_ids=[];
   await api('/api/access/mosques/'+mid+'/change-requests',p);toast('تم رفع الطلب للمدير العام');await renderTools();return;
  }
 }catch(e){toast(e.message,false);}finally{busy=false;}
}
async function onClick(btn){
 if(btn.dataset.scroll){const el=$(btn.dataset.scroll);el?.scrollIntoView({behavior:'smooth',block:'start'});return;}
 try{
  if(btn.dataset.issuePassword){if(!confirm('سيتم إلغاء جلسات المستخدم الحالية وإصدار رمز مؤقت جديد. متابعة؟'))return;const d=await api('/api/halaqat/mosques/'+mid+'/users/'+btn.dataset.issuePassword+'/reset',{});credentials(d);toast('تم إصدار رمز مؤقت');return;}
  if(btn.dataset.approveChange){const note=prompt('ملاحظة الاعتماد (اختيارية):','');if(note===null)return;await api('/api/access/mosques/'+mid+'/change-requests/'+btn.dataset.approveChange+'/approve',{note});toast('تمت الموافقة وتنفيذ التعديل');await renderTools();return;}
  if(btn.dataset.rejectChange){const note=prompt('سبب الرفض:','');if(note===null)return;await api('/api/access/mosques/'+mid+'/change-requests/'+btn.dataset.rejectChange+'/reject',{note});toast('تم رفض الطلب');await renderTools();return;}
  if(btn.dataset.cancelChange){if(!confirm('إلغاء هذا الطلب المعلق؟'))return;await api('/api/access/mosques/'+mid+'/change-requests/'+btn.dataset.cancelChange+'/cancel',{});toast('تم إلغاء الطلب');await renderTools();return;}
 }catch(e){toast(e.message,false);}
}
function filterUsers(){const q=($('#roleUserSearch')?.value||'').trim();$$('[data-user-card]',tools).forEach(c=>c.hidden=q&&!c.textContent.includes(q));}
function panelNavDebounced(){clearTimeout(panelNavDebounced.t);panelNavDebounced.t=setTimeout(refreshNav,100);}
async function init(){
 try{me=await api('/api/access/me',undefined,'GET');ensureShell();mid=await currentMid();if(!mid)throw Error('تعذر تحديد الفرع');await renderTools();
  const mosque=$('#halaqatMosque');mosque?.addEventListener('change',async()=>{mid=Number(mosque.value);await renderTools();});
  const workspace=$('#halaqatWorkspace');if(workspace)new MutationObserver(panelNavDebounced).observe(workspace,{childList:true,subtree:true});
 }catch(e){toast(e.message,false);}
}
document.addEventListener('submit',e=>{if(e.target.matches('#roleCreateUser,.role-user-edit,.change-form')){e.preventDefault();onSubmit(e.target);}});
document.addEventListener('click',e=>{const b=e.target.closest('button');if(b&&(b.dataset.scroll||b.dataset.issuePassword||b.dataset.approveChange||b.dataset.rejectChange||b.dataset.cancelChange))onClick(b);});
document.addEventListener('change',e=>{if(e.target.matches('#roleCreateUser [name="role"]'))toggleCreateRing();if(e.target.matches('.change-form [name="ring_id"]')&&e.target.form?.dataset.action==='ring_update'){const r=directory?.rings?.find(x=>x.id===Number(e.target.value));if(r){e.target.form.elements.name.value=r.name;e.target.form.elements.schedule.value=r.schedule||'';}}});
document.addEventListener('input',e=>{if(e.target.id==='roleUserSearch')filterUsers();});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
