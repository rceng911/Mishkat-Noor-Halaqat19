"""Persistent Quran-circle portal with owner-controlled account activation."""
from datetime import date, datetime, timedelta
import secrets
import string
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Literal
from zoneinfo import ZoneInfo
from sqlalchemy import select, func, delete

from app.api.routes import audit, audit_change, session
from app.db.session import get_db
from app.models import User, Mosque, AuthSession
from app.models.halaqat import Halaqa, HalaqaTeacher, HalaqaSupervisor, HalaqaStudent, HalaqaAccountRequest, HalaqaProgress
from app.services.auth import hash_password
from app.services.account_policy import validate_username, normalize_username
from app.services.password_policy import validate_password

class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


router = APIRouter(prefix="/api/halaqat", tags=["halaqat"])
SUPERVISOR_ROLE = "halaqa_supervisor"
TEACHER_ROLE = "halaqa_teacher"
STUDENT_ROLE = "halaqa_student"
PORTAL_ROLES = {SUPERVISOR_ROLE, TEACHER_ROLE, STUDENT_ROLE}


class SupervisorInput(Input):
    full_name: str = Field(min_length=2, max_length=180)
    username: str = Field(min_length=3, max_length=30)
    email: str = Field("", max_length=200)


class RingInput(Input):
    name: str = Field(min_length=2, max_length=180)
    schedule: str = Field("", max_length=500)
    supervisor_id: int | None = Field(None, gt=0)
    supervisor_ids: list[int] = Field(default_factory=list, max_length=100)


class TeacherRequestInput(Input):
    full_name: str = Field(min_length=2, max_length=180)
    requested_username: str = Field("", max_length=30)
    email: str = Field("", max_length=200)
    halaqa_id: int = Field(gt=0)
    notes: str = Field("", max_length=1000)


class StudentRequestInput(Input):
    recipient_type: Literal["student", "guardian"] = "guardian"
    full_name: str = Field(min_length=2, max_length=180)
    requested_username: str = Field("", max_length=30)
    email: str = Field("", max_length=200)
    halaqa_id: int = Field(gt=0)
    guardian_name: str = Field("", max_length=180)
    guardian_phone: str = Field("", max_length=40)
    guardian_relation: str = Field("", max_length=60)
    national_id: str = Field("", max_length=30, pattern=r"^[0-9٠-٩۰-۹]*$")
    birth_date: date | None = None
    school_grade: str = Field("", max_length=120)
    current_memorization: str = Field("", max_length=250)
    notes: str = Field("", max_length=1000)


class ApprovalInput(Input):
    username: str = Field("", max_length=30)
    email: str = Field("", max_length=200)
    temporary_password: str = Field("", max_length=128)
    existing_user_id: int | None = Field(None, gt=0)


class ProgressInput(Input):
    day: date
    attendance: str = Field("present", pattern="^(present|absent|excused)$")
    memorized: str = Field("", max_length=2000)
    revision: str = Field("", max_length=2000)
    notes: str = Field("", max_length=2000)
    memorized_amount: float = Field(0, ge=0, le=1000, allow_inf_nan=False)
    memorized_unit: Literal["page", "ayah"] = "page"
    revision_amount: float = Field(0, ge=0, le=1000, allow_inf_nan=False)
    revision_unit: Literal["page", "ayah"] = "page"
    memorization_score: int | None = Field(None, ge=0, le=10)
    tajweed_score: int | None = Field(None, ge=0, le=10)
    mistakes: int = Field(0, ge=0, le=1000)
    @model_validator(mode="after")
    def validate_amounts(self):
        for unit, amount in ((self.memorized_unit,self.memorized_amount),(self.revision_unit,self.revision_amount)):
            if unit == "ayah" and not float(amount).is_integer():
                raise ValueError("عدد الآيات يجب أن يكون صحيحًا")
        if self.attendance != "present" and (self.memorized_amount or self.revision_amount):
            raise ValueError("الإنجاز يسجل للحاضر فقط")
        return self


class RejectInput(Input):
    note: str = Field("", max_length=1000)


