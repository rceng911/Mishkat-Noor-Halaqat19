"""Role-aware dashboards, owner user administration, and approval workflow.

This module is additive: it reuses the existing authentication/session boundary and
circle models so current features continue to work unchanged.
"""
from __future__ import annotations

from datetime import datetime
import json
import secrets
import string
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
from app.api.routes import audit, audit_change, session
from app.db.session import get_db
from app.models import (
    AuditLog,
    AuthSession,
    Halaqa,
    HalaqaChangeRequest,
    HalaqaStudent,
    HalaqaSupervisor,
    HalaqaTeacher,
    User,
)
from app.services.auth import hash_password
from app.services.password_policy import validate_password

router = APIRouter(prefix="/api/access", tags=["role-access"])

ROLE_KEYS = {
    "supervisor": SUPERVISOR_ROLE,
    "teacher": TEACHER_ROLE,
    "student": STUDENT_ROLE,
    "guardian": STUDENT_ROLE,
}
ROLE_LABELS = {
    "owner": "المدير العام",
    "supervisor": "مشرف الفرع",
    "teacher": "المعلم",
    "guardian": "ولي الأمر",
    "student": "الطالب",
}
ACTION_LABELS = {
    "student_transfer": "نقل طالب بين الحلقات",
    "ring_update": "تعديل بيانات حلقة",
    "teacher_assignment": "تغيير معلمي الحلقة",
    "deactivate_user": "تعطيل حساب مستخدم",
}


def portal_kind(user) -> str:
    """Return the UI role without changing the stored, backwards-compatible role."""
    if user.role == "owner":
        return "owner"
    if user.role == SUPERVISOR_ROLE:
        return "supervisor"
    if user.role == TEACHER_ROLE:
        return "teacher"
    if user.role == STUDENT_ROLE:
        return "guardian" if (user.account_type or "") == "guardian" else "student"
    return "unknown"


def _actual_user(request: Request, db):
    s = session(request)
    user = db.get(User, s.user_id) if s else None
    if not user or not user.active:
        raise HTTPException(401, "سجل الدخول أولًا")
    if user.force_password_change:
        raise HTTPException(403, "غيّر الرمز المؤقت أولًا")
    return user


def _display_role(user: User) -> str:
    return ROLE_LABELS.get(portal_kind(user), user.role)


def _user_item(user: User, db) -> dict:
    children = []
    if user.role == STUDENT_ROLE and (user.account_type or "") == "guardian":
        children = [
            {"name": s.full_name, "halaqa_id": s.halaqa_id}
            for s in db.scalars(
                select(HalaqaStudent)
                .where(HalaqaStudent.user_id == user.id, HalaqaStudent.active.is_(True))
                .order_by(HalaqaStudent.full_name)
            ).all()
        ]
    return {
        "id": user.id,
        "name": user.full_name,
        "username": user.username,
        "email": "" if user.email.endswith("@accounts.invalid") else user.email,
        "active": bool(user.active),
        "role": user.role,
        "portal_role": portal_kind(user),
        "role_label": _display_role(user),
        "children": children,
    }


def _scoped_ring_ids(user: User, mid: int, db) -> set[int]:
    return set(_ring_ids_for(user, mid, db))


def _ring_in_scope(user: User, mid: int, rid: int, db) -> Halaqa:
    ring = db.get(Halaqa, rid)
    if not ring or ring.mosque_id != mid or not ring.active:
        raise HTTPException(404, "الحلقة غير موجودة")
    if user.role != "owner" and rid not in _scoped_ring_ids(user, mid, db):
        raise HTTPException(403, "الحلقة خارج نطاق صلاحيتك")
    return ring


def _student_in_scope(user: User, mid: int, sid: int, db) -> HalaqaStudent:
    student = db.get(HalaqaStudent, sid)
    if not student or not student.active:
        raise HTTPException(404, "الطالب غير موجود")
    ring = db.get(Halaqa, student.halaqa_id)
    if not ring or ring.mosque_id != mid:
        raise HTTPException(404, "الطالب غير موجود في هذا الفرع")
    if user.role != "owner" and student.halaqa_id not in _scoped_ring_ids(user, mid, db):
        raise HTTPException(403, "الطالب خارج نطاق صلاحيتك")
    return student


