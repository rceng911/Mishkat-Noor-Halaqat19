"""Student file: plans, recitation, exams, attendance and printable certificates."""
import csv
import io
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import Field, model_validator
from sqlalchemy import select
from app.db.session import get_db
from app.core.config import ROOT
from app.models import User, Mosque, Halaqa, HalaqaStudent, HalaqaProgress, StudentPlan, StudentExam, StudentCertificate
from app.api.halaqat import Input, _require, _ring_ids_for, _actor, PORTAL_ROLES, STUDENT_ROLE, SUPERVISOR_ROLE
from app.api.routes import audit
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/api/halaqat")
templates = Jinja2Templates(directory=str(ROOT / "web" / "templates"))

def today():
    return datetime.now(ZoneInfo("Asia/Riyadh")).date()

class PlanInput(Input):
    memorization_unit: Literal["page", "ayah"] = "page"
    memorization_amount: float = Field(1, gt=0, le=1000, allow_inf_nan=False)
    revision_unit: Literal["page", "ayah"] = "page"
    revision_amount: float = Field(2, gt=0, le=1000, allow_inf_nan=False)
    sessions_per_week: int = Field(5, ge=1, le=7)
    start_surah: str = Field("", max_length=120)
    start_ayah: int | None = Field(None, ge=1, le=286)
    end_surah: str = Field("", max_length=120)
    end_ayah: int | None = Field(None, ge=1, le=286)
    notes: str = Field("", max_length=2000)
    @model_validator(mode="after")
    def validate_units(self):
        for unit, amount in ((self.memorization_unit, self.memorization_amount), (self.revision_unit, self.revision_amount)):
            if unit == "ayah" and not float(amount).is_integer():
                raise ValueError("عدد الآيات يجب أن يكون عددًا صحيحًا")
        if self.start_ayah and not self.start_surah or self.end_ayah and not self.end_surah:
            raise ValueError("أدخل اسم السورة مع رقم الآية")
        return self

class ExamInput(Input):
    day: date
    title: str = Field(min_length=2, max_length=180)
    score: float = Field(ge=0, le=1000, allow_inf_nan=False)
    total: float = Field(100, gt=0, le=1000, allow_inf_nan=False)
    next_level: str = Field("", max_length=120)
    notes: str = Field("", max_length=2000)
    @model_validator(mode="after")
    def validate_score(self):
        if self.score > self.total:
            raise ValueError("الدرجة تتجاوز الدرجة الكاملة")
        if self.day > today():
            raise ValueError("لا يمكن تسجيل نتيجة اختبار مستقبلية")
        return self

