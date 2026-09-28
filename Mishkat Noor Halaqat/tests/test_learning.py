from datetime import timedelta
from sqlalchemy import select,func
from app.api.student_file import today
from app.db.session import SessionLocal
from app.models import *
B='/api/halaqat/mosques/1'

def test_completion_goal_math_and_permissions(network):
    n=network;url=B+f'/students/{n["ids"][0]}';d={'title':'ختم جزء','target':20,'completed':6,'unit':'page','start':str(today()),'deadline':str(today()+timedelta(days=13))}
    assert n['students'][0].put(url+'/completion-goal',json=d).status_code==403
    assert n['teachers'][1].put(url+'/completion-goal',json=d).status_code==404
    assert n['teachers'][0].put(url+'/completion-goal',json=d).status_code==200
    g=n['students'][0].get(url+'/learning').json()['goal'];assert g['remaining']==14 and g['weekly']==7 and g['percent']==30
    assert n['teachers'][0].put(url+'/completion-goal',json=d|{'completed':21}).status_code==422
    assert n['teachers'][0].put(url+'/completion-goal',json=d|{'unit':'ayah','target':20.5}).status_code==422
    assert n['teachers'][0].put(url+'/completion-goal',json=d|{'start':str(today()-timedelta(days=3)),'deadline':str(today()-timedelta(days=1))}).status_code==200
    assert n['students'][0].get(url+'/learning').json()['goal']['overdue'] is True


def test_mistakes_reference_repetition_resolution(network):
    n=network;url=B+f'/students/{n["ids"][0]}';t=n['teachers'][0]
    d={'day':str(today()),'surah':1,'ayah':7,'kind':'tajweed','notes':'مد'}
    assert t.post(url+'/mistakes',json=d|{'ayah':8}).status_code==422
    assert t.post(url+'/mistakes',json=d|{'day':str(today()+timedelta(days=1))}).status_code==422
    ids=[t.post(url+'/mistakes',json=d).json()['id'] for _ in range(2)]
    assert all(x['repetitions']==2 for x in n['students'][0].get(url+'/learning').json()['mistakes'])
    assert t.put(url+f'/mistakes/{ids[0]}',json=d|{'resolved':True}).status_code==200
    assert n['students'][0].put(url+f'/mistakes/{ids[0]}',json=d).status_code==403
    assert n['students'][1].get(url+'/learning').status_code==404


def test_guardian_confirmation_separate_and_idempotent(network):
    n=network;sid=n['ids'][0];url=B+f'/students/{sid}';o=n['owner'];t=n['teachers'][0];parent=n['students'][0]
    aid=t.post(url+'/assignments',json={'due':str(today()),'memorization':'الفاتحة'}).json()['id']
    p={'assignment_id':aid,'day':str(today()),'minutes':20,'notes':'راجعت معه'}
    assert t.post(url+'/home-practice',json=p).status_code==403
    assert parent.post(url+'/home-practice',json=p).status_code==200
    assert parent.post(url+'/home-practice',json=p|{'minutes':25}).status_code==200
    assert len(t.get(url+'/learning').json()['home'])==1
    assert t.get(url+'/learning').json()['home'][0]['minutes']==25
    with SessionLocal() as db:
        assert db.get(Assignment,aid).status=='pending'
        assert db.scalar(select(func.count(HalaqaProgress.id)).where(HalaqaProgress.student_id==sid))==0
        uid=db.get(HalaqaStudent,sid).user_id;db.get(User,uid).account_type='student';db.get(HalaqaStudent,sid).recipient_type='student';db.commit()
    assert parent.post(url+'/home-practice',json=p).status_code==403