def _email_for_new_user(db, email: str, prefix: str) -> str:
    email = (email or "").strip().lower()
    if email:
        if "@" not in email or " " in email:
            raise HTTPException(422, "البريد الإلكتروني غير صالح")
        if db.scalar(select(User.id).where(User.email == email)):
            raise HTTPException(409, "البريد الإلكتروني مستخدم مسبقًا")
        return email
    return _unique_email(db, "", prefix, secrets.randbelow(900000000) + 100000000)


@router.get("/me")
def me(request: Request, db=Depends(get_db)):
    user = _actual_user(request, db)
    kind = portal_kind(user)
    if kind == "unknown":
        raise HTTPException(403, "هذا الحساب لا يملك واجهة حلقات")
    return {
        "ok": True,
        "id": user.id,
        "name": user.full_name,
        "portal_role": kind,
        "role_label": ROLE_LABELS[kind],
        "account_type": user.account_type or "",
        "dashboard": f"/dashboard/{kind}",
        "mosque_id": user.mosque_id,
    }


@router.get("/mosques/{mid}/directory")
def directory(mid: int, request: Request, db=Depends(get_db)):
    user = _require(request, db, mid, PORTAL_ROLES)
    ring_ids = _scoped_ring_ids(user, mid, db)
    rings = [r for r in db.scalars(select(Halaqa).where(Halaqa.id.in_(ring_ids)).order_by(Halaqa.name)).all()] if ring_ids else []
    if user.role == STUDENT_ROLE:
        students = db.scalars(
            select(HalaqaStudent)
            .where(
                HalaqaStudent.user_id == user.id,
                HalaqaStudent.halaqa_id.in_(ring_ids),
                HalaqaStudent.active.is_(True),
            )
            .order_by(HalaqaStudent.full_name)
        ).all() if ring_ids else []
    else:
        students = db.scalars(
            select(HalaqaStudent)
            .where(HalaqaStudent.halaqa_id.in_(ring_ids), HalaqaStudent.active.is_(True))
            .order_by(HalaqaStudent.full_name)
        ).all() if ring_ids else []

    teacher_ids = set()
    supervisor_ids = set()
    for rid in ring_ids:
        teacher_ids.update(db.scalars(select(HalaqaTeacher.user_id).where(HalaqaTeacher.halaqa_id == rid, HalaqaTeacher.active.is_(True))).all())
        supervisor_ids.update(db.scalars(select(HalaqaSupervisor.user_id).where(HalaqaSupervisor.halaqa_id == rid, HalaqaSupervisor.active.is_(True))).all())
    if user.role in ("owner", SUPERVISOR_ROLE):
        teacher_ids.update(db.scalars(select(User.id).where(User.mosque_id == mid, User.role == TEACHER_ROLE, User.active.is_(True))).all())
        supervisor_ids.update(db.scalars(select(User.id).where(User.mosque_id == mid, User.role == SUPERVISOR_ROLE, User.active.is_(True))).all())
    teachers = [u for u in (db.get(User, uid) for uid in sorted(teacher_ids)) if u and u.active]
    supervisors = [u for u in (db.get(User, uid) for uid in sorted(supervisor_ids)) if u and u.active]
    guardians = db.scalars(select(User).where(User.mosque_id == mid, User.role == STUDENT_ROLE, User.account_type == "guardian", User.active.is_(True)).order_by(User.full_name)).all() if user.role in ("owner", SUPERVISOR_ROLE) else []

    targets = []
    if user.role in ("owner", SUPERVISOR_ROLE):
        q = select(User).where(User.mosque_id == mid, User.role != "owner").order_by(User.full_name)
        targets = [{"id": u.id, "name": u.full_name, "role_label": _display_role(u), "active": bool(u.active)} for u in db.scalars(q).all()]

    return {
        "rings": [{"id": r.id, "name": r.name, "schedule": r.schedule} for r in rings],
        "students": [{"id": s.id, "name": s.full_name, "halaqa_id": s.halaqa_id} for s in students],
        "teachers": [{"id": u.id, "name": u.full_name} for u in teachers],
        "supervisors": [{"id": u.id, "name": u.full_name} for u in supervisors],
        "guardians": [{"id": u.id, "name": u.full_name} for u in guardians],
        "deactivation_targets": targets,
    }


