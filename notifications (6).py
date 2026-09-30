import base64, hashlib, json, secrets
from datetime import datetime,timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select, delete, func
from app.db.session import get_db
from app.models import NotificationPreference, PushSubscription, NotificationJob
from app.api.halaqat import Input, _actor
from app.services.notifications import CATEGORIES, preference, keypair, valid_endpoint, enqueue, smtp_ready

router=APIRouter(prefix='/api/notifications')

def pref(db,uid):
    p=preference(db,uid)
    if not p:p=NotificationPreference(user_id=uid);db.add(p);db.flush()
    return p

@router.get('/settings')
def settings(request:Request,db=Depends(get_db)):
    u=_actor(request,db);p=pref(db,u.id);k=keypair(db);db.commit()
    return {'user_id':u.id,'public_key':k.public,'email':p.email,'verified':p.verified,'email_enabled':p.email_enabled,'push_enabled':p.push_enabled,'categories':json.loads(p.categories),'labels':CATEGORIES,'smtp_ready':smtp_ready(),
      'delivery':dict(db.execute(select(NotificationJob.status,func.count(NotificationJob.id)).where(NotificationJob.user_id==u.id).group_by(NotificationJob.status)).all())}

class PreferencesInput(Input):
    email_enabled:bool=False
    push_enabled:bool=True
    categories:list[str]=Field(default_factory=list,max_length=6)

@router.put('/settings')
def save(data:PreferencesInput,request:Request,db=Depends(get_db)):
    u=_actor(request,db);p=pref(db,u.id)
    if any(c not in CATEGORIES for c in data.categories):raise HTTPException(422,'نوع تنبيه غير صحيح')
    if data.email_enabled and (not p.verified or not smtp_ready()):raise HTTPException(422,'وثق البريد وتأكد من تفعيل خدمة الإرسال أولًا')
    p.email_enabled=data.email_enabled;p.push_enabled=data.push_enabled;p.categories=json.dumps(sorted(set(data.categories)));db.commit();return {'ok':True}

class SubscriptionInput(Input):
    endpoint:str=Field(max_length=2048)
    keys:dict[str,str]

@router.post('/subscribe')
def subscribe(data:SubscriptionInput,request:Request,db=Depends(get_db)):
    u=_actor(request,db)
    if not valid_endpoint(data.endpoint):raise HTTPException(422,'خادم إشعارات غير مدعوم؛ استخدم Safari أو Chrome أو Firefox')
    try:
        raw=lambda k:base64.urlsafe_b64decode(data.keys[k]+'='*(-len(data.keys[k])%4))
        if len(raw('p256dh'))!=65 or len(raw('auth'))!=16:raise ValueError()
    except Exception:raise HTTPException(422,'مفاتيح اشتراك غير صالحة')
    h=hashlib.sha256(data.endpoint.encode()).hexdigest();row=db.scalar(select(PushSubscription).where(PushSubscription.endpoint_hash==h))
    if not row:
        if db.scalar(select(func.count(PushSubscription.id)).where(PushSubscription.user_id==u.id))>=10:raise HTTPException(422,'الحد الأقصى عشرة أجهزة')
        row=PushSubscription(user_id=u.id,endpoint_hash=h);db.add(row)
    row.user_id=u.id;row.subscription=json.dumps(data.model_dump(),sort_keys=True)
    pref(db,u.id).push_enabled=True;db.commit();return {'ok':True}

class EndpointInput(Input):
    endpoint:str=Field(max_length=2048)

@router.post('/unsubscribe')
def unsubscribe(data:EndpointInput,request:Request,db=Depends(get_db)):
    u=_actor(request,db);db.execute(delete(PushSubscription).where(PushSubscription.user_id==u.id,PushSubscription.endpoint_hash==hashlib.sha256(data.endpoint.encode()).hexdigest()));db.commit();return {'ok':True}

class EmailInput(Input):
    email:str=Field(min_length=5,max_length=254,pattern=r'^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$')

@router.post('/email')
def email(data:EmailInput,request:Request,db=Depends(get_db)):
    u=_actor(request,db);p=pref(db,u.id);now=datetime.utcnow()
    if not smtp_ready():raise HTTPException(503,'إرسال البريد غير مفعّل؛ يضبط المالك إعدادات SMTP على الخادم')
    if p.last_sent and p.last_sent>now-timedelta(minutes=2):raise HTTPException(429,'انتظر دقيقتين قبل طلب رمز آخر')
    p.email=data.email.strip().lower();p.verified=False;p.email_enabled=False;p.attempts=0;p.last_sent=now
    token=str(secrets.randbelow(900000)+100000);p.code_hash=hashlib.sha256(token.encode()).hexdigest();p.code_expires=now+timedelta(minutes=15)
    db.execute(delete(NotificationJob).where(NotificationJob.user_id==u.id,NotificationJob.category=='verification'))
    db.add(NotificationJob(user_id=u.id,category='verification',channel='email',destination=p.email,body='رمز توثيق بريدك في حلقات مشكاة ونور: '+token+'\nصالح لمدة 15 دقيقة.'))
    db.commit();return {'ok':True,'message':'أضيف رمز التحقق إلى قائمة الإرسال؛ راجع بريدك'}

class CodeInput(Input):
    code:str=Field(pattern=r'^\d{6}$')

@router.post('/email/verify')
def verify(data:CodeInput,request:Request,db=Depends(get_db)):
    u=_actor(request,db);p=pref(db,u.id)
    if not p.code_expires or p.code_expires<datetime.utcnow() or p.attempts>=5:raise HTTPException(422,'الرمز منتهٍ؛ اطلب رمزًا جديدًا')
    p.attempts+=1
    if not secrets.compare_digest(p.code_hash,hashlib.sha256(data.code.encode()).hexdigest()):db.commit();raise HTTPException(422,'رمز غير صحيح')
    p.verified=True;p.email_enabled=True;p.code_hash='';p.code_expires=None;db.commit();return {'ok':True}

@router.post('/test')
def test(request:Request,db=Depends(get_db)):
    u=_actor(request,db)
    recent=db.scalar(select(NotificationJob.id).where(NotificationJob.user_id==u.id,NotificationJob.student_id.is_(None),NotificationJob.created_at>datetime.utcnow()-timedelta(minutes=1)))
    if recent:raise HTTPException(429,'انتظر دقيقة قبل الاختبار التالي')
    p=pref(db,u.id);cats=json.loads(p.categories)
    if not cats:raise HTTPException(422,'فعّل نوع تنبيه واحدًا على الأقل')
    enqueue(db,u.id,None,cats[0],'هذا تنبيه تجريبي من حلقات مشكاة ونور.');db.flush()
    if not any(isinstance(x,NotificationJob) for x in db.new) and not db.scalar(select(NotificationJob.id).where(NotificationJob.user_id==u.id,NotificationJob.created_at>datetime.utcnow()-timedelta(seconds=2))):raise HTTPException(422,'فعّل إشعارات الجهاز أو وثّق البريد أولًا')
    db.commit();return {'ok':True,'message':'تمت إضافة الاختبار لقائمة الإرسال؛ راجع حالة التسليم'}
