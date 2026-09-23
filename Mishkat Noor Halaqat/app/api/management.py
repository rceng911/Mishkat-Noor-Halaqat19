"""Owner controlled circle management and reviewed bulk enrollment."""
import hashlib,json
from pathlib import Path
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import select,delete,update,func,or_
from app.db.session import get_db
from app.models import *
from app.api.halaqat import Input,_require,_ring_pack,_unique_email,TEACHER_ROLE
from app.api.development import normalized_name
from app.api.routes import audit,audit_change

router=APIRouter(prefix='/api/halaqat/mosques/{mid}')

def owner_ring(db,request,mid,rid):
    u=_require(request,db,mid,{'owner'});r=db.get(Halaqa,rid)
    if not r or r.mosque_id!=mid:raise HTTPException(404,'الحلقة غير موجودة')
    return u,r

class EditRing(Input):
    name:str=Field(min_length=2,max_length=180)
    schedule:str=Field('',max_length=500)
    supervisor_ids:list[int]=Field(default_factory=list,max_length=100)
    teacher_ids:list[int]=Field(default_factory=list,max_length=100)

@router.put('/rings/{rid}')
def edit_ring(mid:int,rid:int,data:EditRing,request:Request,db=Depends(get_db)):
    u,r=owner_ring(db,request,mid,rid)
    if db.scalar(select(Halaqa.id).where(Halaqa.mosque_id==mid,Halaqa.name==data.name,Halaqa.id!=rid)):raise HTTPException(409,'اسم الحلقة موجود')
    for ids,role in [(data.supervisor_ids,'halaqa_supervisor'),(data.teacher_ids,TEACHER_ROLE)]:
        if len(ids)!=len(set(ids)):raise HTTPException(422,'حساب مكرر')
        for uid in ids:
            target=db.get(User,uid)
            if not target or not target.active or target.mosque_id!=mid or target.role!=role:raise HTTPException(422,'حساب خارج المسجد أو غير صالح')
    before=_ring_pack(r,db)
    for model,ids in [(HalaqaTeacher,data.teacher_ids),(HalaqaSupervisor,data.supervisor_ids)]:
        links=db.scalars(select(model).where(model.halaqa_id==rid)).all()
        for link in links:link.active=link.user_id in ids
        known={x.user_id for x in links}
        for uid in ids:
            if uid not in known:db.add(model(halaqa_id=rid,user_id=uid,assigned_by=u.id,active=True))
    r.name=data.name;r.schedule=data.schedule;r.supervisor_id=data.supervisor_ids[0] if data.supervisor_ids else None
    audit_change(db,u.id,mid,'ring_edited',rid,before,data.model_dump());db.commit()
    return {'ok':True}

class TeacherEdit(Input):
    phone:str=Field("",max_length=40)
    notes:str=Field("",max_length=1000)
    full_name:str=Field(min_length=2,max_length=180)
    email:str=Field('',max_length=200)

@router.get('/teachers/manage')
def teacher_list(mid:int,request:Request,db=Depends(get_db)):
    _require(request,db,mid,{'owner'})
    return {'teachers':[{'id':u.id,'full_name':u.full_name,'email':'' if u.email.endswith('@accounts.invalid') else u.email,'active':u.active,'phone':u.phone or '', 'notes':u.staff_notes or ''} for u in db.scalars(select(User).where(User.mosque_id==mid,User.role==TEACHER_ROLE))]}

@router.put('/teachers/{uid}/profile')
def teacher_edit(mid:int,uid:int,data:TeacherEdit,request:Request,db=Depends(get_db)):
    u=_require(request,db,mid,{'owner'});t=db.get(User,uid)
    if not t or t.mosque_id!=mid or t.role!=TEACHER_ROLE:raise HTTPException(404,'المدرس غير موجود')
    email=data.email.lower()
    if email and ('@' not in email or ' ' in email):raise HTTPException(422,'البريد غير صالح')
    if email and db.scalar(select(User.id).where(User.email==email,User.id!=uid)):raise HTTPException(409,'البريد مستخدم')
    before={'full_name':t.full_name,'email':t.email}
    t.full_name=data.full_name;t.phone=data.phone;t.staff_notes=data.notes;t.email=email or (t.email if t.email.endswith('@accounts.invalid') else _unique_email(db,'','teacher',uid))
    audit_change(db,u.id,mid,'teacher_profile_edited',uid,before,{'full_name':t.full_name,'email':t.email});db.commit();return {'ok':True}

