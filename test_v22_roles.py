from app.db.session import SessionLocal
from app.models import HalaqaStudent


def test_ring_metrics_and_alphabetical_students(network):
    owner = network['owner']
    d = owner.get('/api/halaqat/mosques/1/dashboard').json()
    assert all('completion_rate' in r and 'absence_rate' in r for r in d['rings'])
    names = [s['name'] for s in d['students']]
    assert names == sorted(names, key=str.casefold)
    assert all('absences_30_days' in s and 'repeated_notes' in s and 'low_rating' in s for s in d['students'])


def test_supervisor_can_edit_student_profile(network):
    sid = network['ids'][0]
    sup = network['supervisors'][0]
    payload = {
        'full_name':'طالب 1','guardian_name':'ولي 1','guardian_phone':'0500000000',
        'guardian_relation':'الأب','national_id':'1234567890','birth_date':'2012-01-01',
        'school_grade':'الأول متوسط','current_memorization':'النبأ','notes':'ملاحظة إدارية'
    }
    r = sup.put(f'/api/halaqat/mosques/1/students/{sid}/profile', json=payload)
    assert r.status_code == 200, r.text


def test_roster_print_and_csv_are_scoped(network):
    owner = network['owner']; teacher = network['teachers'][0]; rid = network['rings'][0]
    r = owner.get(f'/api/halaqat/mosques/1/rings/{rid}/roster')
    assert r.status_code == 200 and 'طباعة الكشف' in r.text
    r = owner.get(f'/api/halaqat/mosques/1/rings/{rid}/roster.csv')
    assert r.status_code == 200 and 'اسم الطالب' in r.text
    assert teacher.get(f'/api/halaqat/mosques/1/rings/{rid}/roster').status_code == 403


def test_supervisor_can_permanently_delete_student(network):
    sid = network['ids'][0]
    sup = network['supervisors'][0]
    preview = sup.get(f'/api/halaqat/mosques/1/students/{sid}/deletion-preview')
    assert preview.status_code == 200, preview.text
    p = preview.json()
    deleted = sup.request('DELETE', f'/api/halaqat/mosques/1/students/{sid}', json={'confirm_name':p['name'],'token':p['token']})
    assert deleted.status_code == 200, deleted.text
    with SessionLocal() as db:
        assert db.get(HalaqaStudent, sid) is None


def test_owner_ui_no_student_impersonation_option(owner):
    js = owner.get('/static/halaqat.js').text
    assert "['student','ملفي كطالب']" not in js
