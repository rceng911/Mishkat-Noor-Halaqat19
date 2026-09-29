"""Integration tests for role dashboards, admin usernames, scopes and approvals."""
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Halaqa, Mosque, User


def test_role_dashboard_direct_access_is_denied(network):
    owner = network["owner"]
    supervisor = network["supervisors"][0]
    teacher = network["teachers"][0]
    guardian = network["students"][0]  # fixture creates guardian-tracked student accounts

    assert owner.get("/dashboard/owner").status_code == 200
    assert owner.get("/dashboard/supervisor").status_code == 403
    assert supervisor.get("/dashboard/supervisor").status_code == 200
    assert supervisor.get("/dashboard/owner").status_code == 403
    assert teacher.get("/dashboard/teacher").status_code == 200
    assert teacher.get("/dashboard/owner").status_code == 403
    assert guardian.get("/dashboard/guardian").status_code == 200
    assert guardian.get("/dashboard/student").status_code == 403


def test_parent_and_teacher_directories_are_scoped(network):
    guardian = network["students"][0]
    teacher = network["teachers"][0]

    parent_dir = guardian.get("/api/access/mosques/1/directory")
    assert parent_dir.status_code == 200
    parent_students = parent_dir.json()["students"]
    assert [x["id"] for x in parent_students] == [network["ids"][0]]

    teacher_dir = teacher.get("/api/access/mosques/1/directory")
    assert teacher_dir.status_code == 200
    teacher_students = teacher_dir.json()["students"]
    assert {x["id"] for x in teacher_students} == {network["ids"][0]}


def test_other_branch_is_server_side_forbidden(network):
    supervisor = network["supervisors"][0]
    with SessionLocal() as db:
        db.add(Mosque(id=2, name="فرع آخر"))
        db.add(Halaqa(mosque_id=2, name="حلقة الفرع الآخر", active=True))
        db.commit()
    response = supervisor.get("/api/access/mosques/2/directory")
    assert response.status_code == 403


def test_owner_can_edit_username_and_duplicate_is_rejected(owner):
    first = owner.post("/api/access/mosques/1/users", json={
        "full_name": "مشرف إدارة أول",
        "username": "admin_sup_1",
        "role": "supervisor",
    })
    second = owner.post("/api/access/mosques/1/users", json={
        "full_name": "مشرف إدارة ثاني",
        "username": "admin_sup_2",
        "role": "supervisor",
    })
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    second_user = second.json()["user"]

    duplicate = owner.put(f"/api/access/mosques/1/users/{second_user['id']}", json={
        "full_name": second_user["name"],
        "username": "admin_sup_1",
        "email": "",
        "active": True,
    })
    assert duplicate.status_code == 409

    updated = owner.put(f"/api/access/mosques/1/users/{second_user['id']}", json={
        "full_name": "مشرف إدارة ثاني - معدل",
        "username": "admin_sup_2_new",
        "email": "",
        "active": True,
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["user"]["username"] == "admin_sup_2_new"


def test_supervisor_big_change_waits_for_owner_approval(network):
    owner = network["owner"]
    supervisor = network["supervisors"][0]
    ring_id = network["rings"][0]

    with SessionLocal() as db:
        old_name = db.get(Halaqa, ring_id).name

    created = supervisor.post("/api/access/mosques/1/change-requests", json={
        "action_type": "ring_update",
        "ring_id": ring_id,
        "name": old_name + " - بعد الاعتماد",
        "schedule": "جدول معدل",
        "reason": "اختبار مسار الموافقة",
    })
    assert created.status_code == 200, created.text
    request_id = created.json()["request"]["id"]

    with SessionLocal() as db:
        assert db.get(Halaqa, ring_id).name == old_name

    approved = owner.post(
        f"/api/access/mosques/1/change-requests/{request_id}/approve",
        json={"note": "موافق"},
    )
    assert approved.status_code == 200, approved.text

    with SessionLocal() as db:
        assert db.get(Halaqa, ring_id).name == old_name + " - بعد الاعتماد"

    log = owner.get("/api/access/mosques/1/audit")
    assert log.status_code == 200
    assert any(x["action"] == "change_request_approved" for x in log.json()["items"])