def test_queue_privacy_and_stale_next(network):
    n=network;rid=n['rings'][0];sid=n['ids'][0];o=n['owner'];t=n['teachers'][0];url=B+f'/rings/{rid}/queue'
    # Include another family in the same circle, without granting visibility to its file.
    with SessionLocal() as db:
        s=HalaqaStudent(halaqa_id=rid,full_name='طالب آخر');db.add(s);db.commit();other=s.id
    p={'day':str(today()),'student_ids':[sid,other]}
    assert n['students'][0].put(url,json=p).status_code==403
    assert t.put(url,json=p).status_code==200
    mine=n['students'][0].get(url,params={'day':str(today())}).json();assert len(mine['rows'])==1 and mine['current_id'] is None
    current=t.get(url,params={'day':str(today())}).json()['current_id']
    assert t.post(url+'/next',json={'day':str(today()),'current_id':current}).status_code==200
    assert t.post(url+'/next',json={'day':str(today()),'current_id':current}).status_code==409
    assert t.put(url,json=p).status_code==409
    assert t.put(url,json=p|{'reset':True,'student_ids':[sid,sid]}).status_code==422
    assert n['teachers'][1].get(url,params={'day':str(today())}).status_code==404


def test_substitute_start_expiry_revoke_and_cross_mosque(network):
    n=network;o=n['owner'];t=n['teachers'][1];rid=n['rings'][0];sid=n['ids'][0];path=B+f'/rings/{rid}/substitutes';url=B+f'/students/{sid}/file'
    uid=t.get('/api/halaqat/context').json()['user']['id']
    p={'user_id':uid,'start':str(today()+timedelta(days=1)),'end':str(today()+timedelta(days=2))}
    assert o.post(path,json=p).status_code==200
    assert t.get(url).status_code==404
    assert o.post(path,json=p).status_code==409
    with SessionLocal() as db:
        sub=db.scalar(select(SubstituteTeacher));sub.start=today();sub.end=today();db.commit();tid=sub.id
    assert t.get(url).status_code==200
    with SessionLocal() as db:
        sub=db.get(SubstituteTeacher,tid);sub.start=today()-timedelta(days=2);sub.end=today()-timedelta(days=1);db.commit()
    assert t.get(url).status_code==404
    assert o.post(path,json=p|{'start':str(today()),'end':str(today())}).status_code==200
    tid=o.get(B+'/learning-dashboard').json()['substitutes'][-1]['id'];assert n['supervisors'][0].delete(path+'/'+str(tid)).status_code==200
    assert t.get(url).status_code==404
    mid=o.post('/api/halaqat/organizations',json={'name':'مسجد مستقل'}).json()['id']
    assert o.post(f'/api/halaqat/mosques/{mid}/roster/import',json={'reviewed':True,'groups':[{'name':'حلقة مستقلة','teacher_name':'مدرس مستقل','students':['طالب مستقل']}]}).status_code==200
    other=o.get(f'/api/halaqat/mosques/{mid}/dashboard').json()['rings'][0]['id']
    assert o.post(f'/api/halaqat/mosques/{mid}/rings/{other}/substitutes',json=p).status_code==422


def test_term_report_keeps_units_and_no_data_null(network):
    n=network;sid=n['ids'][0];url=B+f'/students/{sid}';t=n['teachers'][0]
    assert t.post(url+'/progress',json={'day':str(today()),'memorized_amount':2,'memorized_unit':'page','memorization_score':9,'tajweed_score':8}).status_code==200
    assert t.post(url+'/progress',json={'day':str(today()-timedelta(days=1)),'memorized_amount':7,'memorized_unit':'ayah','memorization_score':5,'tajweed_score':6}).status_code==200
    r=n['students'][0].get(url+'/term-report',params={'start':str(today()),'end':str(today())}).json()
    assert r['current']['memorized_pages']==2 and r['current']['memorized_ayahs']==0
    assert r['previous']['memorized_ayahs']==7 and r['current']['tajweed_score']==8 and r['previous']['tajweed_score']==6
    assert n['students'][1].get(url+'/term-report',params={'start':str(today()),'end':str(today())}).status_code==404
    r=t.get(url+'/term-report',params={'start':str(today()-timedelta(days=10)),'end':str(today()-timedelta(days=9))}).json();assert r['current']['attendance_percent'] is None