class UserCreate(Input):
    full_name: str = Field(min_length=2, max_length=180)
    username: str = Field(min_length=3, max_length=30)
    email: str = Field("", max_length=200)
    role: Literal["supervisor", "teacher", "student", "guardian"]
    halaqa_id: int | None = Field(None, gt=0)
    temporary_password: str = Field("", max_length=128)


class UserEdit(Input):
    full_name: str = Field(min_length=2, max_length=180)
    username: str = Field(min_length=3, max_length=30)
    email: str = Field("", max_length=200)
    active: bool = True


@router.get("/mosques/{mid}/users")
def users(mid: int, request: Request, db=Depends(get_db)):
    _require(request, db, mid, {"owner"})
    rows = db.scalars(select(User).where(User.mosque_id == mid, User.role.in_(PORTAL_ROLES)).order_by(User.full_name)).all()
    return {"users": [_user_item(u, db) for u in rows]}


AUDIT_LABELS = {
    "owner_setup": "إعداد المدير العام",
    "login": "تسجيل دخول",
    "password_changed": "تغيير كلمة المرور",
    "user_created_by_owner": "إنشاء حساب من الإدارة",
    "user_profile_edited": "تعديل حساب من الإدارة",
    "halaqa_user_password_reset": "إصدار رمز مؤقت",
    "change_request_created": "رفع طلب تعديل",
    "change_request_approved": "اعتماد طلب تعديل",
    "change_request_rejected": "رفض طلب تعديل",
    "change_request_cancelled": "إلغاء طلب تعديل",
    "student_transferred_after_approval": "نقل طالب بعد الاعتماد",
    "ring_updated_after_approval": "تعديل حلقة بعد الاعتماد",
    "teachers_changed_after_approval": "تغيير معلمي حلقة بعد الاعتماد",
    "user_deactivated_after_approval": "تعطيل حساب بعد الاعتماد",
}


@router.get("/mosques/{mid}/audit")
def audit_log(mid: int, request: Request, db=Depends(get_db)):
    _require(request, db, mid, {"owner"})
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.mosque_id == mid)
        .order_by(AuditLog.id.desc())
        .limit(200)
    ).all()
    actors = {
        uid: db.get(User, uid)
        for uid in {row.user_id for row in rows if row.user_id}
    }
    return {
        "items": [
            {
                "id": row.id,
                "actor": actors.get(row.user_id).full_name if row.user_id and actors.get(row.user_id) else "النظام",
                "action": row.action,
                "action_label": AUDIT_LABELS.get(row.action, row.action.replace("_", " ")),
                "created_at": row.created_at.isoformat() + "Z",
            }
            for row in rows
        ]
    }


@router.post("/mosques/{mid}/users")
def create_user(mid: int, data: UserCreate, request: Request, db=Depends(get_db)):
    owner = _require(request, db, mid, {"owner"})
    username = _clean_username(data.username, required=True)
    if db.scalar(select(User.id).where(User.username == username)):
        raise HTTPException(409, "اسم المستخدم مستخدم مسبقًا")
    stored_role = ROLE_KEYS[data.role]
    account_type = data.role if data.role in ("student", "guardian") else ""
    if data.role in ("teacher", "student") and not data.halaqa_id:
        raise HTTPException(422, "اختر الحلقة لهذا الحساب")
    ring = None
    if data.halaqa_id:
        ring = _ring_in_scope(owner, mid, data.halaqa_id, db)
    password = data.temporary_password or _temporary_password()
    valid, error = validate_password(password)
    if not valid or len(password) > 128:
        raise HTTPException(422, error or "كلمة المرور المؤقتة غير صالحة")
    email = _email_for_new_user(db, data.email, data.role)
    user = User(
        email=email,
        username=username,
        full_name=data.full_name.strip(),
        password_hash=hash_password(password),
        role=stored_role,
        account_type=account_type,
        mosque_id=mid,
        active=True,
        force_password_change=True,
    )
    db.add(user)
    db.flush()
    if data.role == "teacher":
        db.add(HalaqaTeacher(halaqa_id=ring.id, user_id=user.id, assigned_by=owner.id, active=True))
    elif data.role == "student":
        db.add(HalaqaStudent(halaqa_id=ring.id, user_id=user.id, full_name=user.full_name, recipient_type="student", active=True))
    audit(db, owner.id, mid, "user_created_by_owner", json.dumps({"user_id": user.id, "role": data.role}, ensure_ascii=False))
    db.commit()
    return {
        "ok": True,
        "user": _user_item(user, db),
        "temporary_password": password,
        "message": "احفظ كلمة المرور المؤقتة؛ يجب تغييرها عند أول دخول",
    }