def _actor(request: Request, db):
    s = session(request)
    u = db.get(User, s.user_id) if s else None
    if not u or not u.active:
        raise HTTPException(401, "سجل الدخول أولًا")
    if u.force_password_change:
        raise HTTPException(403, "غيّر الرمز المؤقت أولًا")
    view = request.headers.get('x-portal-view') or request.query_params.get('view', '')
    if u.role == 'owner' and view in ('student', 'supervisor'):
        values = {c.name: getattr(u, c.name) for c in User.__table__.columns}
        values['original_role'] = 'owner'
        values['role'] = STUDENT_ROLE if view == 'student' else SUPERVISOR_ROLE
        return SimpleNamespace(**values)
    return u


def _require(request: Request, db, mosque_id: int, roles=None):
    query = select(Mosque).where(Mosque.id == mosque_id)
    if request.method not in ("GET", "HEAD"):
        query = query.with_for_update()
    if not db.scalar(query):
        raise HTTPException(404, "المسجد غير موجود")
    u = _actor(request, db)
    if u.role != "owner" and getattr(u, "original_role", "") != "owner" and u.mosque_id != mosque_id:
        raise HTTPException(403, "هذا الحساب غير مرتبط بهذا المسجد")
    if roles and u.role != "owner" and u.role not in roles:
        raise HTTPException(403, "ليست لديك صلاحية لهذا الإجراء")
    return u


def _clean_username(value: str, *, required=False):
    value = normalize_username(value)
    if not value and not required:
        return ""
    valid, error = validate_username(value)
    if not valid:
        raise HTTPException(422, error)
    return value


def _ensure_username(db, value: str):
    if db.scalar(select(User.id).where(User.username == value)):
        raise HTTPException(409, "اسم المستخدم مستخدم مسبقًا")


def _unique_email(db, requested: str, prefix: str, identifier: int):
    email = (requested or "").strip().lower()
    if email and db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "البريد الإلكتروني مستخدم مسبقًا")
    return email or f"{prefix}-{secrets.token_hex(12)}@accounts.invalid"


def _temporary_password():
    alphabet = string.ascii_letters + string.digits
    return "Mwn" + "".join(secrets.choice(alphabet) for _ in range(12)) + "@1"


def _user_pack(u: User | None):
    if not u:
        return None
    return {"id": u.id, "name": u.full_name, "username": u.username, "role": u.role, "account_type": u.account_type, "original_role": getattr(u, "original_role", u.role), "active": bool(u.active), "force_password_change": bool(u.force_password_change)}


def _account_pack(u: User, db):
    packed = _user_pack(u)
    packed["children"] = [
        {"id": s.id, "name": s.full_name, "halaqa_id": s.halaqa_id}
        for s in db.scalars(select(HalaqaStudent).where(HalaqaStudent.user_id == u.id, HalaqaStudent.active.is_(True)).order_by(HalaqaStudent.full_name)).all()
    ] if u.role in (STUDENT_ROLE, "owner") else []
    return packed


def _ring_pack(r: Halaqa, db):
    supervisor_ids = list(db.scalars(select(HalaqaSupervisor.user_id).where(HalaqaSupervisor.halaqa_id == r.id, HalaqaSupervisor.active.is_(True))))
    if r.supervisor_id and r.supervisor_id not in supervisor_ids:
        supervisor_ids.insert(0, r.supervisor_id)
    supervisors = [u for u in (db.get(User, uid) for uid in supervisor_ids) if u and u.active]
    supervisor = supervisors[0] if supervisors else None
    teacher_ids = list(db.scalars(select(HalaqaTeacher.user_id).where(HalaqaTeacher.halaqa_id == r.id, HalaqaTeacher.active.is_(True))))
    student_ids = list(db.scalars(select(HalaqaStudent.id).where(HalaqaStudent.halaqa_id == r.id, HalaqaStudent.active.is_(True)).order_by(HalaqaStudent.full_name)))
    student_count = len(student_ids)
    since = datetime.now(ZoneInfo("Asia/Riyadh")).date() - timedelta(days=29)
    rows = db.scalars(select(HalaqaProgress).where(HalaqaProgress.student_id.in_(student_ids), HalaqaProgress.day >= since)).all() if student_ids else []
    attendance_rows = [x for x in rows if x.attendance in ("present", "absent")]
    absence_rate = round((sum(x.attendance == "absent" for x in attendance_rows) / len(attendance_rows)) * 100) if attendance_rows else 0
    present_rows = [x for x in rows if x.attendance == "present"]
    completed = sum(bool((x.memorized or "").strip() or (x.revision or "").strip() or x.memorized_amount or x.revision_amount) for x in present_rows)
    completion_rate = round((completed / len(present_rows)) * 100) if present_rows else 0
    return {"id": r.id, "name": r.name, "schedule": r.schedule, "active": bool(r.active), "supervisor": _user_pack(supervisor), "supervisors": [_user_pack(u) for u in supervisors], "supervisor_ids": [u.id for u in supervisors], "teacher_ids": teacher_ids, "teachers": [{"id": t.id, "name": t.full_name} for t in (db.get(User, uid) for uid in teacher_ids) if t and t.active], "student_count": int(student_count), "completion_rate": completion_rate, "absence_rate": absence_rate}