@router.put('/teacher-requests/{qid}')
def teacher_request_edit(mid:int,qid:int,data:TeacherEdit,request:Request,db=Depends(get_db)):
    u=_require(request,db,mid,{'owner'});r=db.get(HalaqaAccountRequest,qid)
    if not r or r.mosque_id!=mid or r.request_type!='teacher':raise HTTPException(404,'طلب المدرس غير موجود')
    if r.status!='pending':raise HTTPException(409,'تمت معالجة الطلب؛ عدل حساب المدرس')
    before={'full_name':r.full_name,'email':r.email};r.full_name=data.full_name;r.email=data.email
    audit_change(db,u.id,mid,'teacher_request_edited',qid,before,data.model_dump());db.commit();return {'ok':True}

def deletion_plan(db,rid):
    students=list(db.scalars(select(HalaqaStudent.id).where(HalaqaStudent.halaqa_id==rid)))
    # Include every dependent student/ring table, even if a later feature adds one.
    from app.db.session import Base
    counts={}
    for table in Base.metadata.sorted_tables:
        key='student_id' if 'student_id' in table.c and any(f.target_fullname=='halaqa_students.id' for f in table.c.student_id.foreign_keys) else None
        if key: counts[table.name]=db.scalar(select(func.count()).select_from(table).where(table.c[key].in_(students)))
    counts['students']=len(students)
    counts['requests']=db.scalar(select(func.count(HalaqaAccountRequest.id)).where(HalaqaAccountRequest.halaqa_id==rid))
    # Snapshot of rows catches changes to the affected data between preview and deletion.
    snapshot={}
    for table in Base.metadata.sorted_tables:
        if table.name=='competition_entries':cond=or_(table.c.student_id.in_(students),table.c.competition_id.in_(select(Competition.id).where(Competition.halaqa_id==rid)))
        elif 'student_id' in table.c and any(f.target_fullname=='halaqa_students.id' for f in table.c.student_id.foreign_keys):cond=or_(table.c.student_id.in_(students),table.c.halaqa_id==rid) if 'halaqa_id' in table.c else table.c.student_id.in_(students)
        elif 'halaqa_id' in table.c:cond=table.c.halaqa_id==rid
        elif table.name=='halaqat':cond=table.c.id==rid
        elif table.name=='halaqa_students':cond=table.c.id.in_(students)
        elif table.name=='organized_exam_results':cond=table.c.exam_id.in_(select(OrganizedExam.id).where(OrganizedExam.student_id.in_(students)))
        else:continue
        snapshot[table.name]=[dict(row) for row in db.execute(select(table).where(cond).order_by(*table.primary_key.columns)).mappings()]
    token=hashlib.sha256(json.dumps(snapshot,sort_keys=True,default=str).encode()).hexdigest()
    return students,counts,token

@router.get('/rings/{rid}/deletion-preview')
def preview_delete(mid:int,rid:int,request:Request,db=Depends(get_db)):
    _,r=owner_ring(db,request,mid,rid);_,counts,token=deletion_plan(db,rid)
    return {'name':r.name,'counts':counts,'token':token}

class DeleteRing(Input):
    confirm_name:str
    token:str=Field(min_length=64,max_length=64)