@router.put("/mosques/{mid}/users/{uid}")
def edit_user(mid: int, uid: int, data: UserEdit, request: Request, db=Depends(get_db)):
    owner = _require(request, db, mid, {"owner"})
    user = db.get(User, uid)
    if not user or user.mosque_id != mid or user.role not in PORTAL_ROLES:
        raise HTTPException(404, "المستخدم غير موجود")
    username = _clean_username(data.username, required=True)
    if db.scalar(select(User.id).where(User.username == username, User.id != uid)):
        raise HTTPException(409, "اسم المستخدم مستخدم مسبقًا")
    email = (data.email or "").strip().lower()
    if email and ("@" not in email or " " in email):
        raise HTTPException(422, "البريد الإلكتروني غير صالح")
    if email and db.scalar(select(User.id).where(User.email == email, User.id != uid)):
        raise HTTPException(409, "البريد الإلكتروني مستخدم مسبقًا")
    before = _user_item(user, db)
    username_changed = username != user.username
    active_changed = bool(data.active) != bool(user.active)
    user.full_name = data.full_name.strip()
    user.username = username
    user.active = bool(data.active)
    if email:
        user.email = email
    elif not user.email.endswith("@accounts.invalid"):
        user.email = _email_for_new_user(db, "", portal_kind(user))
    if username_changed or active_changed:
        db.execute(delete(AuthSession).where(AuthSession.user_id == uid))
    after = _user_item(user, db)
    audit_change(db, owner.id, mid, "user_profile_edited", uid, before, after)
    db.commit()
    return {"ok": True, "user": after}


class ChangeRequestInput(Input):
    action_type: Literal["student_transfer", "ring_update", "teacher_assignment", "deactivate_user"]
    reason: str = Field(min_length=3, max_length=1500)
    student_id: int | None = Field(None, gt=0)
    target_halaqa_id: int | None = Field(None, gt=0)
    ring_id: int | None = Field(None, gt=0)
    name: str = Field("", max_length=180)
    schedule: str = Field("", max_length=500)
    teacher_ids: list[int] = Field(default_factory=list, max_length=100)
    user_id: int | None = Field(None, gt=0)


class ReviewInput(Input):
    note: str = Field("", max_length=1500)


def _safe_json(value: str) -> dict:
    try:
        loaded = json.loads(value or "{}")
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _teacher_names(ids: list[int], db) -> str:
    names = [u.full_name for u in (db.get(User, x) for x in ids) if u]
    return "، ".join(names) or "بدون معلم"


def _request_labels(row: HalaqaChangeRequest, db) -> tuple[str, str, str]:
    before, after = _safe_json(row.before_json), _safe_json(row.after_json)
    target = ""
    before_label = ""
    after_label = ""
    if row.action_type == "student_transfer":
        student = db.get(HalaqaStudent, row.target_id)
        target = student.full_name if student else "طالب"
        before_ring = db.get(Halaqa, before.get("halaqa_id")) if before.get("halaqa_id") else None
        after_ring = db.get(Halaqa, after.get("halaqa_id")) if after.get("halaqa_id") else None
        before_label = before_ring.name if before_ring else "—"
        after_label = after_ring.name if after_ring else "—"
    elif row.action_type == "ring_update":
        ring = db.get(Halaqa, row.target_id)
        target = ring.name if ring else before.get("name", "حلقة")
        before_label = f"{before.get('name','')} · {before.get('schedule','') or 'بدون جدول'}"
        after_label = f"{after.get('name','')} · {after.get('schedule','') or 'بدون جدول'}"
    elif row.action_type == "teacher_assignment":
        ring = db.get(Halaqa, row.target_id)
        target = ring.name if ring else "حلقة"
        before_label = _teacher_names(before.get("teacher_ids", []), db)
        after_label = _teacher_names(after.get("teacher_ids", []), db)
    elif row.action_type == "deactivate_user":
        target_user = db.get(User, row.target_id)
        target = target_user.full_name if target_user else "مستخدم"
        before_label = "نشط" if before.get("active", True) else "معطل"
        after_label = "معطل"
    return target, before_label, after_label