def test_competition_review_awards_and_atomic_scope(network):
    n=network;o=n['owner'];t=n['teachers'][0];sup=n['supervisors'][0];sid=n['ids'][0];rid=n['rings'][0]
    p={'halaqa_id':rid,'title':'مسابقة مراجعة','mode':'team','unit':'وجه','target':10,'start':str(today()),'end':str(today()),'student_ids':[sid],'reward':'شهادة تقدير'}
    assert t.post(B+'/competitions',json=p).status_code==403
    assert o.post(B+'/competitions',json=p|{'student_ids':[n['ids'][1]]}).status_code==422
    cid=sup.post(B+'/competitions',json=p).json()['id'];eid=t.get(B+'/competitions').json()['competitions'][0]['entries'][0]['id'];url=B+f'/competitions/{cid}'
    assert t.put(url+f'/entries/{eid}',json={'value':12}).status_code==200
    assert t.put(url+f'/entries/{eid}/review',json={'status':'approved'}).status_code==403
    assert sup.put(url+'/award',json={'awarded':True}).status_code==409
    assert sup.put(url+f'/entries/{eid}/review',json={'status':'approved'}).status_code==200
    assert sup.put(url+'/award',json={'awarded':True}).status_code==200
    assert sup.put(url+'/award',json={'awarded':True}).status_code==200
    mine=n['students'][0].get(B+'/competitions').json()['competitions'][0];assert mine['team_total']==12 and mine['entries'][0]['awarded'] is True
    assert n['students'][1].get(B+'/competitions').json()['competitions']==[]
    assert t.put(url+f'/entries/{eid}',json={'value':13}).status_code==409
    assert sup.put(url+'/award',json={'awarded':False}).status_code==200
    assert t.put(url+f'/entries/{eid}',json={'value':13}).status_code==200


def test_missing_data_and_full_delete_new_dependencies(network):
    n=network;o=n['owner'];rid=n['rings'][0];sid=n['ids'][0];url=B+f'/students/{sid}'
    m=o.get(B+'/learning-dashboard').json()['missing'];assert sid not in [x['student_id'] for x in m]
    assert n['students'][0].get(B+'/learning-dashboard').json()['missing']==[]
    assert o.put(url+'/profile',json={'full_name':'طالب مكتمل','guardian_name':'ولي الطالب','guardian_phone':'0500000000'}).status_code==200
    assert sid not in [x['student_id'] for x in o.get(B+'/learning-dashboard').json()['missing']]
    from app.models import HalaqaStudent
    # Optional demographics stay empty without making the file incomplete.
    saved=o.get(url+'/file').json()['student']
    assert saved['birth_date'] is None and not saved['national_id'] and not saved['school_grade']
    with SessionLocal() as db:
        student=db.get(HalaqaStudent,sid)
        student.recipient_type='student';student.guardian_phone=''
        db.commit()
    assert sid not in [x['student_id'] for x in o.get(B+'/learning-dashboard').json()['missing']]
    assert o.post(B+'/competitions',json={'halaqa_id':rid,'title':'مسابقة حذف','mode':'individual','unit':'نقطة','target':1,'start':str(today()),'end':str(today()),'student_ids':[sid]}).status_code==200
    assert o.put(B+f'/rings/{rid}/queue',json={'day':str(today()),'student_ids':[sid]}).status_code==200
    # Transfer the participant away; deleting the old ring must clean ring-owned dependencies only.
    assert o.post(url+'/transfer',json={'halaqa_id':n['rings'][1]}).status_code==200
    pre=o.get(B+f'/rings/{rid}/deletion-preview').json()
    r=o.request('DELETE',B+f'/rings/{rid}',json={'confirm_name':pre['name'],'token':pre['token']});assert r.status_code==200,r.text
    assert o.get(url+'/file').status_code==200
    with SessionLocal() as db:
        assert db.scalar(select(func.count(CompetitionEntry.id)))==0
        assert db.scalar(select(func.count(RecitationTurn.id)))==0