@router.delete('/rings/{rid}')
def delete_ring(mid:int,rid:int,data:DeleteRing,request:Request,db=Depends(get_db)):
    u,r=owner_ring(db,request,mid,rid);students,counts,token=deletion_plan(db,rid)
    if data.confirm_name!=r.name:raise HTTPException(422,'اكتب اسم الحلقة كاملًا لتأكيد الحذف')
    if token!=data.token:raise HTTPException(409,'تغيرت بيانات الحلقة؛ افتح معاينة الحذف مجددًا')
    exams=list(db.scalars(select(OrganizedExam.id).where(OrganizedExam.student_id.in_(students))))
    db.execute(delete(OrganizedResult).where(OrganizedResult.exam_id.in_(exams)))
    db.execute(update(OrganizedExam).where(OrganizedExam.next_exam_id.in_(exams)).values(next_exam_id=None))
    db.execute(delete(OrganizedExam).where(OrganizedExam.id.in_(exams)))
    from app.db.session import Base
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in {'organized_exams','organized_exam_results','halaqa_students','halaqat'}:continue
        if 'student_id' in table.c and any(f.target_fullname=='halaqa_students.id' for f in table.c.student_id.foreign_keys):
            cond=table.c.student_id.in_(students)
            if 'halaqa_id' in table.c:cond=or_(cond,table.c.halaqa_id==rid)
            if table.name=='competition_entries':cond=or_(cond,table.c.competition_id.in_(select(Competition.id).where(Competition.halaqa_id==rid)))
            db.execute(delete(table).where(cond))
        elif 'halaqa_id' in table.c and any(f.target_fullname=='halaqat.id' for f in table.c.halaqa_id.foreign_keys):
            db.execute(delete(table).where(table.c.halaqa_id==rid))
    db.execute(delete(HalaqaStudent).where(HalaqaStudent.id.in_(students)))
    audit(db,u.id,mid,'ring_deleted',json.dumps({'id':rid,'name':r.name,'counts':counts},ensure_ascii=False));db.delete(r);db.commit()
    return {'ok':True,'counts':counts}

class RosterGroup(Input):
    name:str=Field(min_length=2,max_length=180)
    teacher_name:str=Field(min_length=2,max_length=180)
    students:list[str]=Field(min_length=1,max_length=100)

class RosterInput(Input):
    reviewed:Literal[True]
    groups:list[RosterGroup]=Field(min_length=1,max_length=10)

@router.post('/roster/import')
def import_roster(mid:int,data:RosterInput,request:Request,db=Depends(get_db)):
    u=_require(request,db,mid,{'owner'})
    ringnames={normalized_name(n) for n in db.scalars(select(Halaqa.name).where(Halaqa.mosque_id==mid))}
    names={normalized_name(n) for n in db.scalars(select(HalaqaStudent.full_name).join(Halaqa).where(Halaqa.mosque_id==mid))}
    names.update(normalized_name(n) for n in db.scalars(select(HalaqaAccountRequest.full_name).where(HalaqaAccountRequest.mosque_id==mid,HalaqaAccountRequest.request_type=='student',HalaqaAccountRequest.status.in_(['pending','returned']))))
    # Validate the complete batch before writing anything; no assumed guardian or password.
    for g in data.groups:
        if '?' in g.teacher_name or '؟' in g.teacher_name:raise HTTPException(422,'أكمل اسم المدرس')
        rn=normalized_name(g.name)
        if rn in ringnames:raise HTTPException(409,'اسم حلقة مكرر؛ لم تتم إضافة أي بيانات')
        ringnames.add(rn)
        for name in g.students:
            clean=name.strip();n=normalized_name(clean)
            if len(clean)<2 or len(clean)>180 or '?' in clean or '؟' in clean:raise HTTPException(422,'راجع أسماء الطلاب')
            if n in names:raise HTTPException(409,'اسم طالب مكرر؛ راجع القائمة قبل الإضافة')
            names.add(n)
    total=0
    for g in data.groups:
        r=Halaqa(mosque_id=mid,name=g.name,active=True);db.add(r);db.flush()
        db.add(HalaqaAccountRequest(mosque_id=mid,request_type='teacher',requested_by=u.id,halaqa_id=r.id,full_name=g.teacher_name,status='pending',notes='من قائمة الحلقات؛ بانتظار إصدار الحساب من المالك'))
        for name in g.students:
            db.add(HalaqaStudent(halaqa_id=r.id,full_name=name.strip(),user_id=None,recipient_type='student',national_id='',birth_date=None,active=True,notes='مستورد من قائمة الحلقات. يحدد المالك حساب متابع التقارير قبل إصدار الدخول.'));total+=1
    audit(db,u.id,mid,'roster_imported',json.dumps({'rings':len(data.groups),'students':total}));db.commit()
    return {'ok':True,'rings':len(data.groups),'students':total}