def _request_pack(row: HalaqaAccountRequest, db):
    requester = db.get(User, row.requested_by)
    ring = db.get(Halaqa, row.halaqa_id) if row.halaqa_id else None
    return {"id": row.id, "type": row.request_type, "full_name": row.full_name, "requested_username": row.requested_username, "email": row.email, "recipient_type": row.recipient_type, "review_note": row.review_note, "guardian_name": row.guardian_name, "guardian_phone": row.guardian_phone, "guardian_relation": row.guardian_relation, "national_id": row.national_id or "", "birth_date": row.birth_date.isoformat() if row.birth_date else None, "school_grade": row.school_grade, "current_memorization": row.current_memorization, "notes": row.notes, "status": row.status, "ring": ring.name if ring else "", "halaqa_id": row.halaqa_id, "requested_by": _user_pack(requester), "created_at": row.created_at.isoformat() + "Z"}


def _ring_ids_for(u: User, mosque_id: int, db):
    if u.role == "owner" or (u.role == SUPERVISOR_ROLE and getattr(u, "original_role", "") == "owner"):
        return list(db.scalars(select(Halaqa.id).where(Halaqa.mosque_id == mosque_id, Halaqa.active.is_(True))))
    if u.role == SUPERVISOR_ROLE:
        # A supervisor oversees every circle within their own mosque, including imports.
        if u.mosque_id != mosque_id:
            return []
        return list(db.scalars(select(Halaqa.id).where(Halaqa.mosque_id == mosque_id, Halaqa.active.is_(True))))
    if u.role == TEACHER_ROLE:
        from app.models import SubstituteTeacher
        current = datetime.now(ZoneInfo('Asia/Riyadh')).date()
        permanent = list(db.scalars(select(HalaqaTeacher.halaqa_id).join(Halaqa,Halaqa.id==HalaqaTeacher.halaqa_id).where(HalaqaTeacher.user_id==u.id,HalaqaTeacher.active.is_(True),Halaqa.mosque_id==mosque_id,Halaqa.active.is_(True))))
        temporary = list(db.scalars(select(SubstituteTeacher.halaqa_id).join(Halaqa,Halaqa.id==SubstituteTeacher.halaqa_id).where(SubstituteTeacher.user_id==u.id,SubstituteTeacher.active.is_(True),SubstituteTeacher.start<=current,SubstituteTeacher.end>=current,Halaqa.mosque_id==mosque_id,Halaqa.active.is_(True))))
        return sorted(set(permanent+temporary))
    if u.role == STUDENT_ROLE:
        return list(db.scalars(select(HalaqaStudent.halaqa_id).join(Halaqa, Halaqa.id == HalaqaStudent.halaqa_id).where(HalaqaStudent.user_id == u.id, HalaqaStudent.active.is_(True), Halaqa.mosque_id == mosque_id)))
    return []


@router.get("/context")
def context(request: Request, db=Depends(get_db)):
    u = _actor(request, db)
    if u.role not in PORTAL_ROLES and u.role != "owner":
        raise HTTPException(403, "هذا الحساب ليس حساب حلقات")
    mosques = db.scalars(select(Mosque).order_by(Mosque.name)).all() if u.role == "owner" or getattr(u,"original_role","")=="owner" else ([db.get(Mosque, u.mosque_id)] if u.mosque_id else [])
    return {"ok": True, "user": _user_pack(u), "mosques": [{"id": m.id, "name": m.name} for m in mosques if m]}


