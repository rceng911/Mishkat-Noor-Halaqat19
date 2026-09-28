from app.db.session import SessionLocal
from app.models import HalaqaStudent, User
B='/api/halaqat/mosques/1'

def test_only_unissued_accounts_are_missing(network):
    n=network;sid=n['ids'][0];owner=n['owner']
    assert owner.get(B+'/learning-dashboard').json()['missing']==[]
    with SessionLocal() as db:
        s=db.get(HalaqaStudent,sid);uid=s.user_id;s.user_id=None;db.commit()
    missing=owner.get(B+'/learning-dashboard').json()['missing']
    assert len(missing)==1 and missing[0]['student_id']==sid
    assert missing[0]['fields']==['لم يُصدر حساب باسم مستخدم']
    assert n['students'][1].get(B+'/learning-dashboard').json()['missing']==[]
    with SessionLocal() as db:
        s=db.get(HalaqaStudent,sid);s.user_id=uid;db.get(User,uid).active=False;db.commit()
    assert owner.get(B+'/learning-dashboard').json()['missing']==[]


def test_circle_announcements_scope(network):
    n=network;sup=n['supervisors'][0]
    payload={'halaqa_id':n['rings'][0],'title':'موعد الحلقة','body':'يبدأ اللقاء بعد العصر'}
    assert sup.post(B+'/announcements',json=payload).status_code==200
    assert n['teachers'][0].post(B+'/announcements',json=payload|{'halaqa_id':n['rings'][1]}).status_code in (403,404)
    result=sup.get(B+'/development').json()['announcements']
    assert result[0]['halaqa_id']==n['rings'][0]
    assert n['students'][1].get(B+'/development').json()['announcements']==[]
    assert n['students'][0].get(B+'/development').json()['announcements'][0]['title']=='موعد الحلقة'