class CertificateInput(Input):
    title: str = Field(min_length=2, max_length=180)
    achievement: str = Field("", max_length=2000)
    memorization_scope: str = Field("", max_length=250)
    mastery_percent: float | None = Field(None, ge=0, le=100, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_certificate(self):
        if self.memorization_scope:
            if len(self.memorization_scope) < 2 or self.mastery_percent is None:
                raise ValueError("حدد مقدار الحفظ ونسبة الإتقان")
        elif len(self.achievement) < 2 or self.mastery_percent is not None:
            raise ValueError("حدد مقدار الحفظ ونسبة الإتقان")
        return self

def access_student(db, request, mid, sid, write=False):
    roles = PORTAL_ROLES - {STUDENT_ROLE} if write else PORTAL_ROLES
    u = _require(request, db, mid, roles)
    s = db.get(HalaqaStudent, sid)
    if not s or (not s.active and (write or u.role not in ("owner", SUPERVISOR_ROLE))) or s.halaqa_id not in _ring_ids_for(u, mid, db):
        raise HTTPException(404, "ملف الطالب غير متاح لهذا الحساب")
    if u.role == STUDENT_ROLE and s.user_id != u.id:
        raise HTTPException(404, "ملف الطالب غير متاح")
    return u, s

def progress_pack(p):
    return {k: getattr(p,k) for k in ("id","student_id","attendance","memorized","revision","notes","memorized_amount","memorized_unit","revision_amount","revision_unit","memorization_score","tajweed_score","mistakes")} | {"day": p.day.isoformat()}

def file_pack(db, u, s, mid):
    ring = db.get(Halaqa, s.halaqa_id)
    plan = db.get(StudentPlan, s.id)
    rows = db.scalars(select(HalaqaProgress).where(HalaqaProgress.student_id == s.id).order_by(HalaqaProgress.day.desc())).all()
    exams = db.scalars(select(StudentExam).where(StudentExam.student_id == s.id).order_by(StudentExam.day.desc(), StudentExam.id.desc())).all()
    certificates = db.scalars(select(StudentCertificate).where(StudentCertificate.student_id == s.id).order_by(StudentCertificate.id.desc())).all()
    days30 = today() - timedelta(days=29)
    absences = sum(p.attendance == "absent" and p.day >= days30 for p in rows)
    # Sunday is the start of the teaching week.
    start_week = today() - timedelta(days=(today().weekday()+1) % 7)
    week = [p for p in rows if start_week <= p.day <= today() and p.attendance == "present"]
    weekly = None
    if plan:
        weekly = {
            "from": start_week.isoformat(),
            "memorization_target": plan.memorization_amount * plan.sessions_per_week,
            "memorization_done": sum(p.memorized_amount for p in week if p.memorized_unit == plan.memorization_unit),
            "revision_target": plan.revision_amount * plan.sessions_per_week,
            "revision_done": sum(p.revision_amount for p in week if p.revision_unit == plan.revision_unit),
            "memorization_unit": plan.memorization_unit, "revision_unit": plan.revision_unit
        }
    return {
        "ok": True, "can_edit": s.active and u.role != STUDENT_ROLE,
        "can_certify": s.active and u.role in ("owner", SUPERVISOR_ROLE),
        "student": {"active": s.active, "id": s.id, "user_id": s.user_id, "halaqa_id": s.halaqa_id, "recipient_type": s.recipient_type, "notes": s.notes if u.role != STUDENT_ROLE else "", "name": s.full_name, "level": s.level, "guardian_name": s.guardian_name,
                    "guardian_phone": s.guardian_phone, "guardian_relation": s.guardian_relation,
                    "national_id": s.national_id or "", "birth_date": s.birth_date.isoformat() if s.birth_date else None,
                    "school_grade": s.school_grade, "current_memorization": s.current_memorization,
                    "ring": ring.name, "schedule": ring.schedule},
        "plan": {k: getattr(plan,k) for k in PlanInput.model_fields} if plan else None,
        "weekly": weekly, "absences_30_days": absences, "absence_alert": absences >= 3,
        "progress": [progress_pack(p) for p in rows],
        "exams": [{"id": x.id, "day": x.day.isoformat(), "title": x.title, "score": x.score, "total": x.total, "next_level": x.next_level, "notes": x.notes} for x in exams],
        "certificates": [{"id": x.id, "title": x.title, "achievement": x.achievement, "issued_on": x.issued_on.isoformat(), "url": f"/api/halaqat/mosques/{mid}/students/{s.id}/certificates/{x.id}"} for x in certificates]
    }

@router.get("/mosques/{mid}/students/{sid}/file")
def student_file(mid: int, sid: int, request: Request, db=Depends(get_db)):
    u, s = access_student(db, request, mid, sid)
    return file_pack(db, u, s, mid)

@router.put("/mosques/{mid}/students/{sid}/plan")
def save_plan(mid: int, sid: int, data: PlanInput, request: Request, db=Depends(get_db)):
    u, s = access_student(db, request, mid, sid, True)
    row = db.get(StudentPlan, sid)
    if not row:
        row = StudentPlan(student_id=sid, updated_by=u.id); db.add(row)
    for k,v in data.model_dump().items():
        setattr(row,k,v)
    row.updated_by, row.updated_at = u.id, datetime.utcnow()
    audit(db, u.id, mid, "student_plan_saved", str(sid))
    db.commit()
    return {"ok": True}

@router.post("/mosques/{mid}/students/{sid}/exams")
def add_exam(mid: int, sid: int, data: ExamInput, request: Request, db=Depends(get_db)):
    u, s = access_student(db, request, mid, sid, True)
    row = StudentExam(student_id=sid, created_by=u.id, **data.model_dump())
    db.add(row)
    if data.next_level:
        s.level = data.next_level
    audit(db, u.id, mid, "student_exam_saved", str(sid)); db.commit()
    return {"ok": True, "id": row.id}

@router.post("/mosques/{mid}/students/{sid}/certificates")
def create_certificate(mid: int, sid: int, data: CertificateInput, request: Request, db=Depends(get_db)):
    u, s = access_student(db, request, mid, sid, True)
    if u.role not in ("owner", SUPERVISOR_ROLE):
        raise HTTPException(403, "إصدار الشهادة من صلاحية المالك والمشرف")
    values = data.model_dump()
    if data.memorization_scope:
        values['achievement'] = f"أكمل حفظ {data.memorization_scope} بنسبة إتقان {data.mastery_percent:g}%"
    row = StudentCertificate(student_id=sid, issued_by=u.id, issued_on=today(),
        student_name=s.full_name, student_national_id=s.national_id or '', **values)
    db.add(row); audit(db, u.id, mid, "student_certificate_issued", str(sid)); db.commit()
    return {"ok": True, "id": row.id}

@router.get("/mosques/{mid}/students/{sid}/certificates/{cid}")
def certificate(mid: int, sid: int, cid: int, request: Request, db=Depends(get_db)):
    u,s = access_student(db, request, mid, sid)
    cert = db.get(StudentCertificate, cid)
    if not cert or cert.student_id != sid:
        raise HTTPException(404, "الشهادة غير موجودة")
    issuer = db.get(User, cert.issued_by)
    return templates.TemplateResponse(request=request, name="certificate.html", context={
        "title": cert.title, "certificate": cert, "student": s, "organization": db.get(Mosque, mid).name, "issuer": issuer.full_name
    })

def csv_safe(value):
    value = "" if value is None else str(value)
    return "'" + value if value.lstrip().startswith(("=","+","-","@")) else value

@router.get("/mosques/{mid}/students/{sid}/report.csv")
def report(mid: int, sid: int, request: Request, db=Depends(get_db)):
    u,s = access_student(db, request, mid, sid)
    data = file_pack(db,u,s,mid)
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["الطالب","الحلقة","التاريخ","الحضور","الحفظ","المراجعة","درجة الحفظ من 10","درجة التجويد من 10","الأخطاء","ملاحظات"])
    labels = {"present":"حاضر","absent":"غائب","excused":"مستأذن"}
    for p in data["progress"]:
        writer.writerow([csv_safe(x) for x in [s.full_name, data["student"]["ring"], p["day"], labels[p["attendance"]], p["memorized"], p["revision"], p["memorization_score"], p["tajweed_score"], p["mistakes"], p["notes"]]])
    return Response("\ufeff"+stream.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="student-{sid}-report.csv"'})
