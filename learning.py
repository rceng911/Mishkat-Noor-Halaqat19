"""Learning workflows; all reads/writes enforce current student and circle scope."""
from datetime import date,timedelta,datetime
from collections import Counter
import math
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import Field,model_validator
from sqlalchemy import select,delete
from app.db.session import get_db
from app.models import *
from app.api.halaqat import Input,_require,_ring_ids_for,STUDENT_ROLE,TEACHER_ROLE,SUPERVISOR_ROLE
from app.api.student_file import access_student,today
from app.api.development import ring_access,STAFF
from app.api.routes import audit,audit_change
from app.services.quran_catalog import SURAH_NAMES,AYAH_COUNTS
router=APIRouter(prefix='/api/halaqat/mosques/{mid}')
MANAGERS={'owner',SUPERVISOR_ROLE}
KINDS={'memory':'نسيان','similar':'متشابهات','tajweed':'تجويد','pronunciation':'نطق'}

def goal_pack(g):
    if not g:return None
    remaining=max(0,g.target-g.completed);days=max(0,(g.deadline-max(today(),g.start)).days+1)
    weekly=(math.ceil(remaining*7/days) if g.unit=='ayah' else math.ceil(remaining*7/days*100)/100) if days and remaining else 0
    return {'title':g.title,'unit':g.unit,'target':g.target,'completed':g.completed,'start':str(g.start),'deadline':str(g.deadline),'notes':g.notes,'remaining':remaining,'weekly':min(remaining,weekly),'overdue':remaining>0 and days==0,'percent':round(g.completed/g.target*100,1)}

class GoalInput(Input):
    title:str=Field(min_length=2,max_length=180)
    unit:Literal['page','ayah']='page'
    target:float=Field(gt=0,le=100000,allow_inf_nan=False)
    completed:float=Field(0,ge=0,le=100000,allow_inf_nan=False)
    start:date
    deadline:date
    notes:str=Field('',max_length=1000)
    @model_validator(mode='after')
    def validate(self):
        if self.deadline<self.start or (self.deadline-self.start).days>3650 or self.completed>self.target:raise ValueError('راجع الفترة والهدف والمنجز')
        if self.unit=='ayah' and (not self.target.is_integer() or not self.completed.is_integer()):raise ValueError('الآيات أعداد صحيحة')
        return self

@router.put('/students/{sid}/completion-goal')
def save_goal(mid:int,sid:int,data:GoalInput,request:Request,db=Depends(get_db)):
    u,s=access_student(db,request,mid,sid,True);g=db.get(CompletionGoal,sid);before=goal_pack(g)
    if not g:g=CompletionGoal(student_id=sid,updated_by=u.id);db.add(g)
    for k,v in data.model_dump().items():setattr(g,k,v)
    g.updated_by=u.id;audit_change(db,u.id,mid,'completion_goal_updated',sid,before,data.model_dump(mode='json'));db.commit();return {'ok':True}

class MistakeInput(Input):
    day:date
    surah:int=Field(ge=1,le=114)
    ayah:int=Field(ge=1,le=286)
    kind:Literal['memory','similar','tajweed','pronunciation']
    support:Literal['strong','light','review']='review'
    notes:str=Field('',max_length=1000)
    resolved:bool=False
    @model_validator(mode='after')
    def verse(self):
        if self.ayah>AYAH_COUNTS[self.surah-1]:raise ValueError('رقم الآية أكبر من عدد آيات السورة')
        return self

@router.post('/students/{sid}/mistakes')
def add_mistake(mid:int,sid:int,data:MistakeInput,request:Request,db=Depends(get_db)):
    u,s=access_student(db,request,mid,sid,True)
    if data.day>today():raise HTTPException(422,'لا تسجل خطأ في يوم مستقبلي')
    row=RecitationMistake(student_id=sid,recorded_by=u.id,**data.model_dump());db.add(row);db.flush();audit(db,u.id,mid,'mistake_recorded',str(row.id));db.commit();return {'id':row.id}

@router.put('/students/{sid}/mistakes/{eid}')
def edit_mistake(mid:int,sid:int,eid:int,data:MistakeInput,request:Request,db=Depends(get_db)):
    u,s=access_student(db,request,mid,sid,True);row=db.get(RecitationMistake,eid)
    if not row or row.student_id!=sid:raise HTTPException(404,'السجل غير موجود')
    if data.day>today():raise HTTPException(422,'التاريخ مستقبلي')
    before={k:str(getattr(row,k)) for k in data.model_fields}
    for k,v in data.model_dump().items():setattr(row,k,v)
    audit_change(db,u.id,mid,'mistake_edited',eid,before,data.model_dump(mode='json'));db.commit();return {'ok':True}

