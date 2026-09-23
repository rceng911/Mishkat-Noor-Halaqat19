import os
import tempfile
from pathlib import Path
import pytest

TEST_DIR = tempfile.TemporaryDirectory(prefix="halaqat-tests-")
os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = "sqlite:///" + (Path(TEST_DIR.name) / "test.db").as_posix()
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import Base, engine, SessionLocal

def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    TEST_DIR.cleanup()

@pytest.fixture
def owner():
    Base.metadata.drop_all(engine)
    with TestClient(app) as client:
        r = client.post("/setup", data={"organization":"حلقات الاختبار","full_name":"مالك الاختبار","username":"المالك","password":"OwnerPass1@","confirm_password":"OwnerPass1@"}, follow_redirects=False)
        assert r.status_code == 303, r.text
        yield client

@pytest.fixture
def network(owner):
    from contextlib import ExitStack
    from app.models import HalaqaStudent
    from sqlalchemy import select
    with ExitStack() as stack:
        def activate(username, temp):
            c = stack.enter_context(TestClient(app))
            r = c.post("/login", data={"identity":username,"password":temp}, follow_redirects=False)
            assert r.status_code == 303
            assert r.headers["location"] == "/account/security"
            assert c.get("/api/halaqat/context").status_code == 403
            new = "NewPass1@abc"
            r = c.post("/account/security", data={"current_password":temp,"new_password":new,"confirm_password":new}, follow_redirects=False)
            assert r.status_code == 303, r.text
            return c
        supervisors, teachers, students, student_ids, ring_ids = [], [], [], [], []
        for n in (1,2):
            d = owner.post("/api/halaqat/mosques/1/supervisors", json={"full_name":f"مشرف {n}","username":f"مشرف_{n}"}).json()
            sup = activate(d["user"]["username"], d["temporary_password"]); supervisors.append(sup)
            ring = sup.post("/api/halaqat/mosques/1/rings",json={"name":f"حلقة {n}","schedule":"الأحد إلى الخميس"}).json()["ring"]
            ring_ids.append(ring["id"])
            req = sup.post("/api/halaqat/mosques/1/requests/teacher",json={"full_name":f"مدرس {n}","halaqa_id":ring["id"]}).json()["request"]
            d = owner.post(f'/api/halaqat/mosques/1/requests/{req["id"]}/approve',json={}).json()
            teacher = activate(d["user"]["username"],d["temporary_password"]); teachers.append(teacher)
            req = teacher.post("/api/halaqat/mosques/1/requests/student",json={"full_name":f"طالب {n}","halaqa_id":ring["id"],"guardian_name":f"ولي {n}","notes":"ملاحظة داخلية"}).json()["request"]
            d = owner.post(f'/api/halaqat/mosques/1/requests/{req["id"]}/approve',json={}).json()
            students.append(activate(d["user"]["username"],d["temporary_password"]))
            with SessionLocal() as db:
                student_ids.append(db.scalar(select(HalaqaStudent.id).where(HalaqaStudent.user_id == d["user"]["id"])))
        yield {"owner":owner,"supervisors":supervisors,"teachers":teachers,"students":students,"ids":student_ids,"rings":ring_ids}