def _change_item(row: HalaqaChangeRequest, db) -> dict:
    requester = db.get(User, row.requested_by)
    reviewer = db.get(User, row.reviewed_by) if row.reviewed_by else None
    target, before_label, after_label = _request_labels(row, db)
    return {
        "id": row.id,
        "action_type": row.action_type,
        "action_label": ACTION_LABELS.get(row.action_type, row.action_type),
        "target": target,
        "before_label": before_label,
        "after_label": after_label,
        "reason": row.reason,
        "status": row.status,
        "requester": requester.full_name if requester else "—",
        "reviewer": reviewer.full_name if reviewer else "",
        "review_note": row.review_note,
        "created_at": row.created_at.isoformat() + "Z",
        "reviewed_at": row.reviewed_at.isoformat() + "Z" if row.reviewed_at else None,
    }


def _active_teacher_ids(db, rid: int) -> list[int]:
    return sorted(db.scalars(select(HalaqaTeacher.user_id).where(HalaqaTeacher.halaqa_id == rid, HalaqaTeacher.active.is_(True))).all())


@router.get("/mosques/{mid}/change-requests")
def change_requests(mid: int, request: Request, db=Depends(get_db)):
    user = _require(request, db, mid, {SUPERVISOR_ROLE})
    q = select(HalaqaChangeRequest).where(HalaqaChangeRequest.mosque_id == mid)
    if user.role != "owner":
        q = q.where(HalaqaChangeRequest.requested_by == user.id)
    rows = db.scalars(q.order_by(HalaqaChangeRequest.id.desc()).limit(100)).all()
    return {"requests": [_change_item(row, db) for row in rows]}


@router.post("/mosques/{mid}/change-requests")
def create_change_request(mid: int, data: ChangeRequestInput, request: Request, db=Depends(get_db)):
    supervisor = _require(request, db, mid, {SUPERVISOR_ROLE})
    if supervisor.role == "owner":
        raise HTTPException(422, "المدير العام ينفذ التعديل من أدوات الإدارة مباشرة")
    before: dict
    after: dict
    target_type: str
    target_id: int

    if data.action_type == "student_transfer":
        if not data.student_id or not data.target_halaqa_id:
            raise HTTPException(422, "اختر الطالب والحلقة الجديدة")
        student = _student_in_scope(supervisor, mid, data.student_id, db)
        target_ring = _ring_in_scope(supervisor, mid, data.target_halaqa_id, db)
        if student.halaqa_id == target_ring.id:
            raise HTTPException(422, "الطالب موجود بالفعل في هذه الحلقة")
        before = {"halaqa_id": student.halaqa_id}
        after = {"halaqa_id": target_ring.id}
        target_type, target_id = "student", student.id
    elif data.action_type == "ring_update":
        if not data.ring_id or not data.name.strip():
            raise HTTPException(422, "اختر الحلقة وأدخل الاسم")
        ring = _ring_in_scope(supervisor, mid, data.ring_id, db)
        duplicate = db.scalar(select(Halaqa.id).where(Halaqa.mosque_id == mid, Halaqa.name == data.name.strip(), Halaqa.id != ring.id))
        if duplicate:
            raise HTTPException(409, "اسم الحلقة مستخدم")
        before = {"name": ring.name, "schedule": ring.schedule}
        after = {"name": data.name.strip(), "schedule": data.schedule.strip()}
        target_type, target_id = "ring", ring.id
    elif data.action_type == "teacher_assignment":
        if not data.ring_id:
            raise HTTPException(422, "اختر الحلقة")
        ring = _ring_in_scope(supervisor, mid, data.ring_id, db)
        ids = sorted(set(data.teacher_ids))
        for uid in ids:
            teacher = db.get(User, uid)
            if not teacher or not teacher.active or teacher.mosque_id != mid or teacher.role != TEACHER_ROLE:
                raise HTTPException(422, "اختر معلمين فعالين من الفرع")
        before = {"teacher_ids": _active_teacher_ids(db, ring.id)}
        after = {"teacher_ids": ids}
        target_type, target_id = "ring", ring.id
    else:
        if not data.user_id:
            raise HTTPException(422, "اختر المستخدم")
        target_user = db.get(User, data.user_id)
        if not target_user or target_user.mosque_id != mid or target_user.role == "owner":
            raise HTTPException(404, "المستخدم غير موجود في الفرع")
        if not target_user.active:
            raise HTTPException(422, "الحساب معطل بالفعل")
        before = {"active": True}
        after = {"active": False}
        target_type, target_id = "user", target_user.id

    existing = db.scalar(
        select(HalaqaChangeRequest.id).where(
            HalaqaChangeRequest.mosque_id == mid,
            HalaqaChangeRequest.requested_by == supervisor.id,
            HalaqaChangeRequest.action_type == data.action_type,
            HalaqaChangeRequest.target_id == target_id,
            HalaqaChangeRequest.status == "pending",
        )
    )
    if existing:
        raise HTTPException(409, "يوجد طلب معلق لنفس التعديل")
    row = HalaqaChangeRequest(
        mosque_id=mid,
        requested_by=supervisor.id,
        action_type=data.action_type,
        target_type=target_type,
        target_id=target_id,
        before_json=json.dumps(before, ensure_ascii=False),
        after_json=json.dumps(after, ensure_ascii=False),
        reason=data.reason.strip(),
        status="pending",
    )
    db.add(row)
    db.flush()
    audit(db, supervisor.id, mid, "change_request_created", f"{data.action_type}:{row.id}")
    db.commit()
    return {"ok": True, "request": _change_item(row, db)}