class PracticeInput(Input):
    assignment_id:int=Field(gt=0)
    day:date
    minutes:int=Field(ge=1,le=600)
    notes:str=Field('',max_length=1000)

@router.post('/students/{sid}/home-practice')
def practice(mid:int,sid:int,data:PracticeInput,request:Request,db=Depends(get_db)):
    u,s=access_student(db,request,mid,sid)
    if u.role!=STUDENT_ROLE or u.account_type!='guardian' or s.recipient_type!='guardian' or not s.active:raise HTTPException(403,'تأكيد المراجعة المنزلية لولي الأمر المرتبط بالطالب فقط')
    a=db.get(Assignment,data.assignment_id)
    if not a or a.student_id!=sid:raise HTTPException(404,'الورد غير موجود')
    if data.day>today() or data.day<a.created_at.date():raise HTTPException(422,'اختر يومًا من إنشاء الورد حتى اليوم')
    row=db.scalar(select(HomePractice).where(HomePractice.assignment_id==a.id,HomePractice.day==data.day))
    if not row:row=HomePractice(student_id=sid,guardian_id=u.id,**data.model_dump());db.add(row)
    elif row.guardian_id!=u.id:raise HTTPException(409,'سجل هذا اليوم محفوظ لولي أمر سابق')
    else:row.minutes=data.minutes;row.notes=data.notes;row.updated_at=datetime.utcnow()
    audit(db,u.id,mid,'home_practice_confirmed',f'{sid}:{a.id}:{data.day}');db.commit();return {'ok':True}

@router.get('/students/{sid}/learning')
def student_learning(mid:int,sid:int,request:Request,db=Depends(get_db)):
    u,s=access_student(db,request,mid,sid)
    mistakes=db.scalars(select(RecitationMistake).where(RecitationMistake.student_id==sid).order_by(RecitationMistake.day.desc(),RecitationMistake.id.desc())).all()
    counts=Counter((m.surah,m.ayah,m.kind) for m in mistakes)
    home=db.scalars(select(HomePractice).where(HomePractice.student_id==sid).order_by(HomePractice.day.desc())).all()
    return {'goal':goal_pack(db.get(CompletionGoal,sid)),'kinds':KINDS,'surahs':SURAH_NAMES,'ayah_counts':AYAH_COUNTS,'mistakes':[{'id':m.id,'day':str(m.day),'surah':m.surah,'surah_name':SURAH_NAMES[m.surah-1],'ayah':m.ayah,'kind':m.kind,'support':m.support,'notes':m.notes,'resolved':m.resolved,'repetitions':counts[m.surah,m.ayah,m.kind]} for m in mistakes],'home':[{'id':h.id,'day':str(h.day),'assignment_id':h.assignment_id,'minutes':h.minutes,'notes':h.notes,'guardian':db.get(User,h.guardian_id).full_name} for h in home],'can_practice':u.role==STUDENT_ROLE and u.account_type=='guardian' and s.recipient_type=='guardian' and s.active}

class QueueInput(Input):
    day:date
    student_ids:list[int]=Field(min_length=1,max_length=300)
    reset:bool=False

@router.put('/rings/{rid}/queue')
def queue_set(mid:int,rid:int,data:QueueInput,request:Request,db=Depends(get_db)):
    u=ring_access(db,request,mid,rid)
    if len(set(data.student_ids))!=len(data.student_ids):raise HTTPException(422,'طالب مكرر')
    for sid in data.student_ids:
        _,s=access_student(db,request,mid,sid,True)
        if s.halaqa_id!=rid:raise HTTPException(422,'الطالب ليس في الحلقة')
    if db.scalar(select(RecitationTurn.id).where(RecitationTurn.halaqa_id==rid,RecitationTurn.day==data.day)) and not data.reset:raise HTTPException(409,'يوجد دور لهذا اليوم؛ يلزم تأكيد إعادة الترتيب')
    db.execute(delete(RecitationTurn).where(RecitationTurn.halaqa_id==rid,RecitationTurn.day==data.day))
    for i,sid in enumerate(data.student_ids):db.add(RecitationTurn(halaqa_id=rid,student_id=sid,day=data.day,position=i+1,status='called' if i==0 else 'waiting'))
    audit(db,u.id,mid,'queue_set',f'{rid}:{data.day}');db.commit();return {'ok':True}

class NextTurn(Input):
    day:date
    current_id:int=Field(gt=0)

