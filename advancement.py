import hashlib, json
from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, model_validator
from sqlalchemy import select
from app.db.session import get_db
from app.models import (JuzMastery, ReviewSchedule, SupportPlan, ExamBooking, OfflineReceipt, User,
    QuranRecord, RecitationMistake, HalaqaProgress, Assignment, OrganizedExam, OrganizedResult, StudentExam, Halaqa, Mosque)
from app.api.halaqat import Input, ProgressInput, _require, _actor, _ring_ids_for, PORTAL_ROLES, STUDENT_ROLE, TEACHER_ROLE, SUPERVISOR_ROLE, add_progress
from app.api.student_file import access_student, progress_pack, today
from app.api.development import active_students, QuranInput
from app.api.routes import audit
from app.services.quran_catalog import SURAH_NAMES

router=APIRouter(prefix='/api/halaqat')

class UsernameInput(Input):
    username:str=Field(min_length=3,max_length=30)

@router.put('/mosques/{mid}/accounts/{uid}/username')
def rename_username(mid:int,uid:int,data:UsernameInput,request:Request,db=Depends(get_db)):
    from app.api.halaqat import _clean_username, _ensure_username
    from app.models import AuthSession
    from sqlalchemy import delete
    u=_require(request,db,mid,{'owner'});target=db.get(User,uid)
    if not target or (target.mosque_id!=mid and target.id!=u.id):raise HTTPException(404,'الحساب غير موجود في المسجد')
    name=_clean_username(data.username,required=True)
    if name!=target.username:
        _ensure_username(db,name);target.username=name
        db.execute(delete(AuthSession).where(AuthSession.user_id==uid))
        audit(db,u.id,mid,'username_changed',str(uid));db.commit()
    return {'ok':True,'self_changed':uid==u.id,'username':name}

def risks(db,s):
    rows=db.scalars(select(HalaqaProgress).where(HalaqaProgress.student_id==s.id,HalaqaProgress.day>=today()-timedelta(days=29))).all()
    absent=sum(p.attendance=='absent' for p in rows)
    scores=[p.memorization_score for p in rows if p.attendance=='present' and p.memorization_score is not None]
    overdue=len(db.scalars(select(Assignment).where(Assignment.student_id==s.id,Assignment.status=='pending',Assignment.due<today())).all())
    reasons=[]
    if absent>=3:reasons.append(f'{absent} أيام غياب مسجلة خلال 30 يومًا')
    if len(scores)>=3 and sum(scores)/len(scores)<6:reasons.append('متوسط الحفظ أقل من 6/10 في ثلاثة تقييمات أو أكثر')
    if overdue>=2:reasons.append(f'{overdue} أوراد تجاوزت الموعد ولم تعتمد نتيجتها')
    return {'student_id':s.id,'name':s.full_name,'reasons':reasons,'severity':'high' if len(reasons)>=2 else 'followup','recorded_days':len(rows)}

@router.get('/mosques/{mid}/support-dashboard')
def dashboard(mid:int,request:Request,db=Depends(get_db)):
    u=_require(request,db,mid,PORTAL_ROLES-{STUDENT_ROLE})
    return {'risks':[r for s in active_students(db,u,mid) if (r:=risks(db,s))['reasons']]}

@router.get('/organizations/learning-overview')
def org_overview(request:Request,db=Depends(get_db)):
    u=_require(request,db,1,{'owner'});out=[]
    for m in db.scalars(select(Mosque).order_by(Mosque.id)):
        students=active_students(db,u,m.id);sids=[s.id for s in students]
        rows=db.scalars(select(HalaqaProgress).where(HalaqaProgress.student_id.in_(sids),HalaqaProgress.day>=today()-timedelta(days=29))).all()
        attended=sum(p.attendance=='present' for p in rows);absent=sum(p.attendance=='absent' for p in rows)
        out.append({'id':m.id,'name':m.name,'students':len(students),'at_risk':sum(bool(risks(db,s)['reasons']) for s in students),
          'attendance':round(100*attended/(attended+absent),1) if attended+absent else None,
          'active_plans':len(db.scalars(select(SupportPlan).where(SupportPlan.student_id.in_(sids),SupportPlan.status=='active')).all())})
    return {'mosques':out}