@router.get("/mosques/{mosque_id}/dashboard")
def dashboard(mosque_id: int, request: Request, db=Depends(get_db)):
    u = _require(request, db, mosque_id, PORTAL_ROLES)
    ring_ids = _ring_ids_for(u, mosque_id, db)
    rings = [r for r in (db.get(Halaqa, rid) for rid in ring_ids) if r]
    if u.role == STUDENT_ROLE:
        students = db.scalars(select(HalaqaStudent).where(HalaqaStudent.user_id == u.id, HalaqaStudent.halaqa_id.in_(ring_ids), HalaqaStudent.active.is_(True)).order_by(HalaqaStudent.full_name)).all()
    else:
        students = db.scalars(select(HalaqaStudent).where(HalaqaStudent.halaqa_id.in_(ring_ids), HalaqaStudent.active.is_(True)).order_by(HalaqaStudent.full_name)).all() if ring_ids else []
    if u.role in ("owner", SUPERVISOR_ROLE):
        requests = db.scalars(select(HalaqaAccountRequest).where(HalaqaAccountRequest.mosque_id == mosque_id).order_by(HalaqaAccountRequest.id.desc())).all()
    else:
        requests = db.scalars(select(HalaqaAccountRequest).where(HalaqaAccountRequest.mosque_id == mosque_id, HalaqaAccountRequest.requested_by == u.id).order_by(HalaqaAccountRequest.id.desc())).all()
    if u.role == STUDENT_ROLE:
        requests = []
    student_ids = [s.id for s in students]
    progress = db.scalars(select(HalaqaProgress).where(HalaqaProgress.student_id.in_(student_ids)).order_by(HalaqaProgress.day.desc())).all() if student_ids else []
    accounts = db.scalars(select(User).where(User.mosque_id == mosque_id, User.role.in_(PORTAL_ROLES)).order_by(User.id)).all() if u.role == "owner" else []
    supervisors = db.scalars(select(User).where(User.mosque_id == mosque_id, User.role == SUPERVISOR_ROLE, User.active.is_(True))).all()
    since30 = datetime.now(ZoneInfo("Asia/Riyadh")).date() - timedelta(days=29)
    since60 = datetime.now(ZoneInfo("Asia/Riyadh")).date() - timedelta(days=59)
    per_student = {}
    for student in students:
        rows = [p for p in progress if p.student_id == student.id]
        recent30 = [p for p in rows if p.day >= since30]
        recent60 = [p for p in rows if p.day >= since60]
        absences = sum(p.attendance == "absent" for p in recent30)
        notes_count = sum(bool((p.notes or "").strip()) for p in recent60)
        scores = [x for p in recent60 for x in (p.memorization_score, p.tajweed_score) if x is not None]
        avg_score = round(sum(scores) / len(scores), 1) if scores else None
        per_student[student.id] = {
            "absences_30_days": absences,
            "repeated_notes": notes_count >= 3,
            "low_rating": avg_score is not None and len(scores) >= 2 and avg_score < 6,
            "avg_score": avg_score,
        }
    return {"ok": True, "user": _user_pack(u), "mosque": {"id": mosque_id, "name": db.get(Mosque, mosque_id).name}, "rings": [_ring_pack(r, db) for r in rings], "students": [{"id": s.id, "user_id": s.user_id, "name": s.full_name, "recipient_type": s.recipient_type, "guardian_name": s.guardian_name, "guardian_phone": s.guardian_phone, "has_national_id": bool(s.national_id), "guardian_relation": s.guardian_relation, "birth_date": s.birth_date.isoformat() if s.birth_date else None, "school_grade": s.school_grade, "current_memorization": s.current_memorization, "halaqa_id": s.halaqa_id, "notes": s.notes if u.role != STUDENT_ROLE else "", **per_student.get(s.id, {})} for s in students], "progress": [{"id": p.id, "student_id": p.student_id, "day": p.day.isoformat(), "attendance": p.attendance, "memorized": p.memorized, "revision": p.revision, "notes": p.notes, "memorization_score": p.memorization_score, "tajweed_score": p.tajweed_score} for p in progress], "requests": [_request_pack(r, db) for r in requests], "accounts": [_account_pack(x, db) for x in accounts], "supervisors": [_user_pack(x) for x in supervisors] if u.role == "owner" else [], "stats": {"rings": len(rings), "students": len(students), "pending_requests": sum(1 for r in requests if r.status == "pending")}}


