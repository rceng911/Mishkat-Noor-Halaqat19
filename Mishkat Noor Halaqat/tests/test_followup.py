from datetime import timedelta
from pathlib import Path
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import HalaqaStudent, User
from app.api.student_file import today
BASE = "/api/halaqat/mosques/1"


def requested(n, **kw):
    payload={'full_name':'طالب جديد','halaqa_id':n['rings'][0], 'recipient_type':'student'}|kw
    r=n['teachers'][0].post(BASE+'/requests/student',json=payload)
    assert r.status_code==200,r.text
    return r.json()['request'],payload


def test_return_resubmit_owner_views_and_self_account(network):
    n=network;o=n['owner'];req,p=requested(n,full_name='محمد الطالب')
    url=BASE+f'/requests/{req["id"]}'
    assert n['teachers'][0].post(url+'/return',json={'note':'أكمل الصف'}).status_code==403
    assert o.post(url+'/return',json={'note':'أكمل الصف'}).status_code==200
    assert o.post(url+'/approve',json={}).status_code==409
    assert n['teachers'][1].put(url,json=p).status_code==403
    assert n['teachers'][0].put(url,json=p|{'school_grade':'الجامعة'}).status_code==200
    uid=o.get('/api/halaqat/context').json()['user']['id']
    r=o.post(url+'/approve',json={'existing_user_id':uid}); assert r.status_code==200,r.text
    own_student=o.get(BASE+'/dashboard',headers={'X-Portal-View':'student'}).json()
    assert own_student['user']['role']=='halaqa_student'
    assert len(own_student['students'])==1 and own_student['students'][0]['name']=='محمد الطالب'
    sid=own_student['students'][0]['id']
    assert o.get(BASE+f'/students/{n["ids"][0]}/file',headers={'X-Portal-View':'student'}).status_code==404
    assert o.put(BASE+f'/students/{sid}/plan',headers={'X-Portal-View':'student'},json={}).status_code==403
    assert o.get(BASE+f'/students/{n["ids"][0]}/file?view=student').status_code==404
    assert o.post(BASE+'/supervisors',headers={'X-Portal-View':'supervisor'},json={'full_name':'غير مسموح','username':'ممنوع'}).status_code==403
    assert len(o.get(BASE+'/dashboard',headers={'X-Portal-View':'supervisor'}).json()['students'])==3
    assert o.get(BASE+f'/students/{sid}/file',headers={'X-Portal-View':'supervisor'}).json()['can_edit']
    req,_=requested(n)
    assert o.post(BASE+f'/requests/{req["id"]}/approve',json={'existing_user_id':uid}).status_code==422
    # An ordinary user's view header never elevates their role.
    assert n['students'][0].get(BASE+'/dashboard',headers={'X-Portal-View':'supervisor'}).json()['user']['role']=='halaqa_student'


def test_relink_family_new_credentials_and_profile(network):
    n=network;o=n['owner'];sid=n['ids'][0];url=BASE+f'/students/{sid}'
    uid=n['students'][1].get('/api/halaqat/context').json()['user']['id']
    assert n['teachers'][0].put(url+'/recipient',json={'user_id':uid,'recipient_type':'guardian'}).status_code==403
    assert o.put(url+'/recipient',json={'user_id':uid,'recipient_type':'guardian'}).status_code==200
    assert n['students'][0].get(url+'/file').status_code==404
    assert n['students'][1].get(url+'/file').status_code==200
    assert len(n['students'][1].get(BASE+'/dashboard').json()['students'])==2
    assert o.put(url+'/recipient',json={'user_id':uid,'recipient_type':'student'}).status_code==422
    assert n['teachers'][0].put(url+'/profile',json={'full_name':'الاسم المصحح','guardian_name':'ولي جديد','school_grade':'الخامس'}).status_code==200
    assert n['students'][1].get(url+'/file').json()['student']['name']=='الاسم المصحح'
    assert n['students'][1].put(url+'/profile',json={'full_name':'تغيير'}).status_code==403
    created=o.post(url+'/recipient-account',json={'recipient_type':'student','full_name':'الاسم المصحح','username':'حساب_ذاتي','temporary_password':'SelfAccount1@'})
    assert created.status_code==200,created.text
    assert created.json()['user']['account_type']=='student'
    assert n['students'][1].get(url+'/file').status_code==404
    assert n['teachers'][0].post(url+'/recipient-account',json={'recipient_type':'student','full_name':'طالب','username':'رفض'}).status_code==403