def suggestions(db,sid):
    schedules={r.surah:r for r in db.scalars(select(ReviewSchedule).where(ReviewSchedule.student_id==sid))}
    mistakes=db.scalars(select(RecitationMistake).where(RecitationMistake.student_id==sid,RecitationMistake.resolved.is_(False))).all()
    records=db.scalars(select(QuranRecord).where(QuranRecord.student_id==sid,QuranRecord.status!='unstarted')).all()
    by_surah={r.surah:r for r in records};out=[]
    for n in set(by_surah)|set(schedules)|{m.surah for m in mistakes}:
        r=schedules.get(n);count=sum(m.surah==n for m in mistakes)
        due=r.due if r else today()
        if count and r and (not r.last_review or any(m.surah==n and m.day>=r.last_review for m in mistakes)):due=min(due,today())
        out.append({'surah':n,'name':SURAH_NAMES[n-1],'due':str(due),'last_review':str(r.last_review) if r and r.last_review else '',
          'mistakes':count,'support': 'strong' if any(m.surah==n and m.support=='strong' for m in mistakes) else 'light' if any(m.surah==n and m.support=='light' for m in mistakes) else 'review','reason':f'{count} مواضع خطأ تحتاج معالجة' if count else 'موعد المراجعة المتباعدة' if r else 'لم تسجل مراجعة معتمدة',
          'assignment_id':r.assignment_id if r else None,'interval':r.interval if r else 1})
    return sorted(out,key=lambda x:(x['due'],{'strong':0,'light':1,'review':2}[x['support']],-x['mistakes'],x['surah']))

@router.get('/mosques/{mid}/students/{sid}/advancement')
def student_advancement(mid:int,sid:int,request:Request,db=Depends(get_db)):
    u,s=access_student(db,request,mid,sid)
    parts={r.juz:r for r in db.scalars(select(JuzMastery).where(JuzMastery.student_id==sid))}
    plans=db.scalars(select(SupportPlan).where(SupportPlan.student_id==sid).order_by(SupportPlan.id.desc())).all()
    teachers=[]
    if u.role!=STUDENT_ROLE:
        for t in db.scalars(select(User).where(User.active.is_(True),User.mosque_id==mid,User.role.in_([TEACHER_ROLE,SUPERVISOR_ROLE,'owner']))):
            if s.halaqa_id in _ring_ids_for(t,mid,db):teachers.append({'id':t.id,'name':t.full_name})
    bookings=[]
    for b in db.scalars(select(ExamBooking).where(ExamBooking.student_id==sid)):
        e=db.get(OrganizedExam,b.exam_id)
        bookings.append({'exam_id':b.exam_id,'examiner_id':b.examiner_id,'examiner':db.get(User,b.examiner_id).full_name,'time':b.time_text,'next_level':b.next_level,'approved':b.approved,'title':e.title,'due':str(e.due)})
    return {'juz':[{'juz':n,'status':parts[n].status if n in parts else 'unstarted','notes':parts[n].notes if n in parts else ''} for n in range(1,31)],
      'suggestions':suggestions(db,sid),'risk':risks(db,s),
      'plans':[{'id':p.id,'title':p.title,'start':str(p.start),'end':str(p.end),'tasks':json.loads(p.tasks_json),'status':p.status,'outcome':p.outcome} for p in plans],
      'teachers':teachers,'bookings':bookings}

@router.put('/mosques/{mid}/students/{sid}/juz/{juz}')
def save_juz(mid:int,sid:int,juz:int,data:QuranInput,request:Request,db=Depends(get_db)):
    u,s=access_student(db,request,mid,sid,True)
    if not 1<=juz<=30:raise HTTPException(422,'رقم الجزء من 1 إلى 30')
    row=db.scalar(select(JuzMastery).where(JuzMastery.student_id==sid,JuzMastery.juz==juz))
    if not row:row=JuzMastery(student_id=sid,juz=juz,approved_by=u.id);db.add(row)
    row.status=data.status;row.notes=data.notes;row.approved_by=u.id
    audit(db,u.id,mid,'juz_mastery_saved',f'{sid}:{juz}');db.commit();return {'ok':True}

class ReviewInput(Input):
    due:date
    notes:str=Field('',max_length=1000)

