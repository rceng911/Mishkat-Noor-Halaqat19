"""Follow-up workflows. Every mutation is scoped and audited."""
import json
from datetime import date, datetime, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import Field, model_validator
from sqlalchemy import select
from app.db.session import get_db
from app.models import (User, Halaqa, HalaqaStudent, HalaqaAccountRequest, HalaqaProgress,
    StudentCertificate, StudentExam, Assignment, AlertRead, ExamAppointment, FeatureSetting)
from app.api.halaqat import (Input, StudentRequestInput, _require, _ring_ids_for, _request_pack,
    _clean_username, _account_pack, STUDENT_ROLE, SUPERVISOR_ROLE, PORTAL_ROLES)
from app.api.student_file import access_student, file_pack, today
from app.api.routes import audit, audit_change

router = APIRouter(prefix='/api/halaqat/mosques/{mid}')
FEATURES = ('assignments', 'notifications', 'rewards', 'monthly_reports')


@router.get('/students/{sid}/monthly.pdf')
def monthly(mid: int, sid: int, month: str, request: Request, db=Depends(get_db)):
    _, s = access_student(db, request, mid, sid); enabled(db, mid, 'monthly_reports')
    try:
        start = date.fromisoformat(month+'-01')
        end = date(start.year+1,1,1) if start.month==12 else date(start.year,start.month+1,1)
    except ValueError:
        raise HTTPException(422, 'اختر الشهر بصيغة YYYY-MM')
    rows=db.scalars(select(HalaqaProgress).where(HalaqaProgress.student_id==sid,HalaqaProgress.day>=start,HalaqaProgress.day<end).order_by(HalaqaProgress.day)).all()
    exams=db.scalars(select(StudentExam).where(StudentExam.student_id==sid,StudentExam.day>=start,StudentExam.day<end).order_by(StudentExam.day)).all()
    from app.services.monthly_report import monthly_pdf
    return Response(monthly_pdf(s,rows,exams,month), media_type='application/pdf', headers={'Content-Disposition':f'attachment; filename="student-{sid}-{month}.pdf"'})


def features(db, mid):
    row = db.get(FeatureSetting, mid)
    return dict.fromkeys(FEATURES, True) | (json.loads(row.settings_json) if row else {})


def enabled(db, mid, key):
    if not features(db, mid)[key]:
        raise HTTPException(403, 'هذه الميزة موقوفة من المالك')


class FeatureInput(Input):
    assignments: bool = True
    notifications: bool = True
    rewards: bool = True
    monthly_reports: bool = True


@router.put('/features')
def change_features(mid: int, data: FeatureInput, request: Request, db=Depends(get_db)):
    u = _require(request, db, mid, {'owner'})
    row = db.get(FeatureSetting, mid)
    if not row:
        row = FeatureSetting(mosque_id=mid); db.add(row)
    row.settings_json = json.dumps(data.model_dump())
    audit(db, u.id, mid, 'features_changed', row.settings_json); db.commit()
    return {'ok': True}


class ReturnInput(Input):
    note: str = Field(min_length=2, max_length=1000)


@router.post('/requests/{rid}/return')
def return_request(mid: int, rid: int, data: ReturnInput, request: Request, db=Depends(get_db)):
    u = _require(request, db, mid, {'owner'})
    row = db.get(HalaqaAccountRequest, rid)
    if not row or row.mosque_id != mid:
        raise HTTPException(404, 'الطلب غير موجود')
    if row.status != 'pending':
        raise HTTPException(409, 'يمكن إرجاع الطلب المعلق فقط')
    if row.request_type != 'student':
        raise HTTPException(422, 'الاستكمال متاح لملفات الطلاب')
    row.status = 'returned'; row.review_note = data.note; row.reviewed_by = u.id
    row.reviewed_at = datetime.utcnow()
    audit(db, u.id, mid, 'request_returned', str(rid)); db.commit()
    return {'ok': True}