def _apply_change(db, owner: User, row: HalaqaChangeRequest):
    before = _safe_json(row.before_json)
    after = _safe_json(row.after_json)
    if row.action_type == "student_transfer":
        student = db.get(HalaqaStudent, row.target_id)
        if not student or not student.active:
            raise HTTPException(409, "ملف الطالب لم يعد متاحًا")
        current_ring = db.get(Halaqa, student.halaqa_id)
        target_ring = db.get(Halaqa, after.get("halaqa_id"))
        if not current_ring or current_ring.mosque_id != row.mosque_id or student.halaqa_id != before.get("halaqa_id"):
            raise HTTPException(409, "تغيرت بيانات الطالب منذ إنشاء الطلب؛ اطلب تعديلًا جديدًا")
        if not target_ring or not target_ring.active or target_ring.mosque_id != row.mosque_id:
            raise HTTPException(409, "الحلقة المطلوبة لم تعد متاحة")
        old = student.halaqa_id
        student.halaqa_id = target_ring.id
        audit_change(db, owner.id, row.mosque_id, "student_transferred_after_approval", student.id, {"halaqa_id": old}, {"halaqa_id": target_ring.id})
    elif row.action_type == "ring_update":
        ring = db.get(Halaqa, row.target_id)
        if not ring or ring.mosque_id != row.mosque_id:
            raise HTTPException(409, "الحلقة لم تعد متاحة")
        if ring.name != before.get("name") or (ring.schedule or "") != (before.get("schedule") or ""):
            raise HTTPException(409, "تغيرت الحلقة منذ إنشاء الطلب؛ اطلب تعديلًا جديدًا")
        duplicate = db.scalar(select(Halaqa.id).where(Halaqa.mosque_id == row.mosque_id, Halaqa.name == after.get("name"), Halaqa.id != ring.id))
        if duplicate:
            raise HTTPException(409, "اسم الحلقة مستخدم الآن")
        ring.name = after.get("name", ring.name)
        ring.schedule = after.get("schedule", "")
        audit_change(db, owner.id, row.mosque_id, "ring_updated_after_approval", ring.id, before, after)
    elif row.action_type == "teacher_assignment":
        ring = db.get(Halaqa, row.target_id)
        if not ring or ring.mosque_id != row.mosque_id:
            raise HTTPException(409, "الحلقة لم تعد متاحة")
        current = _active_teacher_ids(db, ring.id)
        expected = sorted(before.get("teacher_ids", []))
        if current != expected:
            raise HTTPException(409, "تغير معلمو الحلقة منذ إنشاء الطلب؛ اطلب تعديلًا جديدًا")
        ids = sorted(set(after.get("teacher_ids", [])))
        for uid in ids:
            teacher = db.get(User, uid)
            if not teacher or not teacher.active or teacher.mosque_id != row.mosque_id or teacher.role != TEACHER_ROLE:
                raise HTTPException(409, "أحد المعلمين لم يعد صالحًا للتعيين")
        links = db.scalars(select(HalaqaTeacher).where(HalaqaTeacher.halaqa_id == ring.id)).all()
        known = {x.user_id for x in links}
        for link in links:
            link.active = link.user_id in ids
        for uid in ids:
            if uid not in known:
                db.add(HalaqaTeacher(halaqa_id=ring.id, user_id=uid, assigned_by=owner.id, active=True))
        audit_change(db, owner.id, row.mosque_id, "teachers_changed_after_approval", ring.id, before, after)
    elif row.action_type == "deactivate_user":
        target_user = db.get(User, row.target_id)
        if not target_user or target_user.mosque_id != row.mosque_id or target_user.role == "owner":
            raise HTTPException(409, "الحساب لم يعد متاحًا")
        if bool(target_user.active) != bool(before.get("active", True)):
            raise HTTPException(409, "تغيرت حالة الحساب منذ إنشاء الطلب")
        target_user.active = False
        db.execute(delete(AuthSession).where(AuthSession.user_id == target_user.id))
        if target_user.role == TEACHER_ROLE:
            db.execute(update(HalaqaTeacher).where(HalaqaTeacher.user_id == target_user.id).values(active=False))
        elif target_user.role == SUPERVISOR_ROLE:
            db.execute(update(HalaqaSupervisor).where(HalaqaSupervisor.user_id == target_user.id).values(active=False))
            db.execute(update(Halaqa).where(Halaqa.supervisor_id == target_user.id).values(supervisor_id=None))
        audit_change(db, owner.id, row.mosque_id, "user_deactivated_after_approval", target_user.id, before, after)
    else:
        raise HTTPException(422, "نوع التعديل غير مدعوم")