@router.post('/mosques/{mid}/students/{sid}/review/{surah}/approve')
def approve_review(mid:int,sid:int,surah:int,data:ReviewInput,request:Request,db=Depends(get_db)):
    u,s=access_student(db,request,mid,sid,True)
    if surah not in {x['surah'] for x in suggestions(db,sid)}:raise HTTPException(422,'حدد سورة مسجلة في الخريطة أو الأخطاء')
    if not today()<=data.due<=today()+timedelta(days=365):raise HTTPException(422,'حدد موعدًا خلال السنة القادمة')
    row=db.scalar(select(ReviewSchedule).where(ReviewSchedule.student_id==sid,ReviewSchedule.surah==surah))
    if row and row.assignment_id:
        a=db.get(Assignment,row.assignment_id)
        if a and a.status=='pending':raise HTTPException(409,'يوجد ورد مراجعة معتمد لم تسجل نتيجته بعد')
    if not row:row=ReviewSchedule(student_id=sid,surah=surah,due=data.due);db.add(row)
    a=Assignment(student_id=sid,due=data.due,revision='مراجعة سورة '+SURAH_NAMES[surah-1],instructions=data.notes,created_by=u.id)
    db.add(a);db.flush();row.assignment_id=a.id;row.due=data.due
    audit(db,u.id,mid,'review_approved',f'{sid}:{surah}');db.commit();return {'ok':True}

class ReviewResult(Input):
    day:date
    score:int=Field(ge=0,le=10)

@router.post('/mosques/{mid}/students/{sid}/review/{surah}/result')
def review_result(mid:int,sid:int,surah:int,data:ReviewResult,request:Request,db=Depends(get_db)):
    u,s=access_student(db,request,mid,sid,True)
    row=db.scalar(select(ReviewSchedule).where(ReviewSchedule.student_id==sid,ReviewSchedule.surah==surah))
    a=db.get(Assignment,row.assignment_id) if row and row.assignment_id else None
    if not a or a.status!='pending':raise HTTPException(409,'اعتمد ورد المراجعة أولًا؛ النتيجة لا تكرر')
    if not a.due<=data.day<=today():raise HTTPException(422,'تاريخ التسميع خارج الموعد وحتى اليوم')
    row.interval=1 if data.score<6 else 3 if data.score<8 else min(60,max(7,row.interval*2))
    row.last_review=data.day;row.due=data.day+timedelta(days=row.interval)
    a.status='completed';a.result_note=f'تقييم المراجعة {data.score}/10؛ المراجعة التالية {row.due}'
    audit(db,u.id,mid,'spaced_review_assessed',f'{sid}:{surah}');db.commit();return {'ok':True}

class TaskInput(Input):
    text:str=Field(min_length=2,max_length=300)
    done:bool=False

class PlanInput(Input):
    title:str=Field(min_length=2,max_length=180)
    start:date
    end:date
    tasks:list[TaskInput]=Field(min_length=1,max_length=20)
    status:Literal['active','completed','cancelled']='active'
    outcome:str=Field('',max_length=1500)
    @model_validator(mode='after')
    def valid(self):
        if not 0<=(self.end-self.start).days<=366:raise ValueError('المدة من يوم إلى سنة')
        if self.status=='completed' and (not self.outcome.strip() or not all(t.done for t in self.tasks)):raise ValueError('أكمل المهام وسجل النتيجة قبل إغلاق الخطة')
        return self

@router.post('/mosques/{mid}/students/{sid}/support-plans')
def create_plan(mid:int,sid:int,data:PlanInput,request:Request,db=Depends(get_db)):
    u,s=access_student(db,request,mid,sid,True);d=data.model_dump();tasks=d.pop('tasks')
    row=SupportPlan(student_id=sid,created_by=u.id,tasks_json=json.dumps(tasks,ensure_ascii=False),**d);db.add(row)
    audit(db,u.id,mid,'support_plan_created',str(sid));db.commit();return {'ok':True}

@router.put('/mosques/{mid}/students/{sid}/support-plans/{pid}')
def update_plan(mid:int,sid:int,pid:int,data:PlanInput,request:Request,db=Depends(get_db)):
    u,s=access_student(db,request,mid,sid,True);row=db.get(SupportPlan,pid)
    if not row or row.student_id!=sid:raise HTTPException(404,'الخطة غير موجودة')
    d=data.model_dump();row.tasks_json=json.dumps(d.pop('tasks'),ensure_ascii=False)
    for k,v in d.items():setattr(row,k,v)
    audit(db,u.id,mid,'support_plan_updated',str(pid));db.commit();return {'ok':True}

class BookingInput(Input):
    examiner_id:int
    time:str=Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    next_level:str=Field('',max_length=120)

