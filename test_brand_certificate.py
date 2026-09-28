from app.db.session import SessionLocal
from app.models import HalaqaStudent
from sqlalchemy import create_engine, text, inspect
from app.db.migrations import ensure_v10_schema

B='/api/halaqat/mosques/1'

def test_branded_certificate_snapshot_and_permissions(network):
    n=network; owner=n['owner']; sid=n['ids'][0]; url=f'{B}/students/{sid}/certificates'
    with SessionLocal() as db:
        s=db.get(HalaqaStudent,sid);s.national_id='1234567890';db.commit()
    payload={'title':'شهادة إتمام حفظ','memorization_scope':'جزء عم','mastery_percent':97.5}
    assert n['students'][0].post(url,json=payload).status_code==403
    assert owner.post(url,json=payload|{'mastery_percent':101}).status_code==422
    assert owner.post(url,json=payload|{'mastery_percent':None}).status_code==422
    r=owner.post(url,json=payload);assert r.status_code==200,r.text
    page=url+'/'+str(r.json()['id'])
    assert n['students'][1].get(page).status_code==404
    with SessionLocal() as db:
        s=db.get(HalaqaStudent,sid);s.full_name='اسم معدل';s.national_id='9876543210';db.commit()
    html=n['students'][0].get(page).text
    for expected in ['brand-logo.png','حلقات جامع عبدالمحسن عبدالله العثيم','جزء عم','97.5%','1234567890','طالب 1']:
        assert expected in html
    assert '9876543210' not in html
    # Legacy clients and old certificates remain readable.
    old=owner.post(url,json={'title':'شهادة قديمة','achievement':'حفظ سورة الفاتحة'})
    assert old.status_code==200
    assert 'حفظ سورة الفاتحة' in owner.get(url+'/'+str(old.json()['id'])).text
    dashboard=owner.get(B+'/dashboard').json()
    assert next(s for s in dashboard['students'] if s['id']==sid)['has_national_id'] is True
    assert 'national_id' not in dashboard['students'][0]


def test_certificate_columns_upgrade_is_repeatable():
    e=create_engine('sqlite://')
    with e.begin() as c:
        c.execute(text('CREATE TABLE student_certificates (id INTEGER PRIMARY KEY, achievement TEXT)'))
        c.execute(text("INSERT INTO student_certificates VALUES (1, 'existing')"))
    ensure_v10_schema(e);ensure_v10_schema(e)
    with e.connect() as c:
        assert c.execute(text('SELECT achievement FROM student_certificates')).scalar()=='existing'
        assert {'memorization_scope','mastery_percent','student_name','student_national_id'} <= {x['name'] for x in inspect(c).get_columns('student_certificates')}
    e.dispose()
