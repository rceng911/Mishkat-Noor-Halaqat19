"""Owner account tools and approval workflow, designed to keep the v20.4 UI layout.

The stored roles remain backwards compatible. Student/guardian continue to share
``halaqa_student`` and are distinguished by ``account_type``.
"""
from __future__ import annotations

from datetime import datetime
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import delete, select, update

from app.api.halaqat import (
    Input,
    PORTAL_ROLES,
    STUDENT_ROLE,
    SUPERVISOR_ROLE,
    TEACHER_ROLE,
    _clean_username,
    _require,
    _ring_ids_for,
    _temporary_password,
    _unique_email,
)
from app.api.routes import audit, audit_change
from app.db.session import get_db
from app.models import (
    AuthSession,
    Halaqa,
    HalaqaChangeRequest,
    HalaqaStudent,
    HalaqaSupervisor,
    HalaqaTeacher,
    User,
)
from app.services.auth import hash_password

router = APIRouter(prefix="/api/access", tags=["access"])

ROLE_LABELS = {
    "owner": "المدير العام",
    SUPERVISOR_ROLE: "مشرف الفرع",
    TEACHER_ROLE: "المعلم",
    "guardian": "ولي الأمر",
    "student": "الطالب",
}
STATE_LABELS = {
    "pending": "بانتظار موافقة المدير",
    "approved": "تم الاعتماد",
    "rejected": "مرفوض",
    "cancelled": "ملغي",
}
ACTION_LABELS = {
    "student_transfer": "نقل طالب إلى حلقة أخرى",
    "student_archive": "أرشفة / استعادة طالب",
    "ring_update": "تعديل بيانات حلقة",
    "teacher_assignment": "تغيير معلمي الحلقة",
    "deactivate_user": "تعطيل / تفعيل حساب",
}


def _portal_role(user: User) -> str:
    if user.role == "owner":
        return "owner"
    if user.role == SUPERVISOR_ROLE:
        return SUPERVISOR_ROLE
    if user.role == TEACHER_ROLE:
        return TEACHER_ROLE
    if user.role == STUDENT_ROLE:
        return "guardian" if user.account_type == "guardian" else "student"
    return user.role


def _role_label(user: User) -> str:
    return ROLE_LABELS.get(_portal_role(user), user.role)


def _safe_json(value: str) -> dict:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def _ring_name(db, rid):
    row = db.get(Halaqa, rid) if rid else None
    return row.name if row else "—"


def _student_name(db, sid):
    row = db.get(HalaqaStudent, sid) if sid else None
    return row.full_name if row else "—"


def _user_name(db, uid):
    row = db.get(User, uid) if uid else None
    return row.full_name if row else "—"


def _request_item(row: HalaqaChangeRequest, db) -> dict:
    before = _safe_json(row.before_json)
    after = _safe_json(row.after_json)
    details = []
    if row.action_type == "student_transfer":
        details = [
            f"الطالب: {_student_name(db, row.target_id)}",
            f"من: {_ring_name(db, before.get('halaqa_id'))}",
            f"إلى: {_ring_name(db, after.get('halaqa_id'))}",
        ]
    elif row.action_type == "student_archive":
        details = [
            f"الطالب: {_student_name(db, row.target_id)}",
            "الحالة المطلوبة: " + ("فعال" if after.get("active") else "مؤرشف"),
        ]
    elif row.action_type == "ring_update":
        details = [
            f"الحلقة: {_ring_name(db, row.target_id)}",
            f"الاسم قبل: {before.get('name', '—')}",
            f"الاسم بعد: {after.get('name', '—')}",
            f"الموعد بعد: {after.get('schedule', '') or '—'}",
        ]
    elif row.action_type == "teacher_assignment":
        old = [_user_name(db, x) for x in before.get("teacher_ids", [])]
        new = [_user_name(db, x) for x in after.get("teacher_ids", [])]
        details = [
            f"الحلقة: {_ring_name(db, row.target_id)}",
            "المعلمون قبل: " + ("، ".join(old) or "لا يوجد"),
            "المعلمون بعد: " + ("، ".join(new) or "لا يوجد"),
        ]
    elif row.action_type == "deactivate_user":
        details = [
            f"الحساب: {_user_name(db, row.target_id)}",
            "الحالة المطلوبة: " + ("فعال" if after.get("active") else "معطل"),
        ]
    requester = db.get(User, row.requested_by)
    reviewer = db.get(User, row.reviewed_by) if row.reviewed_by else None
    return {
        "id": row.id,
        "action_type": row.action_type,
        "action_label": ACTION_LABELS.get(row.action_type, row.action_type),
        "status": row.status,
        "status_label": STATE_LABELS.get(row.status, row.status),
        "reason": row.reason,
        "details": details,
        "requested_by": requester.full_name if requester else "—",
        "reviewed_by": reviewer.full_name if reviewer else "",
        "review_note": row.review_note,
        "created_at": row.created_at.isoformat() + "Z",
        "reviewed_at": row.reviewed_at.isoformat() + "Z" if row.reviewed_at else "",
    }


