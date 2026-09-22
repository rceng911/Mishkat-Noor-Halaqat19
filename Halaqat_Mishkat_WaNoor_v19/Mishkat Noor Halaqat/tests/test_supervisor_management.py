from sqlalchemy import select
from app.models import User,Halaqa,HalaqaStudent,HalaqaSupervisor,AuthSession
from app.db.session import SessionLocal
B='/api/halaqat/mosques/1'

def test_supervisor_sees_unassigned_and_imported_circles_but_not_other_mosques(network):
    n=network;o=n['owner'];sup=n['supervisors'][0]
    payload={'reviewed':True,'groups':[{'name':'حلقة دون تكليف','teacher_name':'مدرس مستورد','students':['طالب مستورد جديد']}]}
    assert o.post(B+'/roster/import',json=payload).status_code==200
    dash=sup.get(B+'/dashboard').json();assert len(dash['rings'])==3 and len(dash['students'])==3
    assert dash['requests']==o.get(B+'/dashboard').json()['requests']
    assert all('teachers' in r for r in dash['rings'])
    for s in dash['students']:
        assert sup.get(B+f'/students/{s["id"]}/file').status_code==200
        assert sup.get(B+f'/students/{s["id"]}/followup').status_code==200
    mid=o.post('/api/halaqat/organizations',json={'name':'مسجد مستقل'}).json()['id'];other=f'/api/halaqat/mosques/{mid}'
    assert o.post(other+'/roster/import',json={'reviewed':True,'groups':[{'name':'خاصة','teacher_name':'معلم آخر','students':['طالب مسجد آخر']}]}).status_code==200
    sid=o.get(other+'/dashboard').json()['students'][0]['id']
    assert sup.get(other+'/dashboard').status_code==403
    assert sup.get(other+f'/students/{sid}/file').status_code==403
    assert sup.get(B+f'/students/{sid}/file').status_code==404
    q=next(x for x in dash['requests'] if x['status']=='pending')
    assert sup.post(B+f'/requests/{q["id"]}/approve',json={}).status_code==403


def test_owner_edits_removes_supervisor_and_preserves_history(network):
    n=network;o=n['owner'];sup=n['supervisors'][0];other_sup=n['supervisors'][1]
    uid=sup.get('/api/halaqat/context').json()['user']['id'];path=B+f'/supervisors/{uid}'
    data={'full_name':'مشرف معدل','username':'supervisor_edited','phone':'0501234567','email':'edited@example.test','notes':'مشرف عام'}
    assert sup.put(path+'/profile',json=data).status_code==403
    assert o.put(path+'/profile',headers={'X-Portal-View':'supervisor'},json=data).status_code==403
    assert o.put(path+'/profile',json=data).status_code==200
    assert sup.get('/api/halaqat/context').status_code==401
    assert sup.post('/login',data={'identity':'supervisor_edited','password':'NewPass1@abc'},follow_redirects=False).status_code==303
    assert sup.get(B+'/dashboard').json()['user']['name']=='مشرف معدل'
    assert o.request('DELETE',path,json={'confirm_name':'غير مطابق'}).status_code==422
    assert other_sup.request('DELETE',path,json={'confirm_name':data['full_name']}).status_code==403
    assert o.request('DELETE',path,json={'confirm_name':data['full_name']}).status_code==200
    assert sup.get('/api/halaqat/context').status_code==401
    assert sup.post('/login',data={'identity':'supervisor_edited','password':'NewPass1@abc'},follow_redirects=False).status_code!=303
    with SessionLocal() as db:
        assert not db.get(User,uid).active
        assert not db.scalar(select(AuthSession.id).where(AuthSession.user_id==uid))
        assert not db.scalar(select(HalaqaSupervisor.id).where(HalaqaSupervisor.user_id==uid,HalaqaSupervisor.active.is_(True)))
        assert not db.scalar(select(Halaqa.id).where(Halaqa.supervisor_id==uid))
        assert db.get(HalaqaStudent,n['ids'][0]) is not None
    assert len(other_sup.get(B+'/dashboard').json()['students'])==2
    assert o.request('DELETE',B+f'/supervisors/{o.get("/api/halaqat/context").json()["user"]["id"]}',json={'confirm_name':'مالك الاختبار'}).status_code==404
