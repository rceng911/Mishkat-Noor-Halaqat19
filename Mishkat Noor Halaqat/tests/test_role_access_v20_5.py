"""Role/UI workflow tests added for v20.5 without removing v20.4 features."""
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import Halaqa, HalaqaStudent, User


def test_owner_username_edit_and_duplicate_rejected(network):
    owner=network['owner']
    ctx=owner.get('/api/access/mosques/1/overview')
    assert ctx.status_code==200,ctx.text
    users=ctx.json()['users']
    teacher=next(x for x in users if x['role_label']=='المعلم')
    supervisor=next(x for x in users if x['role_label']=='مشرف الفرع')
    duplicate=owner.put(f"/api/access/mosques/1/users/{teacher['id']}",json={
        'full_name':teacher['name'],'username':supervisor['username'],'email':teacher['email'],'active':True})
    assert duplicate.status_code==409
    changed=owner.put(f"/api/access/mosques/1/users/{teacher['id']}",json={
        'full_name':teacher['name'],'username':'teacher_new_name','email':teacher['email'],'active':True})
    assert changed.status_code==200,changed.text
    assert changed.json()['user']['username']=='teacher_new_name'


def test_owner_can_issue_account_with_unique_username(owner):
    made=owner.post('/api/access/mosques/1/users',json={
        'full_name':'مشرف مباشر','username':'direct_supervisor','role':'supervisor','email':''})
    assert made.status_code==200,made.text
    assert made.json()['temporary_password']
    duplicate=owner.post('/api/access/mosques/1/users',json={
        'full_name':'مشرف آخر','username':'direct_supervisor','role':'supervisor','email':''})
    assert duplicate.status_code==409


def test_teacher_and_guardian_scopes_stay_private(network):
    t1,t2=network['teachers']
    s1,s2=network['students']
    sid1,sid2=network['ids']
    assert t1.get(f'/api/halaqat/mosques/1/students/{sid1}/file').status_code==200
    assert t1.get(f'/api/halaqat/mosques/1/students/{sid2}/file').status_code==404
    assert s1.get(f'/api/halaqat/mosques/1/students/{sid1}/file').status_code==200
    assert s1.get(f'/api/halaqat/mosques/1/students/{sid2}/file').status_code==404
    assert s2.get(f'/api/halaqat/mosques/1/students/{sid1}/file').status_code==404


def test_supervisor_transfer_requires_owner_approval(network):
    owner=network['owner'];sup=network['supervisors'][0]
    sid=network['ids'][0];old_ring=network['rings'][0];new_ring=network['rings'][1]
    requested=sup.post(f'/api/halaqat/mosques/1/students/{sid}/transfer',json={'halaqa_id':new_ring})
    assert requested.status_code==200,requested.text
    assert requested.json()['pending_approval'] is True
    with SessionLocal() as db:
        assert db.get(HalaqaStudent,sid).halaqa_id==old_ring
    qid=requested.json()['request_id']
    approved=owner.post(f'/api/access/mosques/1/change-requests/{qid}/approve',json={'note':'تمت المراجعة'})
    assert approved.status_code==200,approved.text
    with SessionLocal() as db:
        assert db.get(HalaqaStudent,sid).halaqa_id==new_ring


def test_supervisor_ring_change_waits_for_approval(network):
    owner=network['owner'];sup=network['supervisors'][0];rid=network['rings'][0]
    with SessionLocal() as db:
        old=db.get(Halaqa,rid).name
    req=sup.post('/api/access/mosques/1/change-requests',json={
        'action_type':'ring_update','ring_id':rid,'name':old+' المعدلة','schedule':'بعد المغرب','reason':'تعديل تنظيمي'})
    assert req.status_code==200,req.text
    with SessionLocal() as db:
        assert db.get(Halaqa,rid).name==old
    qid=req.json()['request']['id']
    assert owner.post(f'/api/access/mosques/1/change-requests/{qid}/reject',json={'note':'غير مناسب'}).status_code==200
    with SessionLocal() as db:
        assert db.get(Halaqa,rid).name==old

def test_server_blocks_direct_admin_urls(network):
    supervisor=network['supervisors'][0]
    teacher=network['teachers'][0]
    payload={'full_name':'مستخدم غير مصرح','username':'blocked_user','role':'teacher','email':''}
    assert supervisor.post('/api/access/mosques/1/users',json=payload).status_code==403
    assert teacher.get('/api/access/mosques/1/overview').status_code==403