@router.post('/rings/{rid}/queue/next')
def queue_next(mid:int,rid:int,data:NextTurn,request:Request,db=Depends(get_db)):
    u=ring_access(db,request,mid,rid)
    rows=db.scalars(select(RecitationTurn).where(RecitationTurn.halaqa_id==rid,RecitationTurn.day==data.day).order_by(RecitationTurn.position)).all()
    current=next((r for r in rows if r.status=='called'),None)
    if not current or current.id!=data.current_id:raise HTTPException(409,'تغير الدور؛ حدّث القائمة')
    current.status='done'
    for r in rows:
        if r.status=='waiting':
            s=db.get(HalaqaStudent,r.student_id)
            if not s.active or s.halaqa_id!=rid:r.status='skipped';continue
            r.status='called';break
    audit(db,u.id,mid,'queue_advanced',str(current.id));db.commit();return {'ok':True}

@router.get('/rings/{rid}/queue')
def queue_get(mid:int,rid:int,day:date,request:Request,db=Depends(get_db)):
    u=ring_access(db,request,mid,rid,STAFF|{STUDENT_ROLE})
    rows=db.scalars(select(RecitationTurn).where(RecitationTurn.halaqa_id==rid,RecitationTurn.day==day).order_by(RecitationTurn.position)).all()
    visible=[];current=next((x for x in rows if x.status=='called'),None)
    for x in rows:
        s=db.get(HalaqaStudent,x.student_id)
        if s.halaqa_id!=rid or not s.active:continue
        if u.role==STUDENT_ROLE and s.user_id!=u.id:continue
        visible.append({'id':x.id,'student_id':s.id,'name':s.full_name,'position':x.position,'status':x.status})
    return {'rows':visible,'current_position':current.position if current else None,'current_id':current.id if current and u.role!=STUDENT_ROLE else None,'total':len(rows),'day':str(day)}

class SubstituteInput(Input):
    user_id:int=Field(gt=0)
    start:date
    end:date
    @model_validator(mode='after')
    def dates(self):
        if self.end<self.start or (self.end-self.start).days>366:raise ValueError('مدة التكليف من يوم إلى سنة')
        return self

@router.post('/rings/{rid}/substitutes')
def assign_substitute(mid:int,rid:int,data:SubstituteInput,request:Request,db=Depends(get_db)):
    u=ring_access(db,request,mid,rid,MANAGERS);teacher=db.get(User,data.user_id)
    if not teacher or teacher.role!=TEACHER_ROLE or teacher.mosque_id!=mid or not teacher.active:raise HTTPException(422,'اختر مدرسًا فعالًا من المسجد نفسه')
    if data.end<today():raise HTTPException(422,'التكليف منتهٍ')
    if db.scalar(select(SubstituteTeacher.id).where(SubstituteTeacher.halaqa_id==rid,SubstituteTeacher.user_id==data.user_id,SubstituteTeacher.active.is_(True),SubstituteTeacher.start<=data.end,SubstituteTeacher.end>=data.start)):raise HTTPException(409,'يوجد تكليف متداخل لهذا المدرس')
    row=SubstituteTeacher(halaqa_id=rid,assigned_by=u.id,**data.model_dump());db.add(row);db.flush();audit(db,u.id,mid,'substitute_assigned',str(row.id));db.commit();return {'ok':True}

@router.delete('/rings/{rid}/substitutes/{tid}')
def revoke_substitute(mid:int,rid:int,tid:int,request:Request,db=Depends(get_db)):
    u=ring_access(db,request,mid,rid,MANAGERS);row=db.get(SubstituteTeacher,tid)
    if not row or row.halaqa_id!=rid:raise HTTPException(404,'التكليف غير موجود')
    row.active=False;audit(db,u.id,mid,'substitute_revoked',str(tid));db.commit();return {'ok':True}

@router.get('/learning-dashboard')
def learning_dashboard(mid:int,request:Request,db=Depends(get_db)):
    u=_require(request,db,mid,STAFF|{STUDENT_ROLE});rids=_ring_ids_for(u,mid,db);manager=u.role in MANAGERS
    students=db.scalars(select(HalaqaStudent).where(HalaqaStudent.halaqa_id.in_(rids),HalaqaStudent.active.is_(True))).all() if manager else []
    missing=[]
    for s in students:
        fields=[];account=db.get(User,s.user_id) if s.user_id else None
        if not account or not (account.username or '').strip():fields.append('لم يُصدر حساب باسم مستخدم')
        if fields:missing.append({'student_id':s.id,'name':s.full_name,'ring':db.get(Halaqa,s.halaqa_id).name,'fields':fields})
    teachers=db.scalars(select(User).where(User.mosque_id==mid,User.role==TEACHER_ROLE,User.active.is_(True))).all() if manager else []
    subs=db.scalars(select(SubstituteTeacher).where(SubstituteTeacher.halaqa_id.in_(rids),SubstituteTeacher.active.is_(True))).all() if manager else []
    return {'missing':missing,'teachers':[{'id':t.id,'name':t.full_name} for t in teachers],'substitutes':[{'id':s.id,'halaqa_id':s.halaqa_id,'ring':db.get(Halaqa,s.halaqa_id).name,'name':db.get(User,s.user_id).full_name,'start':str(s.start),'end':str(s.end),'expired':s.end<today()} for s in subs]}