def _scope_ring_ids(user, mid: int, db) -> set[int]:
    return set(_ring_ids_for(user, mid, db))


def _student_in_scope(user, mid: int, sid: int, db) -> HalaqaStudent:
    student = db.get(HalaqaStudent, sid)
    if not student:
        raise HTTPException(404, "الطالب غير موجود")
    ring = db.get(Halaqa, student.halaqa_id)
    if not ring or ring.mosque_id != mid:
        raise HTTPException(404, "الطالب غير موجود في هذا الفرع")
    if user.role != "owner" and student.halaqa_id not in _scope_ring_ids(user, mid, db):
        raise HTTPException(403, "الطالب خارج نطاق صلاحيتك")
    return student


def _ring_in_scope(user, mid: int, rid: int, db) -> Halaqa:
    ring = db.get(Halaqa, rid)
    if not ring or ring.mosque_id != mid:
        raise HTTPException(404, "الحلقة غير موجودة")
    if user.role != "owner" and rid not in _scope_ring_ids(user, mid, db):
        raise HTTPException(403, "الحلقة خارج نطاق صلاحيتك")
    return ring


class UserCreate(Input):
    full_name: str = Field(min_length=2, max_length=180)
    username: str = Field(min_length=3, max_length=30)
    role: Literal["supervisor", "teacher", "student", "guardian"]
    email: str = Field("", max_length=200)
    halaqa_id: int | None = Field(None, gt=0)
    student_id: int | None = Field(None, gt=0)


class UserEdit(Input):
    full_name: str = Field(min_length=2, max_length=180)
    username: str = Field(min_length=3, max_length=30)
    email: str = Field("", max_length=200)
    active: bool = True


class ChangeRequest(Input):
    action_type: Literal["student_transfer", "student_archive", "ring_update", "teacher_assignment", "deactivate_user"]
    reason: str = Field(min_length=2, max_length=1000)
    student_id: int | None = Field(None, gt=0)
    target_halaqa_id: int | None = Field(None, gt=0)
    active: bool | None = None
    ring_id: int | None = Field(None, gt=0)
    name: str = Field("", max_length=180)
    schedule: str = Field("", max_length=500)
    teacher_ids: list[int] = Field(default_factory=list, max_length=100)
    user_id: int | None = Field(None, gt=0)


class Review(Input):
    note: str = Field("", max_length=1000)


