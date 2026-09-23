from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal, engine
from app.models import User, StudentPlan, AuditLog, AuthSession
from app.api.student_file import today
from sqlalchemy import select

BASE = "/api/halaqat/mosques/1"

def test_setup_and_isolation(owner):
    assert owner.get("/").headers.get("content-type","").startswith("text/html")
    for route in ("/owner", "/screen", "/community", "/accessibility", "/register", "/api/v79/owner/users"):
        assert owner.get(route).status_code == 404
    assert owner.get("/healthz").json() == {"ok": True}
    assert "الإصدار 19" in owner.get("/halaqat").text
    assert owner.post("/setup",data={"organization":"ثان","full_name":"مالك آخر","username":"مالك_آخر","password":"OwnerPass1@","confirm_password":"OwnerPass1@"}, follow_redirects=False).headers["location"] == "/login"
    with SessionLocal() as db:
        assert len(db.scalars(select(User).where(User.role=="owner")).all()) == 1

def test_temporary_password_cannot_be_bypassed(owner):
    d=owner.post(BASE+"/supervisors",json={"full_name":"مشرف مؤقت","username":"مشرف_مؤقت"}).json()
    with TestClient(app) as c:
        c.post("/login",data={"identity":d["user"]["username"],"password":d["temporary_password"]},follow_redirects=False)
        assert c.get(BASE+"/dashboard").status_code == 403
        assert c.post(BASE+"/rings",json={"name":"حلقة جديدة"}).status_code == 403
        assert c.get("/halaqat",follow_redirects=False).headers["location"] == "/account/security"
        assert c.post("/account/security",data={"current_password":d["temporary_password"],"new_password":d["temporary_password"],"confirm_password":d["temporary_password"]}).status_code == 422
    with SessionLocal() as db:
        u=db.get(User,d["user"]["id"])
        assert d["temporary_password"] not in u.password_hash

def test_role_scope_and_multiple_supervisors(network):
    n=network
    third = n["owner"].post(BASE+"/supervisors",json={"full_name":"مشرف ثالث","username":"الثالث"})
    assert third.status_code == 200
    supervisor_ids = [x["id"] for x in n["owner"].get(BASE+"/dashboard").json()["supervisors"]][-2:]
    ring = n["owner"].post(BASE+"/rings", json={"name":"حلقة مشتركة","supervisor_ids":supervisor_ids})
    assert ring.status_code == 200, ring.text
    assert len(ring.json()["ring"]["supervisors"]) == 2
    for category in ("teachers","students"):
        c=n[category][0]
        assert c.get(BASE+f'/students/{n["ids"][1]}/file').status_code == 404
        assert c.get(BASE+f'/students/{n["ids"][1]}/report.csv').status_code == 404
        dash=c.get(BASE+"/dashboard").json()
        assert [s["id"] for s in dash["students"]] == [n["ids"][0]]
    teacher=n["teachers"][0]
    assert teacher.post(BASE+"/supervisors",json={"full_name":"مشرف آخر","username":"new_one"}).status_code == 403
    assert teacher.post(BASE+"/requests/student",json={"full_name":"طالب آخر","halaqa_id":n["rings"][1]}).status_code == 403
    assert n["supervisors"][0].post(BASE+"/requests/student",json={"full_name":"طالب آخر","halaqa_id":n["rings"][1],"recipient_type":"student"}).status_code == 200
    student=n["students"][0]
    assert student.put(BASE+f'/students/{n["ids"][0]}/plan',json={}).status_code == 403
    assert "ملاحظة داخلية" not in student.get(BASE+"/dashboard").text

@pytest.mark.parametrize("unit,amount",[("page",.5),("page",1),("page",2),("page",3.5),("ayah",7)])
def test_student_plan_sizes(network,unit,amount):
    sid=network["ids"][0];url=BASE+f"/students/{sid}"
    c=network["teachers"][0]
    r=c.put(url+"/plan",json={"memorization_unit":unit,"memorization_amount":amount,"revision_unit":"page","revision_amount":2,"start_surah":"البقرة","start_ayah":1,"end_surah":"البقرة","end_ayah":5})
    assert r.status_code == 200,r.text
    engine.dispose() # force new DB connections; persisted values must survive
    f=network["students"][0].get(url+"/file").json()
    assert f["plan"]["memorization_amount"] == amount
    assert f["weekly"]["memorization_target"] == amount*5
    assert f["can_edit"] is False