@router.put('/requests/{rid}')
def amend_request(mid: int, rid: int, data: StudentRequestInput, request: Request, db=Depends(get_db)):
    u = _require(request, db, mid, {SUPERVISOR_ROLE, 'halaqa_teacher'})
    row = db.get(HalaqaAccountRequest, rid)
    if not row or row.mosque_id != mid or row.request_type != 'student':
        raise HTTPException(404, 'الطلب غير موجود')
    if row.status not in ('returned', 'pending'):
        raise HTTPException(409, 'الطلب تمت معالجته')
    if u.role != 'owner' and (row.requested_by != u.id or row.halaqa_id not in _ring_ids_for(u, mid, db)):
        raise HTTPException(403, 'يمكنك تعديل طلباتك ضمن حلقاتك فقط')
    if data.halaqa_id not in _ring_ids_for(u, mid, db):
        raise HTTPException(403, 'الحلقة خارج صلاحياتك')
    if data.recipient_type == 'guardian' and not data.guardian_name:
        raise HTTPException(422, 'حدد اسم ولي الأمر')
    values = data.model_dump(); values['requested_username'] = _clean_username(data.requested_username)
    for k, v in values.items():
        setattr(row, k, v)
    row.status = 'pending'
    audit(db, u.id, mid, 'request_resubmitted', str(rid)); db.commit()
    return {'ok': True, 'request': _request_pack(row, db)}


class ProfileInput(Input):
    full_name: str = Field(min_length=2, max_length=180)
    guardian_name: str = Field('', max_length=180)
    guardian_phone: str = Field('', max_length=40)
    guardian_relation: str = Field('', max_length=60)
    national_id: str = Field("", max_length=30, pattern=r"^[0-9٠-٩۰-۹]*$")
    birth_date: date | None = None
    school_grade: str = Field('', max_length=120)
    current_memorization: str = Field('', max_length=250)
    notes: str = Field('', max_length=1000)


@router.put('/students/{sid}/profile')
def profile(mid: int, sid: int, data: ProfileInput, request: Request, db=Depends(get_db)):
    u, s = access_student(db, request, mid, sid, True)
    if s.recipient_type == 'guardian' and not data.guardian_name:
        raise HTTPException(422, 'حدد اسم ولي الأمر')
    before={k:getattr(s,k) for k in data.model_fields if k != 'national_id'}
    for k, v in data.model_dump().items():
        if k=='national_id' and k not in data.model_fields_set:continue
        setattr(s, k, v)
    audit_change(db,u.id,mid,'student_profile_edited',sid,before,data.model_dump(mode='json', exclude={'national_id'})); db.commit()
    return {'ok': True}


class LinkInput(Input):
    user_id: int = Field(gt=0)
    recipient_type: Literal['student', 'guardian']


@router.put('/students/{sid}/recipient')
def link(mid: int, sid: int, data: LinkInput, request: Request, db=Depends(get_db)):
    u = _require(request, db, mid, {'owner'})
    _, s = access_student(db, request, mid, sid, True)
    target = db.get(User, data.user_id)
    if not target or not target.active or (target.mosque_id != mid and target.id != u.id) or (target.role != STUDENT_ROLE and target.id != u.id):
        raise HTTPException(422, 'الحساب غير صالح')
    if data.recipient_type == 'guardian' and target.account_type != 'guardian':
        raise HTTPException(422, 'اختر حساب ولي أمر')
    if data.recipient_type == 'student' and (target.account_type == 'guardian' or db.scalar(select(HalaqaStudent.id).where(HalaqaStudent.user_id == target.id, HalaqaStudent.id != sid))):
        raise HTTPException(422, 'حساب الطالب يرتبط بملف شخصي واحد')
    old = s.user_id; s.user_id = target.id; s.recipient_type = data.recipient_type
    if data.recipient_type == 'guardian':
        s.guardian_name = target.full_name
    audit_change(db,u.id,mid,'student_recipient_changed',sid,{'user_id':old},{'user_id':target.id,'recipient_type':data.recipient_type}); db.commit()
    return {'ok': True}


class TransferInput(Input):
    halaqa_id: int = Field(gt=0)