@router.get("/mosques/{mid}/overview")
def overview(mid: int, request: Request, db=Depends(get_db)):
    user = _require(request, db, mid, {SUPERVISOR_ROLE})
    if user.role not in ("owner", SUPERVISOR_ROLE):
        raise HTTPException(403, "هذه الأدوات للإدارة فقط")
    ring_ids = _scope_ring_ids(user, mid, db)
    rings = db.scalars(select(Halaqa).where(Halaqa.id.in_(ring_ids)).order_by(Halaqa.name)).all() if ring_ids else []
    students = db.scalars(select(HalaqaStudent).where(HalaqaStudent.halaqa_id.in_(ring_ids), HalaqaStudent.active.is_(True)).order_by(HalaqaStudent.full_name)).all() if ring_ids else []
    teachers = db.scalars(select(User).where(User.mosque_id == mid, User.role == TEACHER_ROLE, User.active.is_(True)).order_by(User.full_name)).all()
    users = []
    unlinked = []
    if user.role == "owner":
        users = db.scalars(select(User).where(User.mosque_id == mid, User.role.in_(PORTAL_ROLES)).order_by(User.full_name)).all()
        unlinked = db.scalars(
            select(HalaqaStudent)
            .join(Halaqa, Halaqa.id == HalaqaStudent.halaqa_id)
            .where(Halaqa.mosque_id == mid, HalaqaStudent.user_id.is_(None), HalaqaStudent.active.is_(True))
            .order_by(HalaqaStudent.full_name)
        ).all()
    q = select(HalaqaChangeRequest).where(HalaqaChangeRequest.mosque_id == mid)
    if user.role != "owner":
        q = q.where(HalaqaChangeRequest.requested_by == user.id)
    changes = db.scalars(q.order_by(HalaqaChangeRequest.id.desc()).limit(100)).all()
    return {
        "rings": [{"id": r.id, "name": r.name, "schedule": r.schedule} for r in rings],
        "students": [{"id": s.id, "name": s.full_name, "halaqa_id": s.halaqa_id} for s in students],
        "teachers": [{"id": u.id, "name": u.full_name} for u in teachers],
        "unlinked_students": [{"id": s.id, "name": s.full_name, "halaqa_id": s.halaqa_id} for s in unlinked],
        "users": [{
            "id": u.id,
            "name": u.full_name,
            "username": u.username,
            "email": "" if u.email.endswith("@accounts.invalid") else u.email,
            "active": bool(u.active),
            "role_label": _role_label(u),
        } for u in users],
        "change_requests": [_request_item(x, db) for x in changes],
        "pending_count": sum(1 for x in changes if x.status == "pending"),
    }


@router.post("/mosques/{mid}/users")
def create_user(mid: int, data: UserCreate, request: Request, db=Depends(get_db)):
    owner = _require(request, db, mid, {"owner"})
    if owner.role != "owner":
        raise HTTPException(403, "إصدار الحسابات من صلاحية المدير العام")
    username = _clean_username(data.username, required=True)
    if db.scalar(select(User.id).where(User.username == username)):
        raise HTTPException(409, "اسم المستخدم مستخدم مسبقًا")
    email = data.email.strip().lower()
    if email:
        if "@" not in email or " " in email:
            raise HTTPException(422, "البريد الإلكتروني غير صالح")
        if db.scalar(select(User.id).where(User.email == email)):
            raise HTTPException(409, "البريد الإلكتروني مستخدم مسبقًا")
    else:
        email = _unique_email(db, "", data.role, int(datetime.utcnow().timestamp() * 1000) % 2_000_000_000)
    role = {"supervisor": SUPERVISOR_ROLE, "teacher": TEACHER_ROLE, "student": STUDENT_ROLE, "guardian": STUDENT_ROLE}[data.role]
    temp = _temporary_password()
    user = User(
        email=email,
        username=username,
        password_hash=hash_password(temp),
        full_name=data.full_name.strip(),
        role=role,
        account_type=data.role if data.role in ("student", "guardian") else "",
        mosque_id=mid,
        active=True,
        force_password_change=True,
    )
    db.add(user); db.flush()
    if data.halaqa_id:
        ring = db.get(Halaqa, data.halaqa_id)
        if not ring or ring.mosque_id != mid or not ring.active:
            raise HTTPException(422, "الحلقة المختارة غير صالحة")
        if data.role == "teacher":
            db.add(HalaqaTeacher(halaqa_id=ring.id, user_id=user.id, assigned_by=owner.id, active=True))
        elif data.role == "supervisor":
            db.add(HalaqaSupervisor(halaqa_id=ring.id, user_id=user.id, assigned_by=owner.id, active=True))
    if data.student_id:
        if data.role not in ("student", "guardian"):
            raise HTTPException(422, "ربط ملف طالب متاح لحساب الطالب أو ولي الأمر")
        student = _student_in_scope(owner, mid, data.student_id, db)
        if student.user_id:
            raise HTTPException(409, "ملف الطالب مرتبط بحساب مسبقًا")
        if data.role == "student" and db.scalar(select(HalaqaStudent.id).where(HalaqaStudent.user_id == user.id)):
            raise HTTPException(409, "حساب الطالب يرتبط بملف طالب واحد")
        student.user_id = user.id
        student.recipient_type = data.role
        if data.role == "guardian":
            student.guardian_name = user.full_name
    audit(db, owner.id, mid, "account_issued", json.dumps({"user_id": user.id, "role": data.role}, ensure_ascii=False))
    db.commit()
    return {"ok": True, "user": {"id": user.id, "name": user.full_name, "username": user.username, "role_label": _role_label(user)}, "temporary_password": temp}