@router.put('/mosques/{mid}/students/{sid}/organized-exams/{eid}/booking')
def book(mid:int,sid:int,eid:int,data:BookingInput,request:Request,db=Depends(get_db)):
    u,s=access_student(db,request,mid,sid,True);_require(request,db,mid,{SUPERVISOR_ROLE})
    exam=db.get(OrganizedExam,eid);t=db.get(User,data.examiner_id)
    if not exam or exam.student_id!=sid or exam.status!='scheduled':raise HTTPException(409,'اختر اختبارًا قادمًا')
    if not t or not t.active or t.role not in (TEACHER_ROLE,SUPERVISOR_ROLE,'owner') or (t.role!='owner' and t.mosque_id!=mid) or s.halaqa_id not in _ring_ids_for(t,mid,db):raise HTTPException(422,'المختبر يجب أن يكون من فريق الحلقة المصرح له')
    for b in db.scalars(select(ExamBooking).join(OrganizedExam,OrganizedExam.id==ExamBooking.exam_id).where(ExamBooking.examiner_id==t.id,OrganizedExam.due==exam.due,OrganizedExam.status=='scheduled',ExamBooking.exam_id!=eid)):
        if b.time_text==data.time:raise HTTPException(409,'المختبر لديه اختبار في نفس الموعد')
    b=db.get(ExamBooking,eid)
    if not b:b=ExamBooking(exam_id=eid,student_id=sid);db.add(b)
    b.examiner_id=t.id;b.time_text=data.time;b.next_level=data.next_level;b.approved=False
    audit(db,u.id,mid,'exam_booked',str(eid));db.commit();return {'ok':True}

@router.post('/mosques/{mid}/students/{sid}/organized-exams/{eid}/promote')
def promote(mid:int,sid:int,eid:int,request:Request,db=Depends(get_db)):
    u,s=access_student(db,request,mid,sid,True);_require(request,db,mid,{SUPERVISOR_ROLE})
    b=db.get(ExamBooking,eid);r=db.get(OrganizedResult,eid)
    if not b or b.student_id!=sid or not r or not r.passed or not b.next_level:raise HTTPException(409,'يلزم اختبار مجتاز ومستوى تالي محدد')
    if b.approved:raise HTTPException(409,'اعتمد الانتقال سابقًا')
    s.level=b.next_level;b.approved=True;db.get(StudentExam,r.legacy_exam_id).next_level=b.next_level
    audit(db,u.id,mid,'exam_promotion_approved',f'{sid}:{eid}');db.commit();return {'ok':True}

def progress_digest(row):
    return hashlib.sha256(json.dumps(progress_pack(row) if row else None,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

@router.get('/mosques/{mid}/offline-snapshot')
def offline_snapshot(mid:int,request:Request,db=Depends(get_db)):
    u=_require(request,db,mid,{TEACHER_ROLE,SUPERVISOR_ROLE});out=[]
    for s in active_students(db,u,mid):
        p=db.scalar(select(HalaqaProgress).where(HalaqaProgress.student_id==s.id,HalaqaProgress.day==today()))
        out.append({'id':s.id,'name':s.full_name,'ring':db.get(Halaqa,s.halaqa_id).name,'base':progress_digest(p),'progress':progress_pack(p) if p else None})
    return {'user_id':u.id,'mid':mid,'day':str(today()),'expires':(datetime.utcnow()+timedelta(hours=24)).isoformat()+'Z','students':out}

class OfflineInput(Input):
    id:UUID
    user_id:int
    student_id:int
    base:str=Field(pattern='^[a-f0-9]{64}$')
    progress:ProgressInput

@router.post('/mosques/{mid}/offline-sync')
def offline_sync(mid:int,data:OfflineInput,request:Request,db=Depends(get_db)):
    u,s=access_student(db,request,mid,data.student_id,True)
    if u.id!=data.user_id:raise HTTPException(403,'سجل الدخول بالحساب الذي جهز الدفتر')
    digest=hashlib.sha256(data.model_dump_json().encode()).hexdigest();receipt=db.get(OfflineReceipt,str(data.id))
    if receipt:
        if receipt.user_id!=u.id or receipt.digest!=digest:raise HTTPException(409,'رقم عملية مستخدم لبيانات مختلفة')
        return {'ok':True,'already_synced':True}
    if not today()-timedelta(days=1)<=data.progress.day<=today():raise HTTPException(422,'دفتر دون اتصال يقبل اليوم والأمس فقط؛ راجع السجل يدويًا')
    row=db.scalar(select(HalaqaProgress).where(HalaqaProgress.student_id==s.id,HalaqaProgress.day==data.progress.day))
    if progress_digest(row)!=data.base:raise HTTPException(409,'تعارض: تغير سجل الطالب على الموقع. راجعه قبل إعادة الإدخال؛ لم نكتب فوقه')
    db.add(OfflineReceipt(id=str(data.id),user_id=u.id,student_id=s.id,digest=digest))
    # Existing writer performs all validation and commits receipt and progress atomically.
    return add_progress(mid,s.id,data.progress,request,db)