def test_plans_assessment_exams_certificates(network):
    n=network;sid=n["ids"][0];url=BASE+f"/students/{sid}";t=n["teachers"][0]
    assert t.put(url+"/plan",json={"memorization_unit":"ayah","memorization_amount":.5}).status_code == 422
    assert t.put(url+"/plan",json={"memorization_amount":.5,"revision_amount":2}).status_code == 200
    progress={"day":today().isoformat(),"memorized":"الفاتحة","memorized_amount":.5,"revision_amount":2,"memorization_score":9,"tajweed_score":8,"mistakes":1}
    assert t.post(url+"/progress",json=progress).status_code == 200
    assert t.post(url+"/progress",json=progress|{"memorization_score":10}).status_code == 200
    f=n["students"][0].get(url+"/file").json()
    assert len(f["progress"])==1 and f["weekly"]["memorization_done"]==.5
    assert f["progress"][0]["memorization_score"]==10
    assert t.post(url+"/progress",json=progress|{"attendance":"absent"}).status_code == 422
    assert t.post(url+"/progress",json=progress|{"day":(today()+timedelta(days=1)).isoformat()}).status_code == 422
    assert t.post(url+"/exams",json={"day":today().isoformat(),"title":"اختبار جزء عم","score":95,"total":100,"next_level":"المستوى الثاني"}).status_code==200
    assert t.post(url+"/exams",json={"day":today().isoformat(),"title":"اختبار","score":101,"total":100}).status_code==422
    cert={"title":"شهادة إنجاز","achievement":"إتمام جزء عم"}
    assert t.post(url+"/certificates",json=cert).status_code==403
    r=n["supervisors"][0].post(url+"/certificates",json=cert)
    assert r.status_code==200,r.text
    link=url+"/certificates/"+str(r.json()["id"])
    assert n["students"][0].get(link).status_code==200
    assert n["students"][1].get(link).status_code==404
    assert "إتمام جزء عم" in n["students"][0].get(link).text
    assert n["students"][0].get(url+"/file").json()["student"]["level"]=="المستوى الثاني"
    assert "الفاتحة" in n["students"][0].get(url+"/report.csv").text

def test_absences_reset_and_audit(network):
    n=network;sid=n["ids"][0];url=BASE+f"/students/{sid}"
    for days in (1,2,3):
        assert n["teachers"][0].post(url+"/progress",json={"day":(today()-timedelta(days=days)).isoformat(),"attendance":"absent"}).status_code==200
    assert n["supervisors"][0].get(url+"/file").json()["absence_alert"] is True
    uid=n["teachers"][0].get("/api/halaqat/context").json()["user"]["id"]
    assert n["owner"].post(BASE+f"/users/{uid}/reset").status_code==200
    assert n["teachers"][0].get("/api/halaqat/context").status_code==401
    with SessionLocal() as db:
        assert db.scalar(select(AuthSession.id).where(AuthSession.user_id==uid)) is None
        assert db.scalar(select(AuditLog.id).where(AuditLog.action=="halaqa_user_password_reset"))

def test_cross_site_block_and_session_headers(owner):
    assert owner.post(BASE+"/supervisors",json={"full_name":"مشرف","username":"supervisor"},headers={"origin":"https://evil.invalid"}).status_code==403
    assert owner.get("/halaqat").headers["cache-control"]=="no-store"
    assert owner.get("/static/halaqat.js").status_code==200

def test_login_throttle(owner):
    with TestClient(app) as c:
        for _ in range(10):
            assert c.post("/login",data={"identity":"not-found","password":"wrong"}).status_code==401
        assert c.post("/login",data={"identity":"not-found","password":"wrong"}).status_code==429


def test_remember_me_and_hidden_version(owner):
    with TestClient(app) as c:
        assert "الإصدار 19" not in c.get("/login").text
        ordinary = c.post("/login", data={"identity":"المالك","password":"OwnerPass1@"}, follow_redirects=False)
        assert "max-age=" not in ordinary.headers["set-cookie"].lower()
    with TestClient(app) as c:
        remembered = c.post("/login", data={"identity":"المالك","password":"OwnerPass1@","remember_me":"1"}, follow_redirects=False)
        assert "max-age=2592000" in remembered.headers["set-cookie"].lower()


def test_family_account_multiple_children_and_complete_request(network):
    n = network
    first_request = n["supervisors"][0].post(BASE+"/requests/student", json={
        "full_name":"الابن الأول", "halaqa_id":n["rings"][0], "guardian_name":"أب الأسرة",
        "guardian_phone":"0500000000", "guardian_relation":"الأب", "birth_date":"2014-02-03",
        "school_grade":"الصف السادس", "current_memorization":"سورة الملك", "notes":"ملف مكتمل"
    })
    assert first_request.status_code == 200, first_request.text
    approved = n["owner"].post(BASE+f'/requests/{first_request.json()["request"]["id"]}/approve', json={
        "username":"اب_الاسرة", "temporary_password":"FamilyPass1@"
    })
    assert approved.status_code == 200, approved.text
    family_user_id = approved.json()["user"]["id"]
    with TestClient(app) as family:
        login = family.post("/login", data={"identity":"اب_الاسرة","password":"FamilyPass1@"}, follow_redirects=False)
        assert login.headers["location"] == "/account/security"
        family.post("/account/security", data={"current_password":"FamilyPass1@","new_password":"FamilyPass2@","confirm_password":"FamilyPass2@"}, follow_redirects=False)
        second_request = n["teachers"][0].post(BASE+"/requests/student", json={
            "full_name":"الابن الثاني", "halaqa_id":n["rings"][0], "guardian_name":"أب الأسرة", "guardian_phone":"0500000000"
        }).json()["request"]
        linked = n["owner"].post(BASE+f'/requests/{second_request["id"]}/approve', json={"existing_user_id":family_user_id})
        assert linked.status_code == 200 and linked.json()["linked_existing"] is True
        dashboard = family.get(BASE+"/dashboard").json()
        assert {s["name"] for s in dashboard["students"]} == {"الابن الأول", "الابن الثاني"}
        assert dashboard["students"][0]["guardian_name"] == "أب الأسرة"
        assert "الإصدار 19" not in family.get("/halaqat").text
    accounts = n["owner"].get(BASE+"/dashboard").json()["accounts"]
    family_account = next(a for a in accounts if a["id"] == family_user_id)
    assert {c["name"] for c in family_account["children"]} == {"الابن الأول", "الابن الثاني"}