@router.put("/mosques/{mid}/users/{uid}")
def edit_user(mid: int, uid: int, data: UserEdit, request: Request, db=Depends(get_db)):
    owner = _require(request, db, mid, {"owner"})
    if owner.role != "owner":
        raise HTTPException(403, "إدارة الحسابات من صلاحية المدير العام")
    target = db.get(User, uid)
    if not target or target.mosque_id != mid or target.role == "owner" or target.role not in PORTAL_ROLES:
        raise HTTPException(404, "الحساب غير موجود")
    username = _clean_username(data.username, required=True)
    if db.scalar(select(User.id).where(User.username == username, User.id != uid)):
        raise HTTPException(409, "اسم المستخدم مستخدم مسبقًا")
    email = data.email.strip().lower()
    if email:
        if "@" not in email or " " in email:
            raise HTTPException(422, "البريد الإلكتروني غير صالح")
        if db.scalar(select(User.id).where(User.email == email, User.id != uid)):
            raise HTTPException(409, "البريد الإلكتروني مستخدم مسبقًا")
    elif not target.email.endswith("@accounts.invalid"):
        email = _unique_email(db, "", "user", uid)
    else:
        email = target.email
    before = {"full_name": target.full_name, "username": target.username, "email": target.email, "active": bool(target.active)}
    if username != target.username or (target.active and not data.active):
        db.execute(delete(AuthSession).where(AuthSession.user_id == uid))
    target.full_name = data.full_name.strip()
    target.username = username
    target.email = email
    target.active = data.active
    audit_change(db, owner.id, mid, "user_admin_edited", uid, before, {"full_name": target.full_name, "username": target.username, "email": target.email, "active": bool(target.active)})
    db.commit()
    return {"ok": True, "user": {"id": target.id, "name": target.full_name, "username": target.username, "active": bool(target.active)}}