@router.post("/mosques/{mosque_id}/supervisors")
def create_supervisor(mosque_id: int, data: SupervisorInput, request: Request, db=Depends(get_db)):
    owner = _require(request, db, mosque_id, {"owner"})
    count = db.scalar(select(func.count(User.id)).where(User.mosque_id == mosque_id, User.role == SUPERVISOR_ROLE, User.active.is_(True))) or 0
    username = _clean_username(data.username, required=True)
    _ensure_username(db, username)
    temp = _temporary_password()
    user = User(email=_unique_email(db, data.email, "supervisor", count + 1), username=username, password_hash=hash_password(temp), full_name=data.full_name.strip(), role=SUPERVISOR_ROLE, mosque_id=mosque_id, active=True, force_password_change=True)
    db.add(user); db.flush(); audit(db, owner.id, mosque_id, "halaqa_supervisor_created", str(user.id)); db.commit()
    return {"ok": True, "user": _user_pack(user), "temporary_password": temp, "message": "احفظ رمز الدخول الآن؛ لن يظهر مرة أخرى"}


@router.post("/mosques/{mosque_id}/rings")
def create_ring(mosque_id: int, data: RingInput, request: Request, db=Depends(get_db)):
    u = _require(request, db, mosque_id, {SUPERVISOR_ROLE})
    supervisor_ids = list(dict.fromkeys(data.supervisor_ids + ([data.supervisor_id] if data.supervisor_id else []))) if u.role == "owner" else [u.id]
    if not supervisor_ids:
        raise HTTPException(422, "اختر مشرفًا واحدًا على الأقل للحلقة")
    for supervisor_id in supervisor_ids:
        supervisor = db.get(User, supervisor_id)
        if not supervisor or supervisor.mosque_id != mosque_id or supervisor.role not in (SUPERVISOR_ROLE, "owner") or not supervisor.active:
            raise HTTPException(400, "اختر مشرفًا فعالًا من المسجد")
    ring = Halaqa(mosque_id=mosque_id, name=data.name.strip(), schedule=data.schedule.strip(), supervisor_id=supervisor_ids[0], active=True)
    db.add(ring); db.flush()
    for supervisor_id in supervisor_ids:
        db.add(HalaqaSupervisor(halaqa_id=ring.id, user_id=supervisor_id, assigned_by=u.id, active=True))
    audit(db, u.id, mosque_id, "halaqa_created", str(ring.id)); db.commit()
    return {"ok": True, "ring": _ring_pack(ring, db)}


@router.post("/mosques/{mosque_id}/requests/teacher")
def request_teacher(mosque_id: int, data: TeacherRequestInput, request: Request, db=Depends(get_db)):
    u = _require(request, db, mosque_id, {SUPERVISOR_ROLE})
    username = _clean_username(data.requested_username)
    ring = db.get(Halaqa, data.halaqa_id)
    if not ring or ring.mosque_id != mosque_id or not ring.active or (u.role != "owner" and ring.id not in _ring_ids_for(u, mosque_id, db)):
        raise HTTPException(400, "الحلقة غير مرتبطة بهذا المشرف")
    row = HalaqaAccountRequest(mosque_id=mosque_id, request_type="teacher", requested_by=u.id, halaqa_id=data.halaqa_id, full_name=data.full_name.strip(), requested_username=username, email=data.email.strip().lower(), notes=data.notes.strip(), status="pending")
    db.add(row); db.flush(); audit(db, u.id, mosque_id, "halaqa_teacher_requested", str(row.id)); db.commit()
    return {"ok": True, "request": _request_pack(row, db)}


@router.post("/mosques/{mosque_id}/requests/student")
def request_student(mosque_id: int, data: StudentRequestInput, request: Request, db=Depends(get_db)):
    u = _require(request, db, mosque_id, {TEACHER_ROLE, SUPERVISOR_ROLE})
    ring = db.get(Halaqa, data.halaqa_id)
    if not ring or ring.mosque_id != mosque_id or not ring.active:
        raise HTTPException(400, "الحلقة غير موجودة")
    if u.role != "owner" and data.halaqa_id not in _ring_ids_for(u, mosque_id, db):
        raise HTTPException(403, "هذه الحلقة غير مسندة لك")
    username = _clean_username(data.requested_username)
    if data.recipient_type == 'guardian' and not data.guardian_name:
        raise HTTPException(422, 'حدد اسم ولي الأمر')
    row = HalaqaAccountRequest(mosque_id=mosque_id, request_type="student", requested_by=u.id, halaqa_id=data.halaqa_id, full_name=data.full_name.strip(), recipient_type=data.recipient_type, requested_username=username, email=data.email.strip().lower(), guardian_name=data.guardian_name.strip(), guardian_phone=data.guardian_phone.strip(), guardian_relation=data.guardian_relation.strip(), birth_date=data.birth_date, school_grade=data.school_grade.strip(), current_memorization=data.current_memorization.strip(), notes=data.notes.strip(), status="pending")
    db.add(row); db.flush(); audit(db, u.id, mosque_id, "halaqa_student_requested", str(row.id)); db.commit()
    return {"ok": True, "request": _request_pack(row, db)}