@router.post('/students/{sid}/transfer')
def transfer(mid: int, sid: int, data: TransferInput, request: Request, db=Depends(get_db)):
    u = _require(request, db, mid, {SUPERVISOR_ROLE})
    _, s = access_student(db, request, mid, sid, True)
    if data.halaqa_id not in _ring_ids_for(u, mid, db):
        raise HTTPException(403, 'الحلقة الجديدة خارج صلاحياتك')
    old = s.halaqa_id; s.halaqa_id = data.halaqa_id
    audit_change(db,u.id,mid,'student_transferred',sid,{'halaqa_id':old},{'halaqa_id':data.halaqa_id}); db.commit()
    return {'ok': True}


class AttendanceRow(Input):
    student_id: int = Field(gt=0)
    attendance: Literal['present', 'absent', 'excused']


class BatchInput(Input):
    day: date
    rows: list[AttendanceRow] = Field(min_length=1, max_length=500)


@router.post('/attendance/batch')
def batch(mid: int, data: BatchInput, request: Request, db=Depends(get_db)):
    u = _require(request, db, mid, {SUPERVISOR_ROLE, 'halaqa_teacher'})
    if data.day > today():
        raise HTTPException(422, 'لا يمكن التحضير ليوم مستقبلي')
    if len({r.student_id for r in data.rows}) != len(data.rows):
        raise HTTPException(422, 'طالب مكرر')
    # Validate the entire batch before changing any rows.
    for item in data.rows:
        access_student(db, request, mid, item.student_id, True)
        row = db.scalar(select(HalaqaProgress).where(HalaqaProgress.student_id == item.student_id, HalaqaProgress.day == data.day))
        if row and item.attendance != 'present' and (row.memorized_amount or row.revision_amount or row.memorized or row.revision):
            raise HTTPException(409, 'يوجد تسميع مسجل لأحد الطلاب؛ صححه من ملف الطالب قبل تغيير حضوره')
    for item in data.rows:
        row = db.scalar(select(HalaqaProgress).where(HalaqaProgress.student_id == item.student_id, HalaqaProgress.day == data.day))
        if not row:
            row = HalaqaProgress(student_id=item.student_id, day=data.day, created_by=u.id); db.add(row)
        from app.services.calendar import resolved_attendance
        value=resolved_attendance(db,item.student_id,data.day,item.attendance)
        audit_change(db,u.id,mid,'attendance_batch_student',item.student_id,{'day':str(data.day),'attendance':row.attendance},{'day':str(data.day),'attendance':value})
        row.attendance = value
    audit(db, u.id, mid, 'attendance_batch', f'{data.day}:{len(data.rows)}'); db.commit()
    return {'ok': True}


class AssignmentInput(Input):
    due: date
    memorization: str = Field('', max_length=1000)
    revision: str = Field('', max_length=1000)
    instructions: str = Field('', max_length=1000)
    @model_validator(mode='after')
    def check(self):
        if not self.memorization and not self.revision:
            raise ValueError('حدد ورد الحفظ أو المراجعة')
        return self


class ResultInput(Input):
    status: Literal['completed', 'partial', 'not_done', 'pending']
    result_note: str = Field('', max_length=1000)


@router.post('/students/{sid}/assignments')
def assignment(mid: int, sid: int, data: AssignmentInput, request: Request, db=Depends(get_db)):
    u, _ = access_student(db, request, mid, sid, True); enabled(db, mid, 'assignments')
    row = Assignment(student_id=sid, created_by=u.id, **data.model_dump()); db.add(row)
    audit(db, u.id, mid, 'assignment_created', str(sid)); db.commit()
    return {'ok': True, 'id': row.id}


@router.put('/students/{sid}/assignments/{aid}')
def assignment_result(mid: int, sid: int, aid: int, data: ResultInput, request: Request, db=Depends(get_db)):
    u, _ = access_student(db, request, mid, sid, True); enabled(db, mid, 'assignments')
    row = db.get(Assignment, aid)
    if not row or row.student_id != sid:
        raise HTTPException(404, 'الورد غير موجود')
    row.status = data.status; row.result_note = data.result_note
    audit(db, u.id, mid, 'assignment_assessed', f'{sid}:{aid}:{data.status}'); db.commit()
    return {'ok': True}


class AppointmentInput(Input):
    due: date
    title: str = Field(min_length=2, max_length=180)
    notes: str = Field('', max_length=1000)