@router.post("/mosques/{mid}/change-requests/{qid}/approve")
def approve_change(mid: int, qid: int, data: ReviewInput, request: Request, db=Depends(get_db)):
    owner = _require(request, db, mid, {"owner"})
    row = db.scalar(select(HalaqaChangeRequest).where(HalaqaChangeRequest.id == qid, HalaqaChangeRequest.mosque_id == mid).with_for_update())
    if not row:
        raise HTTPException(404, "طلب التعديل غير موجود")
    if row.status != "pending":
        raise HTTPException(409, "تمت معالجة الطلب مسبقًا")
    _apply_change(db, owner, row)
    row.status = "approved"
    row.reviewed_by = owner.id
    row.review_note = data.note.strip()
    row.reviewed_at = datetime.utcnow()
    audit(db, owner.id, mid, "change_request_approved", f"{row.action_type}:{row.id}")
    db.commit()
    return {"ok": True, "request": _change_item(row, db)}


@router.post("/mosques/{mid}/change-requests/{qid}/reject")
def reject_change(mid: int, qid: int, data: ReviewInput, request: Request, db=Depends(get_db)):
    owner = _require(request, db, mid, {"owner"})
    row = db.scalar(select(HalaqaChangeRequest).where(HalaqaChangeRequest.id == qid, HalaqaChangeRequest.mosque_id == mid).with_for_update())
    if not row:
        raise HTTPException(404, "طلب التعديل غير موجود")
    if row.status != "pending":
        raise HTTPException(409, "تمت معالجة الطلب مسبقًا")
    row.status = "rejected"
    row.reviewed_by = owner.id
    row.review_note = data.note.strip()
    row.reviewed_at = datetime.utcnow()
    audit(db, owner.id, mid, "change_request_rejected", f"{row.action_type}:{row.id}")
    db.commit()
    return {"ok": True, "request": _change_item(row, db)}


@router.post("/mosques/{mid}/change-requests/{qid}/cancel")
def cancel_change(mid: int, qid: int, request: Request, db=Depends(get_db)):
    user = _require(request, db, mid, {SUPERVISOR_ROLE})
    row = db.scalar(select(HalaqaChangeRequest).where(HalaqaChangeRequest.id == qid, HalaqaChangeRequest.mosque_id == mid).with_for_update())
    if not row:
        raise HTTPException(404, "طلب التعديل غير موجود")
    if row.status != "pending":
        raise HTTPException(409, "لا يمكن إلغاء طلب تمت معالجته")
    if user.role != "owner" and row.requested_by != user.id:
        raise HTTPException(403, "لا يمكنك إلغاء طلب مشرف آخر")
    row.status = "cancelled"
    row.reviewed_by = user.id
    row.reviewed_at = datetime.utcnow()
    audit(db, user.id, mid, "change_request_cancelled", f"{row.action_type}:{row.id}")
    db.commit()
    return {"ok": True, "request": _change_item(row, db)}