@router.post("/mosques/{mosque_id}/requests/{request_id}/approve")
def approve_request(mosque_id: int, request_id: int, data: ApprovalInput, request: Request, db=Depends(get_db)):
    owner = _require(request, db, mosque_id, {"owner"})
    row = db.get(HalaqaAccountRequest, request_id)
    if not row or row.mosque_id != mosque_id:
        raise HTTPException(404, "الطلب غير موجود")
    if row.status != "pending":
        raise HTTPException(409, "تمت معالجة هذا الطلب مسبقًا")
    role = TEACHER_ROLE if row.request_type == "teacher" else STUDENT_ROLE
    if data.existing_user_id:
        if role != STUDENT_ROLE:
            raise HTTPException(422, "ربط حساب موجود متاح لولي أمر الطالب فقط")
        user = db.get(User, data.existing_user_id)
        if not user or (user.mosque_id != mosque_id and user.id != owner.id) or (user.role != STUDENT_ROLE and user.id != owner.id) or not user.active:
            raise HTTPException(400, "حساب ولي الأمر المختار غير صالح")
        if row.recipient_type == 'guardian' and user.account_type != 'guardian':
            raise HTTPException(422, 'اختر حساب ولي أمر')
        if row.recipient_type == 'student' and (user.account_type == 'guardian' or db.scalar(select(HalaqaStudent.id).where(HalaqaStudent.user_id == user.id))):
            raise HTTPException(422, 'حساب الطالب الذاتي يرتبط بملف طالب واحد فقط')
        temp = ""
    else:
        username = _clean_username(data.username or row.requested_username)
        if not username:
            username = normalize_username("_".join((row.guardian_name if role == STUDENT_ROLE and row.recipient_type == "guardian" and row.guardian_name else row.full_name).split()))[:30]
            if not validate_username(username)[0]:
                username = f"{row.request_type}_{row.id}"
        _clean_username(username, required=True); _ensure_username(db, username)
        temp = data.temporary_password or _temporary_password()
        valid, password_error = validate_password(temp)
        if not valid:
            raise HTTPException(422, password_error)
        email = _unique_email(db, data.email or row.email, row.request_type, row.id)
        account_name = row.guardian_name if role == STUDENT_ROLE and row.recipient_type == "guardian" and row.guardian_name else row.full_name
        user = User(email=email, username=username, password_hash=hash_password(temp), full_name=account_name, role=role, account_type=row.recipient_type if role == STUDENT_ROLE else "", mosque_id=mosque_id, active=True, force_password_change=True)
        db.add(user); db.flush()
    if role == TEACHER_ROLE:
        if row.halaqa_id:
            ring = db.get(Halaqa, row.halaqa_id)
            if not ring or ring.mosque_id != mosque_id or not ring.active:
                raise HTTPException(400, "الحلقة المرتبطة بالطلب غير موجودة")
            db.add(HalaqaTeacher(halaqa_id=ring.id, user_id=user.id, assigned_by=owner.id, active=True))
    else:
        ring = db.get(Halaqa, row.halaqa_id) if row.halaqa_id else None
        if not ring or ring.mosque_id != mosque_id or not ring.active:
            raise HTTPException(400, "يجب ربط الطالب بحلقة قبل التفعيل")
        db.add(HalaqaStudent(halaqa_id=ring.id, user_id=user.id, full_name=row.full_name, recipient_type=row.recipient_type, guardian_name=user.full_name if row.recipient_type == "guardian" else row.guardian_name, guardian_phone=row.guardian_phone, guardian_relation=row.guardian_relation, birth_date=row.birth_date, national_id=row.national_id, school_grade=row.school_grade, current_memorization=row.current_memorization, notes=row.notes, active=True))
    row.status = "approved"; row.reviewed_by = owner.id; row.reviewed_at = datetime.utcnow(); row.user_id = user.id
    audit(db, owner.id, mosque_id, "halaqa_request_approved", f"{row.request_type}:{row.id}:{user.id}"); db.commit()
    return {"ok": True, "request": _request_pack(row, db), "user": _account_pack(user, db), "temporary_password": temp, "linked_existing": bool(data.existing_user_id), "message": "تم ربط الابن بحساب ولي الأمر" if data.existing_user_id else "احفظ رمز الدخول الآن؛ لن يظهر مرة أخرى"}