@router.get('/students/{sid}/term-report')
def term_report(mid:int,sid:int,start:date,end:date,request:Request,db=Depends(get_db)):
    u,s=access_student(db,request,mid,sid)
    if start<date(1900,1,1) or end<start or end>today() or (end-start).days>365:raise HTTPException(422,'اختر فترة سابقة لا تتجاوز سنة')
    span=(end-start).days+1;previous_start=start-timedelta(days=span);previous_end=start-timedelta(days=1)
    rows=db.scalars(select(HalaqaProgress).where(HalaqaProgress.student_id==sid,HalaqaProgress.day>=previous_start,HalaqaProgress.day<=end)).all()
    def summarize(a,b):
        period=[x for x in rows if a<=x.day<=b];present=[x for x in period if x.attendance=='present'];absent=sum(x.attendance=='absent' for x in period)
        def avg(field):
            nums=[getattr(x,field) for x in present if getattr(x,field) is not None];return round(sum(nums)/len(nums),2) if nums else None
        return {'from':str(a),'to':str(b),'recorded_days':len(period),'present':len(present),'absent':absent,'excused':sum(x.attendance=='excused' for x in period),'attendance_percent':round(len(present)/(len(present)+absent)*100,1) if len(present)+absent else None,'memorized_pages':sum(x.memorized_amount for x in present if x.memorized_unit=='page'),'memorized_ayahs':sum(x.memorized_amount for x in present if x.memorized_unit=='ayah'),'revision_pages':sum(x.revision_amount for x in present if x.revision_unit=='page'),'revision_ayahs':sum(x.revision_amount for x in present if x.revision_unit=='ayah'),'memorization_score':avg('memorization_score'),'tajweed_score':avg('tajweed_score')}
    return {'student':s.full_name,'current':summarize(start,end),'previous':summarize(previous_start,previous_end)}

class CompetitionInput(Input):
    halaqa_id:int=Field(gt=0)
    title:str=Field(min_length=2,max_length=180)
    mode:Literal['individual','team']
    unit:str=Field(min_length=1,max_length=60)
    target:float=Field(gt=0,le=100000,allow_inf_nan=False)
    start:date
    end:date
    reward:str=Field('',max_length=500)
    student_ids:list[int]=Field(min_length=1,max_length=300)
    @model_validator(mode='after')
    def dates(self):
        if self.end<self.start or (self.end-self.start).days>366:raise ValueError('راجع فترة المسابقة')
        return self

@router.post('/competitions')
def competition_create(mid:int,data:CompetitionInput,request:Request,db=Depends(get_db)):
    u=ring_access(db,request,mid,data.halaqa_id,MANAGERS)
    if data.end<today():raise HTTPException(422,'اختر فترة لم تنتهِ')
    if len(set(data.student_ids))!=len(data.student_ids):raise HTTPException(422,'طالب مكرر')
    for sid in data.student_ids:
        _,s=access_student(db,request,mid,sid,True)
        if s.halaqa_id!=data.halaqa_id:raise HTTPException(422,'المشارك ليس من الحلقة')
    c=Competition(created_by=u.id,**data.model_dump(exclude={'student_ids'}));db.add(c);db.flush()
    for sid in data.student_ids:db.add(CompetitionEntry(competition_id=c.id,student_id=sid))
    audit(db,u.id,mid,'competition_created',str(c.id));db.commit();return {'id':c.id}

def competition_access(db,request,mid,cid,roles=STAFF):
    c=db.get(Competition,cid)
    if not c:raise HTTPException(404,'المسابقة غير موجودة')
    u=ring_access(db,request,mid,c.halaqa_id,roles)
    return u,c

class CompetitionScore(Input):
    value:float=Field(ge=0,le=100000,allow_inf_nan=False)
    notes:str=Field('',max_length=1000)