@router.post('/students/{sid}/exam-appointments')
def appointment(mid: int, sid: int, data: AppointmentInput, request: Request, db=Depends(get_db)):
    u, _ = access_student(db, request, mid, sid, True)
    if data.due < today():
        raise HTTPException(422, 'موعد الاختبار يجب ألا يكون في الماضي')
    row = ExamAppointment(student_id=sid, created_by=u.id, **data.model_dump()); db.add(row)
    audit(db, u.id, mid, 'exam_scheduled', str(sid)); db.commit()
    return {'ok': True, 'id': row.id}


def extras(db, u, s, mid):
    f = file_pack(db, u, s, mid)
    assigned = db.scalars(select(Assignment).where(Assignment.student_id == s.id).order_by(Assignment.due, Assignment.id)).all()
    assigned.sort(key=lambda a: (a.status != 'pending', a.due if a.status == 'pending' else -a.due.toordinal(), a.id))
    appointments = db.scalars(select(ExamAppointment).where(ExamAppointment.student_id == s.id, ExamAppointment.due >= today()).order_by(ExamAppointment.due)).all()
    start = today() - timedelta(days=(today().weekday()+1) % 7)
    week = [p for p in f['progress'] if start.isoformat() <= p['day'] <= today().isoformat()]
    points = sum(2 for p in f['progress'] if p['attendance']=='present') + sum(5 for a in assigned if a.status=='completed')
    badges = []
    if sum(p['attendance']=='present' for p in week) >= 5: badges.append('مواظب الأسبوع')
    if any(a.status=='completed' for a in assigned): badges.append('أتم وردًا')
    if f['weekly'] and f['weekly']['memorization_done'] >= f['weekly']['memorization_target']: badges.append('حقق هدف الحفظ الأسبوعي')
    return {'assignments': [{k: (getattr(a,k).isoformat() if k=='due' else getattr(a,k)) for k in ('id','due','memorization','revision','instructions','status','result_note')} for a in assigned],
        'appointments': [{'id':a.id, 'due':a.due.isoformat(), 'title':a.title, 'notes':a.notes} for a in appointments],
        'rewards': {'points': points, 'badges':badges, 'weekly':f['weekly']}, 'file':f}


@router.get('/students/{sid}/followup')
def followup(mid: int, sid: int, request: Request, db=Depends(get_db)):
    u, s = access_student(db, request, mid, sid)
    result = extras(db, u, s, mid); result.pop('file')
    flags = features(db, mid)
    if not flags['assignments']: result['assignments'] = []
    if not flags['rewards']: result['rewards'] = None
    return result | {'features': flags}


def monitor_data(db, u, mid):
    ids = _ring_ids_for(u, mid, db)
    query = select(HalaqaStudent).where(HalaqaStudent.halaqa_id.in_(ids), HalaqaStudent.active.is_(True))
    if u.role == STUDENT_ROLE: query = query.where(HalaqaStudent.user_id == u.id)
    students = db.scalars(query).all()
    reads = set(db.scalars(select(AlertRead.alert_key).where(AlertRead.user_id==u.id)))
    alerts=[]; struggling=[]; flags=features(db,mid)
    def add(key, s, message):
        alerts.append({'key':key, 'student_id':s.id, 'student':s.full_name, 'message':message, 'read':key in reads})
    for s in students:
        x=extras(db,u,s,mid); f=x['file']; weak=False
        for p in f['progress']:
            if p['day'] < (today()-timedelta(days=29)).isoformat(): continue
            if p['attendance']=='absent': add(f'absence:{p["id"]}',s,'غياب بتاريخ '+p['day'])
            if p['attendance']=='present' and f['plan'] and p['revision_unit']==f['plan']['revision_unit'] and p['revision_amount'] < f['plan']['revision_amount']:
                add(f'revision:{p["id"]}',s,'المراجعة أقل من الخطة بتاريخ '+p['day']); weak=True
        for a in x['appointments']: add(f'exam:{a["id"]}',s,'اختبار '+a['title']+' بتاريخ '+a['due'])
        for a in x['assignments']:
            if flags['assignments'] and a['status']=='pending': add(f'ward:{a["id"]}',s,'ورد التسميع القادم بتاريخ '+a['due'])
        for c in f['certificates']: add(f'certificate:{c["id"]}',s,'إنجاز جديد: '+c['achievement'])
        for b in (x['rewards']['badges'] if flags['rewards'] else []): add(f'badge:{s.id}:{today().year}:{today().isocalendar().week}:{b}',s,b)
        if weak or f['absence_alert']: struggling.append({'id':s.id,'name':s.full_name,'reason':'غياب متكرر' if f['absence_alert'] else 'مراجعة أقل من الخطة'})
    missing=[]
    if u.role != STUDENT_ROLE:
        for rid in ids:
            from app.services.calendar import meeting_day
            if not meeting_day(db, rid, today()): continue
            own=[s for s in students if s.halaqa_id==rid]
            recorded=set(db.scalars(select(HalaqaProgress.student_id).where(HalaqaProgress.day==today(), HalaqaProgress.student_id.in_([s.id for s in own]))))
            if own and len(recorded)<len(own): missing.append({'id':rid,'name':db.get(Halaqa,rid).name,'missing':len(own)-len(recorded)})
    return {'alerts':alerts,'struggling':struggling,'missing_attendance':missing}