@router.post("/mosques/{mosque_id}/requests/{request_id}/reject")
def reject_request(mosque_id: int, request_id: int, data: RejectInput, request: Request, db=Depends(get_db)):
    owner = _require(request, db, mosque_id, {"owner"})
    row = db.get(HalaqaAccountRequest, request_id)
    if not row or row.mosque_id != mosque_id:
        raise HTTPException(404, "الطلب غير موجود")
    if row.status != "pending":
        raise HTTPException(409, "تمت معالجة هذا الطلب مسبقًا")
    row.status = "rejected"; row.reviewed_by = owner.id; row.reviewed_at = datetime.utcnow()
    if data.note.strip(): row.notes = (row.notes + "\nسبب الرفض: " + data.note.strip()).strip()
    audit(db, owner.id, mosque_id, "halaqa_request_rejected", str(row.id)); db.commit()
    return {"ok": True, "request": _request_pack(row, db)}


@router.post("/mosques/{mosque_id}/users/{user_id}/reset")
def reset_user(mosque_id: int, user_id: int, request: Request, db=Depends(get_db)):
    owner = _require(request, db, mosque_id, {"owner"})
    user = db.get(User, user_id)
    if not user or user.mosque_id != mosque_id or user.role not in PORTAL_ROLES:
        raise HTTPException(404, "حساب الحلقات غير موجود")
    temp = _temporary_password(); user.password_hash = hash_password(temp); user.force_password_change = True
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    audit(db, owner.id, mosque_id, "halaqa_user_password_reset", str(user.id)); db.commit()
    return {"ok": True, "username": user.username, "temporary_password": temp, "message": "احفظ الرمز الجديد الآن"}


@router.post("/mosques/{mosque_id}/students/{student_id}/progress")
def add_progress(mosque_id: int, student_id: int, data: ProgressInput, request: Request, db=Depends(get_db)):
    u = _require(request, db, mosque_id, {TEACHER_ROLE, SUPERVISOR_ROLE})
    student = db.get(HalaqaStudent, student_id)
    if not student or not student.active:
        raise HTTPException(404, "الطالب غير موجود")
    if student.halaqa_id not in _ring_ids_for(u, mosque_id, db):
        raise HTTPException(403, "الطالب خارج الحلقات المسندة لك")
    row = db.scalar(select(HalaqaProgress).where(HalaqaProgress.student_id == student.id, HalaqaProgress.day == data.day))
    if data.day > datetime.now(ZoneInfo("Asia/Riyadh")).date():
        raise HTTPException(422, "لا يمكن تسجيل تقدم في يوم مستقبلي")
    if row is None:
        row = HalaqaProgress(student_id=student.id, day=data.day, created_by=u.id); db.add(row)
    before = {k:getattr(row,k) for k in ('attendance','memorized','revision','memorization_score','tajweed_score','mistakes','memorized_amount','revision_amount','notes')}
    from app.services.calendar import resolved_attendance
    row.attendance = resolved_attendance(db, student.id, data.day, data.attendance); row.memorized = data.memorized.strip(); row.revision = data.revision.strip(); row.notes = data.notes.strip()
    for k in ("memorized_amount","memorized_unit","revision_amount","revision_unit","memorization_score","tajweed_score","mistakes"):
        setattr(row, k, getattr(data, k))
    audit_change(db,u.id,mosque_id,"halaqa_progress_saved",student.id,before,data.model_dump(mode="json") | {"attendance":row.attendance}); db.commit()
    return {"ok": True, "progress": {"id": row.id, "student_id": row.student_id, "day": row.day.isoformat(), "attendance": row.attendance, "memorized": row.memorized, "revision": row.revision, "notes": row.notes}}