@router.put('/competitions/{cid}/entries/{eid}')
def score_competition(mid:int,cid:int,eid:int,data:CompetitionScore,request:Request,db=Depends(get_db)):
    u,c=competition_access(db,request,mid,cid);e=db.get(CompetitionEntry,eid)
    if not e or e.competition_id!=cid:raise HTTPException(404,'المشارك غير موجود')
    access_student(db,request,mid,e.student_id,True)
    if not c.active or today()<c.start:raise HTTPException(409,'المسابقة لم تبدأ أو مغلقة')
    if db.scalar(select(CompetitionEntry.id).where(CompetitionEntry.competition_id==cid,CompetitionEntry.awarded.is_(True))):raise HTTPException(409,'اسحب اعتماد التكريم أولًا قبل تعديل النتائج')
    before={'value':e.value,'status':e.status};e.value=data.value;e.notes=data.notes;e.status='pending';e.reviewed_by=None
    audit_change(db,u.id,mid,'competition_score_submitted',eid,before,data.model_dump());db.commit();return {'ok':True}

class CompetitionReview(Input):
    status:Literal['approved','rejected']

@router.put('/competitions/{cid}/entries/{eid}/review')
def review_competition(mid:int,cid:int,eid:int,data:CompetitionReview,request:Request,db=Depends(get_db)):
    u,c=competition_access(db,request,mid,cid,MANAGERS);e=db.get(CompetitionEntry,eid)
    if not e or e.competition_id!=cid:raise HTTPException(404,'المشارك غير موجود')
    if not c.active or e.status!='pending':raise HTTPException(409,'تراجع النتائج المعلقة للمسابقة المفتوحة فقط')
    if db.scalar(select(CompetitionEntry.id).where(CompetitionEntry.competition_id==cid,CompetitionEntry.awarded.is_(True))):raise HTTPException(409,'اسحب التكريم قبل تغيير النتائج')
    e.status=data.status;e.reviewed_by=u.id;audit(db,u.id,mid,'competition_score_reviewed',f'{eid}:{data.status}');db.commit();return {'ok':True}

class AwardInput(Input):
    awarded:bool

@router.put('/competitions/{cid}/award')
def award_competition(mid:int,cid:int,data:AwardInput,request:Request,db=Depends(get_db)):
    u,c=competition_access(db,request,mid,cid,MANAGERS);entries=db.scalars(select(CompetitionEntry).where(CompetitionEntry.competition_id==cid)).all()
    if data.awarded:
        if not c.active or today()<c.end:raise HTTPException(409,'التكريم بعد انتهاء الفترة وفي مسابقة مفتوحة')
        if any(e.status in ('pending','empty') for e in entries):raise HTTPException(409,'سجل وراجع نتائج جميع المشاركين أولًا')
    total=sum(e.value for e in entries if e.status=='approved')
    for e in entries:e.awarded=data.awarded and e.status=='approved' and (total>=c.target if c.mode=='team' else e.value>=c.target)
    audit(db,u.id,mid,'competition_awards_changed',f'{cid}:{data.awarded}');db.commit();return {'ok':True}

@router.put('/competitions/{cid}/active')
def close_competition(mid:int,cid:int,data:AwardInput,request:Request,db=Depends(get_db)):
    u,c=competition_access(db,request,mid,cid,MANAGERS);c.active=data.awarded
    audit(db,u.id,mid,'competition_active_changed',f'{cid}:{c.active}');db.commit();return {'ok':True}

@router.get('/competitions')
def competitions(mid:int,request:Request,db=Depends(get_db)):
    u=_require(request,db,mid,STAFF|{STUDENT_ROLE});ids=_ring_ids_for(u,mid,db);result=[]
    for c in db.scalars(select(Competition).where(Competition.halaqa_id.in_(ids)).order_by(Competition.id.desc())):
        entries=db.scalars(select(CompetitionEntry).where(CompetitionEntry.competition_id==c.id)).all();visible=[]
        total=sum(e.value for e in entries if e.status=='approved')
        for e in entries:
            s=db.get(HalaqaStudent,e.student_id)
            if u.role==STUDENT_ROLE and s.user_id!=u.id:continue
            # Teachers must not see a transferred student's new private profile.
            if u.role==TEACHER_ROLE and s.halaqa_id not in ids:continue
            visible.append({'id':e.id,'student_id':s.id,'name':s.full_name,'value':e.value,'notes':e.notes,'status':e.status,'awarded':e.awarded})
        if u.role==STUDENT_ROLE and not visible:continue
        result.append({'id':c.id,'halaqa_id':c.halaqa_id,'ring':db.get(Halaqa,c.halaqa_id).name,'title':c.title,'mode':c.mode,'unit':c.unit,'target':c.target,'start':str(c.start),'end':str(c.end),'reward':c.reward,'active':c.active,'team_total':total,'entries':visible})
    return {'competitions':result}
