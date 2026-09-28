from datetime import timedelta,datetime
from sqlalchemy import select
from app.api.student_file import today
from app.db.session import SessionLocal
from app.models import NotificationJob,NotificationPreference,HalaqaStudent,User,PushSubscription

B='/api/halaqat/mosques/1'
def test_learning_support_scope_and_intervals(network):
    n=network;t=n['teachers'][0];s=n['ids'][0];url=f'{B}/students/{s}'
    assert t.put(url+'/juz/1',json={'status':'memorized'}).status_code==200
    assert n['students'][0].put(url+'/juz/1',json={'status':'memorized'}).status_code==403
    assert n['teachers'][1].get(url+'/advancement').status_code==404
    r=t.post(url+'/mistakes',json={'day':str(today()),'surah':1,'ayah':3,'kind':'memory','support':'strong'});assert r.status_code==200,r.text
    assert t.post(url+'/mistakes',json={'day':str(today()),'surah':1,'ayah':8,'kind':'memory'}).status_code==422
    d=t.get(url+'/advancement').json();assert d['suggestions'][0]['support']=='strong'
    assert t.post(url+'/review/1/approve',json={'due':str(today())}).status_code==200
    assert t.post(url+'/review/1/approve',json={'due':str(today())}).status_code==409
    assert t.post(url+'/review/1/result',json={'day':str(today()),'score':9}).status_code==200
    assert t.get(url+'/advancement').json()['suggestions'][0]['interval']==7
    # An unresolved error keeps the suggestion urgent even after a good review.
    assert t.get(url+'/advancement').json()['suggestions'][0]['due']==str(today())
    assert t.put(url+'/mistakes/'+str(r.json()['id']),json={'day':str(today()),'surah':1,'ayah':3,'kind':'memory','support':'strong','resolved':True}).status_code==200
    assert t.get(url+'/advancement').json()['suggestions'][0]['due']==str(today()+timedelta(days=7))
    assert t.post(url+'/review/1/result',json={'day':str(today()),'score':9}).status_code==409
    plan={'title':'تثبيت الفاتحة','start':str(today()),'end':str(today()+timedelta(days=14)),'tasks':[{'text':'تثبيت أول ثلاث آيات'}]}
    assert t.post(url+'/support-plans',json=plan).status_code==200
    pid=t.get(url+'/advancement').json()['plans'][0]['id']
    assert t.put(url+f'/support-plans/{pid}',json=plan|{'status':'completed','outcome':'تحسن'}).status_code==422
    assert t.put(url+f'/support-plans/{pid}',json=plan|{'tasks':[{'text':'تثبيت أول ثلاث آيات','done':True}],'status':'completed','outcome':'اجتاز'}).status_code==200

def test_risk_and_cross_mosque_analytics(network):
    n=network;t=n['teachers'][0];url=f'{B}/students/{n["ids"][0]}'
    for i in range(3):assert t.post(url+'/progress',json={'day':str(today()-timedelta(days=i)),'attendance':'absent'}).status_code==200
    assert len(t.get(B+'/support-dashboard').json()['risks'])==1
    assert n['students'][0].get(B+'/support-dashboard').status_code==403
    assert n['teachers'][1].get(B+'/support-dashboard').json()['risks']==[]
    assert n['owner'].get('/api/halaqat/organizations/learning-overview').json()['mosques'][0]['at_risk']==1
    assert t.get('/api/halaqat/organizations/learning-overview').status_code==403

def test_offline_conflict_idempotence_and_scope(network):
    from uuid import uuid4
    n=network;t=n['teachers'][0];snap=t.get(B+'/offline-snapshot').json();s=snap['students'][0]
    p={'id':str(uuid4()),'user_id':snap['user_id'],'student_id':s['id'],'base':s['base'],'progress':{'day':snap['day'],'attendance':'present','memorized':'الفاتحة'}}
    assert n['students'][0].get(B+'/offline-snapshot').status_code==403
    assert n['teachers'][1].post(B+'/offline-sync',json=p).status_code in (403,404)
    assert t.post(B+'/offline-sync',json=p).status_code==200
    assert t.post(B+'/offline-sync',json=p).json()['already_synced']
    assert t.post(B+'/offline-sync',json=p|{'id':str(uuid4())}).status_code==409
    assert t.post(B+'/offline-sync',json=p|{'progress':p['progress']|{'notes':'changed'}}).status_code==409

def test_exam_booking_promotes_after_review(network):
    n=network;t=n['teachers'][0];o=n['owner'];sid=n['ids'][0];url=f'{B}/students/{sid}'
    tid=t.get('/api/halaqat/context').json()['user']['id']
    r=t.post(url+'/organized-exams',json={'title':'اختبار الجزء','syllabus':'الجزء الأول','due':str(today()),'criteria':[{'name':'الحفظ','maximum':100}]});assert r.status_code==200,r.text
    eid=r.json()['id'];e=url+f'/organized-exams/{eid}'
    assert t.put(e+'/booking',json={'examiner_id':tid,'time':'16:00'}).status_code==403
    assert o.put(e+'/booking',json={'examiner_id':tid,'time':'16:00','next_level':'الجزء الثاني'}).status_code==200
    assert o.post(e+'/promote').status_code==409
    assert t.put(e+'/result',json={'day':str(today()),'scores':[90]}).status_code==200
    assert o.post(e+'/promote').status_code==200
    assert o.get(url+'/file').json()['student']['level']=='الجزء الثاني'
    assert o.post(e+'/promote').status_code==409
    assert t.put(e+'/result',json={'day':str(today()),'scores':[95]}).status_code==409

