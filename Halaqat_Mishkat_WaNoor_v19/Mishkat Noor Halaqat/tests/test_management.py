from datetime import timedelta
from sqlalchemy import select,func
from app.models import *
from app.db.session import SessionLocal
from app.api.student_file import today
B='/api/halaqat/mosques/1'

def test_ring_edit_and_teacher_permissions(network):
    n=network;o=n['owner'];rid=n['rings'][0]
    ds=o.get(B+'/dashboard').json();t=next(a for a in ds['accounts'] if a['role']=='halaqa_teacher');sup=ds['supervisors'][0]
    payload={'name':'حلقة معدلة','schedule':'بعد العصر','teacher_ids':[t['id']],'supervisor_ids':[sup['id']]}
    assert n['teachers'][0].put(B+f'/rings/{rid}',json=payload).status_code==403
    assert o.put(B+f'/rings/{rid}',headers={'X-Portal-View':'student'},json=payload).status_code==403
    assert o.put(B+f'/rings/{rid}',json=payload).status_code==200
    assert o.get(B+'/dashboard').json()['rings'][0]['name']=='حلقة معدلة'
    assert o.put(B+f'/rings/{rid}',json=payload|{'teacher_ids':[sup['id']]}).status_code==422
    assert o.put(B+f'/teachers/{t["id"]}/profile',json={'full_name':'مدرس بعد التعديل','email':'teacher@example.test','phone':'0500000000','notes':'ملاحظة'}).status_code==200
    assert n['teachers'][0].get('/api/halaqat/context').json()['user']['name']=='مدرس بعد التعديل'
    assert n['students'][0].get(B+'/teachers/manage').status_code==403
    # Removed assignment revokes teacher file access immediately, without deleting the account.
    assert o.put(B+f'/rings/{rid}',json=payload|{'teacher_ids':[]}).status_code==200
    assert n['teachers'][0].get(B+f'/students/{n["ids"][0]}/file').status_code==404


def test_bulk_roster_identity_and_no_auto_accounts(owner):
    payload={'reviewed':True,'groups':[{'name':f'حلقة جديدة {i}','teacher_name':f'مدرس جديد {i}','students':[f'طالب مستورد {i}']} for i in range(1,4)]}
    assert owner.post(B+'/roster/import',json=payload|{'reviewed':False}).status_code==422
    assert owner.post(B+'/roster/import',json=payload).json()['students']==3
    assert owner.post(B+'/roster/import',json=payload).status_code==409
    dash=owner.get(B+'/dashboard').json();assert len(dash['students'])==3 and len(dash['requests'])==3 and dash['accounts']==[]
    q=dash['requests'][0];assert owner.put(B+f'/teacher-requests/{q["id"]}',json={'full_name':'اسم مدرس مصحح'}).status_code==200
    s=dash['students'][0];sid=s['id'];url=B+f'/students/{sid}'
    assert s['user_id'] is None and s['birth_date'] is None
    assert owner.put(url+'/profile',json={'full_name':s['name'],'national_id':'١٢٣٤٥٦٧٨٩٠','birth_date':'2010-01-01'}).status_code==200
    assert owner.get(url+'/file').json()['student']['national_id']=='١٢٣٤٥٦٧٨٩٠'
    assert owner.put(url+'/profile',json={'full_name':s['name']}).status_code==200
    assert owner.get(url+'/file').json()['student']['national_id']=='١٢٣٤٥٦٧٨٩٠'
    assert owner.put(url+'/profile',json={'full_name':s['name'],'national_id':'bad'}).status_code==422
    assert owner.get(B+'/roster/source').status_code==200
    result=owner.post(url+'/recipient-account',json={'full_name':'ولي أمر الطالب','recipient_type':'guardian','username':'parent_import'})
    # The existing owner workflow issues credentials only when requested.
    assert result.status_code==200,result.text


def test_complete_ring_deletion_with_history_and_preview_guard(network):
    n=network;o=n['owner'];rid=n['rings'][0];sid=n['ids'][0];url=B+f'/students/{sid}'
    assert o.post(url+'/progress',json={'day':str(today()),'attendance':'present'}).status_code==200
    assert o.put(url+'/quran/1',json={'status':'memorized'}).status_code==200
    assert n['students'][0].post(url+'/messages',json={'body':'رسالة'}).status_code==200
    eid=o.post(url+'/organized-exams',json={'title':'اختبار حذف','syllabus':'الفاتحة','due':str(today()),'repeat_days':7,'criteria':[{'name':'الحفظ','maximum':100}]}).json()['id']
    r=o.put(url+f'/organized-exams/{eid}/result',json={'day':str(today()),'scores':[100]});assert r.status_code==200,r.text
    assert o.put(B+f'/rings/{rid}/calendar',json={'weekdays':[0]}).status_code==200
    assert o.post(B+'/announcements',json={'halaqa_id':rid,'title':'إعلان الحلقة','body':'نص'}).status_code==200
    preview=o.get(B+f'/rings/{rid}/deletion-preview').json()
    assert preview['counts']['students']==1
    assert n['supervisors'][0].get(B+f'/rings/{rid}/deletion-preview').status_code==403
    args={'confirm_name':preview['name'],'token':preview['token']}
    assert o.request('DELETE',B+f'/rings/{rid}',json=args|{'confirm_name':'خطأ'}).status_code==422
    assert o.put(url+'/quran/2',json={'status':'in_progress'}).status_code==200
    assert o.request('DELETE',B+f'/rings/{rid}',json=args).status_code==409
    args['token']=o.get(B+f'/rings/{rid}/deletion-preview').json()['token']
    r=o.request('DELETE',B+f'/rings/{rid}',json=args);assert r.status_code==200,r.text
    assert o.get(url+'/file').status_code==404
    assert n['students'][1].get(B+f'/students/{n["ids"][1]}/file').status_code==200
    with SessionLocal() as db:
        assert db.get(Halaqa,rid) is None
        assert db.scalar(select(func.count(OrganizedResult.exam_id)))==0
        assert db.scalar(select(func.count(OrganizedExam.id)))==0
        assert db.scalar(select(func.count(User.id)))==7
        assert db.scalar(select(AuditLog.id).where(AuditLog.action=='ring_deleted'))