@router.get('/monitor')
def monitor(mid: int, request: Request, db=Depends(get_db)):
    u=_require(request,db,mid,PORTAL_ROLES)
    result=monitor_data(db,u,mid); flags=features(db,mid)
    if not flags['notifications']: result['alerts']=[]
    if u.role==STUDENT_ROLE: result['struggling']=[]
    targets=[]
    if u.role=='owner':
        targets=[_account_pack(x,db) for x in db.scalars(select(User).where((User.mosque_id==mid) | (User.id==u.id),User.active.is_(True),User.role.in_([STUDENT_ROLE,'owner'])))]
    return result | {'features':flags,'recipients':targets}


class ReadInput(Input):
    key: str = Field(min_length=1,max_length=160)


@router.post('/alerts/read')
def read_alert(mid: int,data:ReadInput,request:Request,db=Depends(get_db)):
    u=_require(request,db,mid,PORTAL_ROLES)
    enabled(db,mid,'notifications')
    if data.key not in {a['key'] for a in monitor_data(db,u,mid)['alerts']}:
        raise HTTPException(404,'التنبيه غير موجود')
    if not db.scalar(select(AlertRead.id).where(AlertRead.user_id==u.id,AlertRead.alert_key==data.key)):
        db.add(AlertRead(user_id=u.id,alert_key=data.key)); db.commit()
    return {'ok':True}

class RecipientAccountInput(Input):
    recipient_type: Literal['student', 'guardian']
    full_name: str = Field(min_length=2, max_length=180)
    username: str = Field(min_length=3, max_length=30)
    temporary_password: str = Field('', max_length=128)


@router.post('/students/{sid}/recipient-account')
def create_recipient_account(mid: int, sid: int, data: RecipientAccountInput, request: Request, db=Depends(get_db)):
    from app.api.halaqat import _ensure_username, _temporary_password, _unique_email
    from app.services.auth import hash_password
    from app.services.password_policy import validate_password
    u = _require(request, db, mid, {'owner'})
    _, s = access_student(db, request, mid, sid, True)
    username = _clean_username(data.username, required=True); _ensure_username(db, username)
    password = data.temporary_password or _temporary_password()
    valid, error = validate_password(password)
    if not valid: raise HTTPException(422, error)
    target = User(username=username, email=_unique_email(db, '', 'student', sid), full_name=data.full_name,
        password_hash=hash_password(password), role=STUDENT_ROLE, account_type=data.recipient_type,
        mosque_id=mid, active=True, force_password_change=True)
    db.add(target); db.flush()
    old = s.user_id; s.user_id = target.id; s.recipient_type = data.recipient_type
    if data.recipient_type == 'guardian': s.guardian_name = target.full_name
    audit(db,u.id,mid,'student_recipient_account_created',f'{sid}:{old}->{target.id}'); db.commit()
    return {'ok':True, 'user':_account_pack(target, db), 'temporary_password':password}