@router.get('/roster/source')
def roster_source(mid:int,request:Request,db=Depends(get_db)):
    _require(request,db,mid,{'owner'})
    return FileResponse(Path(__file__).resolve().parents[1]/'assets'/'roster-source.png',headers={'Cache-Control':'no-store'})


class SupervisorEdit(TeacherEdit):
    username: str = Field(min_length=3,max_length=30)

@router.get('/supervisors/manage')
def supervisor_list(mid:int,request:Request,db=Depends(get_db)):
    _require(request,db,mid,{'owner'})
    return {'supervisors':[{'id':u.id,'full_name':u.full_name,'username':u.username,'email':'' if u.email.endswith('@accounts.invalid') else u.email,'phone':u.phone or '', 'notes':u.staff_notes or '', 'active':u.active} for u in db.scalars(select(User).where(User.mosque_id==mid,User.role=='halaqa_supervisor'))]}

@router.put('/supervisors/{uid}/profile')
def edit_supervisor(mid:int,uid:int,data:SupervisorEdit,request:Request,db=Depends(get_db)):
    from app.api.halaqat import _clean_username
    u=_require(request,db,mid,{'owner'});target=db.get(User,uid)
    if not target or target.mosque_id!=mid or target.role!='halaqa_supervisor':raise HTTPException(404,'المشرف غير موجود')
    username=_clean_username(data.username,required=True)
    if db.scalar(select(User.id).where(User.username==username,User.id!=uid)):raise HTTPException(409,'اسم المستخدم مستخدم')
    email=data.email.lower()
    if email and ('@' not in email or ' ' in email):raise HTTPException(422,'البريد غير صالح')
    if email and db.scalar(select(User.id).where(User.email==email,User.id!=uid)):raise HTTPException(409,'البريد مستخدم')
    before={'full_name':target.full_name,'username':target.username,'email':target.email,'phone':target.phone,'notes':target.staff_notes}
    if username!=target.username:db.execute(delete(AuthSession).where(AuthSession.user_id==uid))
    target.username=username;target.full_name=data.full_name;target.phone=data.phone;target.staff_notes=data.notes
    target.email=email or (target.email if target.email.endswith('@accounts.invalid') else _unique_email(db,'','supervisor',uid))
    audit_change(db,u.id,mid,'supervisor_profile_edited',uid,before,data.model_dump());db.commit();return {'ok':True}

class RemoveSupervisor(Input):
    confirm_name: str

@router.delete('/supervisors/{uid}')
def remove_supervisor(mid:int,uid:int,data:RemoveSupervisor,request:Request,db=Depends(get_db)):
    u=_require(request,db,mid,{'owner'});target=db.get(User,uid)
    if not target or target.mosque_id!=mid or target.role!='halaqa_supervisor':raise HTTPException(404,'المشرف غير موجود')
    if data.confirm_name!=target.full_name:raise HTTPException(422,'اكتب اسم المشرف لتأكيد الإزالة')
    target.active=False
    db.execute(delete(AuthSession).where(AuthSession.user_id==uid))
    db.execute(update(HalaqaSupervisor).where(HalaqaSupervisor.user_id==uid).values(active=False))
    db.execute(update(Halaqa).where(Halaqa.supervisor_id==uid).values(supervisor_id=None))
    audit(db,u.id,mid,'supervisor_removed',json.dumps({'id':uid,'name':target.full_name},ensure_ascii=False));db.commit()
    return {'ok':True}