def test_transfer_preserves_history(network):
    n=network;sid=n['ids'][0];url=BASE+f'/students/{sid}'
    assert n['teachers'][0].post(url+'/progress',json={'day':today().isoformat(),'memorized':'الفاتحة','memorized_amount':1}).status_code==200
    assert n['supervisors'][0].post(url+'/transfer',json={'halaqa_id':n['rings'][1]}).status_code==200
    assert n['owner'].post(url+'/transfer',json={'halaqa_id':n['rings'][1]}).status_code==200
    assert n['teachers'][0].get(url+'/file').status_code==404
    assert n['teachers'][1].get(url+'/file').json()['progress'][0]['memorized']=='الفاتحة'
    assert n['students'][0].get(url+'/file').status_code==200


def test_batch_atomic_and_preserves_recitation(network):
    n=network;t=n['teachers'][0];sid=n['ids'][0];url=BASE+f'/students/{sid}'
    batch={'day':today().isoformat(),'rows':[{'student_id':sid,'attendance':'present'},{'student_id':n['ids'][1],'attendance':'present'}]}
    assert t.post(BASE+'/attendance/batch',json=batch).status_code==404
    assert t.get(url+'/file').json()['progress']==[]
    assert n['owner'].post(BASE+'/attendance/batch',json=batch).status_code==200
    assert t.post(url+'/progress',json={'day':today().isoformat(),'memorized':'سورة الناس','memorized_amount':1,'memorization_score':9}).status_code==200
    assert n['owner'].post(BASE+'/attendance/batch',json=batch).status_code==200
    assert t.get(url+'/file').json()['progress'][0]['memorization_score']==9
    batch['rows'][0]['attendance']='absent'
    assert n['owner'].post(BASE+'/attendance/batch',json=batch).status_code==409
    assert t.get(url+'/file').json()['progress'][0]['attendance']=='present'


def test_wards_rewards_notifications_pdf_and_flags(network,tmp_path):
    n=network;t=n['teachers'][0];s=n['students'][0];o=n['owner'];sid=n['ids'][0];url=BASE+f'/students/{sid}'
    day=today().isoformat()
    assert t.put(url+'/plan',json={'memorization_amount':1,'revision_amount':2,'sessions_per_week':1}).status_code==200
    assert t.post(url+'/progress',json={'day':day,'memorized':'سورة الفاتحة','memorized_amount':1,'revision_amount':1}).status_code==200
    ward={'due':day,'memorization':'البقرة من الآية 1 إلى 5','revision':'سورة الفاتحة','instructions':'الاهتمام بالتجويد'}
    assert s.post(url+'/assignments',json=ward).status_code==403
    r=t.post(url+'/assignments',json=ward);assert r.status_code==200,r.text
    aid=r.json()['id']
    assert n['teachers'][1].put(url+f'/assignments/{aid}',json={'status':'completed'}).status_code==404
    for _ in range(2): assert t.put(url+f'/assignments/{aid}',json={'status':'completed'}).status_code==200
    follow=s.get(url+'/followup').json();assert follow['rewards']['points']==7
    assert 'حقق هدف الحفظ الأسبوعي' in follow['rewards']['badges']
    assert t.post(url+'/exam-appointments',json={'due':day,'title':'اختبار جزء عم'}).status_code==200
    mon=s.get(BASE+'/monitor').json()
    assert any('اختبار' in a['message'] for a in mon['alerts'])
    assert any('المراجعة أقل' in a['message'] for a in mon['alerts'])
    key=mon['alerts'][0]['key']
    assert n['students'][1].post(BASE+'/alerts/read',json={'key':key}).status_code==404
    assert s.post(BASE+'/alerts/read',json={'key':key}).status_code==200
    assert next(a for a in s.get(BASE+'/monitor').json()['alerts'] if a['key']==key)['read']
    pdf=s.get(url+'/monthly.pdf?month='+day[:7]);assert pdf.status_code==200,pdf.text[:100] if pdf.status_code!=200 else ''
    assert pdf.content.startswith(b'%PDF')
    assert n['students'][1].get(url+'/monthly.pdf?month='+day[:7]).status_code==404
    assert s.get(url+'/monthly.pdf?month=bad').status_code==422
    Path('/tmp/halaqat14-sample.pdf').write_bytes(pdf.content)
    flags=dict.fromkeys(['assignments','notifications','rewards','monthly_reports'],False)
    assert t.put(BASE+'/features',json=flags).status_code==403
    assert o.put(BASE+'/features',json=flags).status_code==200
    assert s.get(url+'/followup').json()['rewards'] is None
    assert s.get(BASE+'/monitor').json()['alerts']==[]
    assert t.post(url+'/assignments',json=ward).status_code==403
    assert s.get(url+'/monthly.pdf?month='+day[:7]).status_code==403