@router.post("/mosques/{mid}/change-requests")
def create_change_request(mid: int, data: ChangeRequest, request: Request, db=Depends(get_db)):
    user = _require(request, db, mid, {SUPERVISOR_ROLE})
    if user.role != SUPERVISOR_ROLE:
        raise HTTPException(422, "طلبات الموافقة مخصصة لتعديلات مشرف الفرع")
    before = {}
    after = {}
    target_type = ""
    target_id = None
    if data.action_type == "student_transfer":
        if not data.student_id or not data.target_halaqa_id:
            raise HTTPException(422, "اختر الطالب والحلقة الجديدة")
        student = _student_in_scope(user, mid, data.student_id, db)
        _ring_in_scope(user, mid, data.target_halaqa_id, db)
        if student.halaqa_id == data.target_halaqa_id:
            raise HTTPException(409, "الطالب موجود أصلًا في هذه الحلقة")
        before = {"halaqa_id": student.halaqa_id}
        after = {"halaqa_id": data.target_halaqa_id}
        target_type, target_id = "student", student.id
    elif data.action_type == "student_archive":
        if not data.student_id or data.active is None:
            raise HTTPException(422, "حدد الطالب والحالة المطلوبة")
        student = _student_in_scope(user, mid, data.student_id, db)
        before = {"active": bool(student.active)}
        after = {"active": bool(data.active)}
        target_type, target_id = "student", student.id
    elif data.action_type == "ring_update":
        if not data.ring_id or len(data.name.strip()) < 2:
            raise HTTPException(422, "اختر الحلقة وأدخل الاسم")
        ring = _ring_in_scope(user, mid, data.ring_id, db)
        before = {"name": ring.name, "schedule": ring.schedule}
        after = {"name": data.name.strip(), "schedule": data.schedule.strip()}
        target_type, target_id = "ring", ring.id
    elif data.action_type == "teacher_assignment":
        if not data.ring_id:
            raise HTTPException(422, "اختر الحلقة")
        ring = _ring_in_scope(user, mid, data.ring_id, db)
        if len(data.teacher_ids) != len(set(data.teacher_ids)):
            raise HTTPException(422, "يوجد معلم مكرر")
        for uid in data.teacher_ids:
            target = db.get(User, uid)
            if not target or target.mosque_id != mid or target.role != TEACHER_ROLE or not target.active:
                raise HTTPException(422, "اختر معلمين فعالين من نفس الفرع")
        current = list(db.scalars(select(HalaqaTeacher.user_id).where(HalaqaTeacher.halaqa_id == ring.id, HalaqaTeacher.active.is_(True))))
        before = {"teacher_ids": current}
        after = {"teacher_ids": data.teacher_ids}
        target_type, target_id = "ring", ring.id
    elif data.action_type == "deactivate_user":
        if not data.user_id or data.active is None:
            raise HTTPException(422, "اختر الحساب والحالة المطلوبة")
        target = db.get(User, data.user_id)
        if not target or target.mosque_id != mid or target.role == "owner":
            raise HTTPException(404, "الحساب غير موجود")
        before = {"active": bool(target.active)}
        after = {"active": bool(data.active)}
        target_type, target_id = "user", target.id
    row = HalaqaChangeRequest(
        mosque_id=mid,
        requested_by=user.id,
        action_type=data.action_type,
        target_type=target_type,
        target_id=target_id,
        before_json=json.dumps(before, ensure_ascii=False),
        after_json=json.dumps(after, ensure_ascii=False),
        reason=data.reason.strip(),
        status="pending",
    )
    db.add(row); db.flush()
    audit(db, user.id, mid, "change_request_created", f"{row.id}:{row.action_type}")
    db.commit()
    return {"ok": True, "pending_approval": True, "message": "تم رفع التعديل للمدير العام للموافقة", "request": _request_item(row, db)}