def test_username_revokes_sessions_keeps_children(network):
    n=network;parent=n['students'][0];uid=parent.get('/api/halaqat/context').json()['user']['id'];url=f'{B}/accounts/{uid}/username'
    assert n['teachers'][0].put(url,json={'username':'parent_new'}).status_code==403
    assert n['owner'].put(url,json={'username':'اسم بمسافة'}).status_code==422
    assert n['owner'].put(url,json={'username':'parent_new'}).status_code==200
    assert parent.get('/api/halaqat/context').status_code==401
    with SessionLocal() as db:assert db.get(HalaqaStudent,n['ids'][0]).user_id==uid

def test_push_outbox_delivery_and_revoked_recipient(network,monkeypatch):
    import base64,json
    from app.services.notifications import deliver_one
    n=network;c=n['students'][0];t=n['teachers'][0];url=f'{B}/students/{n["ids"][0]}'
    assert c.get('/api/notifications/settings').status_code==200
    sub={'endpoint':'https://fcm.googleapis.com/fcm/send/test','keys':{'p256dh':base64.urlsafe_b64encode(b'\x04'+b'x'*64).decode().rstrip('='),'auth':base64.urlsafe_b64encode(b'y'*16).decode().rstrip('=')}}
    assert c.post('/api/notifications/subscribe',json=sub|{'endpoint':'http://127.0.0.1/private'}).status_code==422
    assert c.post('/api/notifications/subscribe',json=sub).status_code==200
    assert t.post(url+'/progress',json={'day':str(today()),'attendance':'present'}).status_code==200
    delivered=[]
    monkeypatch.setattr('pywebpush.webpush',lambda **kw:delivered.append(kw))
    assert deliver_one();assert len(delivered)==1
    assert 'طالب' not in json.loads(delivered[0]['data'])['body']
    assert c.get('/api/notifications/settings').json()['delivery']['sent']==1
    assert t.post(url+'/messages',json={'body':'رسالة جديدة'}).status_code==200
    with SessionLocal() as db:
        db.get(HalaqaStudent,n['ids'][0]).user_id=None;db.commit()
    assert deliver_one();assert len(delivered)==1
    assert c.get('/api/notifications/settings').json()['delivery']['cancelled']==1

def test_email_verification_preference_and_retry(network,monkeypatch):
    import re
    from app.services.notifications import deliver_one
    n=network;c=n['students'][0]
    for k,v in {'SMTP_HOST':'smtp.example.test','SMTP_FROM':'admin@example.test','PUBLIC_URL':'https://example.test'}.items():monkeypatch.setenv(k,v)
    c.get('/api/notifications/settings')
    assert c.put('/api/notifications/settings',json={'email_enabled':True,'categories':['message']}).status_code==422
    assert c.post('/api/notifications/email',json={'email':'parent@example.test'}).status_code==200
    sent=[];monkeypatch.setattr('app.services.notifications.send_email',lambda dest,body:sent.append((dest,body)))
    assert deliver_one();code=re.search(r'\b\d{6}\b',sent[0][1]).group()
    assert c.post('/api/notifications/email/verify',json={'code':'000000'}).status_code==422
    assert c.post('/api/notifications/email/verify',json={'code':code}).status_code==200
    assert c.get('/api/notifications/settings').json()['verified']
    assert c.put('/api/notifications/settings',json={'email_enabled':True,'push_enabled':False,'categories':['message']}).status_code==200
    n['teachers'][0].post(f'{B}/students/{n["ids"][0]}/messages',json={'body':'hello'})
    monkeypatch.setattr('app.services.notifications.send_email',lambda *args:(_ for _ in ()).throw(OSError('failure')))
    assert deliver_one()
    with SessionLocal() as db:
        j=db.scalar(select(NotificationJob).where(NotificationJob.category=='message'));assert j.status=='pending' and j.attempts==1
        j.available_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
    monkeypatch.setattr('app.services.notifications.send_email',lambda dest,body:sent.append((dest,body)))
    assert deliver_one();assert len(sent)==2

def test_upgrade_v19_mistakes_preserves_records(tmp_path):
    from sqlalchemy import create_engine,text
    from app.db.migrations import ensure_v10_schema
    e=create_engine('sqlite:///'+str(tmp_path/'old.db'))
    with e.begin() as c:
        c.execute(text('CREATE TABLE recitation_mistakes (id INTEGER PRIMARY KEY, surah INTEGER, ayah INTEGER)'))
        c.execute(text('INSERT INTO recitation_mistakes VALUES (1,1,3)'))
    ensure_v10_schema(e);ensure_v10_schema(e)
    with e.connect() as c:assert tuple(c.execute(text('SELECT surah,ayah,support FROM recitation_mistakes')).one())==(1,3,'review')
    e.dispose()