def _apply_change(row: HalaqaChangeRequest, owner: User, db):
    before = _safe_json(row.before_json)
    after = _safe_json(row.after_json)
    if row.action_type == "student_transfer":
        student = db.get(HalaqaStudent, row.target_id)
        target = db.get(Halaqa, after.get("halaqa_id"))
        if not student or not target or target.mosque_id != row.mosque_id:
            raise HTTPException(409, "تعذر تنفيذ الطلب لأن البيانات تغيرت")
        student.halaqa_id = target.id
    elif row.action_type == "student_archive":
        student = db.get(HalaqaStudent, row.target_id)
        if not student:
            raise HTTPException(409, "ملف الطالب لم يعد موجودًا")
        student.active = bool(after.get("active"))
    elif row.action_type == "ring_update":
        ring = db.get(Halaqa, row.target_id)
        if not ring:
            raise HTTPException(409, "الحلقة لم تعد موجودة")
        name = str(after.get("name") or "").strip()
        if db.scalar(select(Halaqa.id).where(Halaqa.mosque_id == row.mosque_id, Halaqa.name == name, Halaqa.id != ring.id)):
            raise HTTPException(409, "اسم الحلقة مستخدم في الفرع")
        ring.name = name
        ring.schedule = str(after.get("schedule") or "").strip()
    elif row.action_type == "teacher_assignment":
        ring = db.get(Halaqa, row.target_id)
        if not ring:
            raise HTTPException(409, "الحلقة لم تعد موجودة")
        ids = [int(x) for x in after.get("teacher_ids", [])]
        for uid in ids:
            target = db.get(User, uid)
            if not target or target.mosque_id != row.mosque_id or target.role != TEACHER_ROLE or not target.active:
                raise HTTPException(409, "أحد المعلمين لم يعد صالحًا للتكليف")
        links = db.scalars(select(HalaqaTeacher).where(HalaqaTeacher.halaqa_id == ring.id)).all()
        known = {x.user_id for x in links}
        for link in links:
            link.active = link.user_id in ids
        for uid in ids:
            if uid not in known:
                db.add(HalaqaTeacher(halaqa_id=ring.id, user_id=uid, assigned_by=owner.id, active=True))
    elif row.action_type == "deactivate_user":
        target = db.get(User, row.target_id)
        if not target or target.role == "owner":
            raise HTTPException(409, "الحساب لم يعد متاحًا")
        target.active = bool(after.get("active"))
        if not target.active:
            db.execute(delete(AuthSession).where(AuthSession.user_id == target.id))
    else:
        raise HTTPException(422, "نوع التعديل غير مدعوم")
    audit_change(db, owner.id, row.mosque_id, "approved_sensitive_change", row.target_id or row.id, before, after)


@router.post("/mosques/{mid}/change-requests/{qid}/approve")
def approve_change(mid: int, qid: int, data: Review, request: Request, db=Depends(get_db)):
    owner = _require(request, db, mid, {"owner"})
    if owner.role != "owner":
        raise HTTPException(403, "الاعتماد من صلاحية المدير العام")
    row = db.scalar(select(HalaqaChangeRequest).where(HalaqaChangeRequest.id == qid, HalaqaChangeRequest.mosque_id == mid).with_for_update())
    if not row:
        raise HTTPException(404, "طلب التعديل غير موجود")
    if row.status != "pending":
        raise HTTPException(409, "تمت معالجة هذا الطلب مسبقًا")
    _apply_change(row, owner, db)
    row.status = "approved"
    row.reviewed_by = owner.id
    row.review_note = data.note.strip()
    row.reviewed_at = datetime.utcnow()
    audit(db, owner.id, mid, "change_request_approved", f"{row.id}:{row.action_type}")
    db.commit()
    return {"ok": True, "request": _request_item(row, db)}


@router.post("/mosques/{mid}/change-requests/{qid}/reject")
def reject_change(mid: int, qid: int, data: Review, request: Request, db=Depends(get_db)):
    owner = _require(request, db, mid, {"owner"})
    if owner.role != "owner":
        raise HTTPException(403, "الرفض من صلاحية المدير العام")
    row = db.scalar(select(HalaqaChangeRequest).where(HalaqaChangeRequest.id == qid, HalaqaChangeRequest.mosque_id == mid).with_for_update())
    if not row:
        raise HTTPException(404, "طلب التعديل غير موجود")
    if row.status != "pending":
        raise HTTPException(409, "تمت معالجة هذا الطلب مسبقًا")
    row.status = "rejected"
    row.reviewed_by = owner.id
    row.review_note = data.note.strip()
    row.reviewed_at = datetime.utcnow()
    audit(db, owner.id, mid, "change_request_rejected", f"{row.id}:{row.action_type}")
    db.commit()
    return {"ok": True, "request": _request_item(row, db)}
