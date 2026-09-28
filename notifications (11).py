"""Transactional outbox. Generic payloads keep student details off lock screens."""
import base64, hashlib, json, os, secrets, smtplib, ssl, threading, logging
from datetime import datetime, timedelta
from email.message import EmailMessage
from urllib.parse import urlsplit
from sqlalchemy import select, event, inspect, update
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models import (PushKey, PushSubscription, NotificationPreference, NotificationJob, User, HalaqaStudent,
 Halaqa, HalaqaProgress, Assignment, StudentCertificate, StudentMessage, OrganizedExam, OrganizedResult, AbsenceExcuse)

log=logging.getLogger(__name__)
CATEGORIES={'attendance':'الحضور والغياب','progress':'التقييم والتسميع','assignment':'الأوراد','achievement':'الإنجازات','message':'المراسلات','exam':'الاختبارات'}

def public_url():
    raw=os.getenv('PUBLIC_URL',os.getenv('RENDER_EXTERNAL_URL','')).rstrip('/')
    return raw if raw.startswith('https://') else ''

def smtp_ready():
    return bool(os.getenv('SMTP_HOST') and os.getenv('SMTP_FROM') and public_url())

def keypair(db):
    row=db.get(PushKey,1)
    if row:return row
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    k=ec.generate_private_key(ec.SECP256R1())
    private=k.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
    public=base64.urlsafe_b64encode(k.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)).decode().rstrip('=')
    row=PushKey(id=1,private=private,public=public);db.add(row);db.flush();return row

def valid_endpoint(endpoint):
    try:
        p=urlsplit(endpoint);host=p.hostname or ''
        return p.scheme=='https' and p.port in (None,443) and not p.username and not p.password and not p.fragment and (host=='fcm.googleapis.com' or host=='updates.push.services.mozilla.com' or host.endswith('.push.services.mozilla.com') or host.endswith('.push.apple.com') or host=='web.push.apple.com')
    except ValueError:return False

def preference(db,uid):
    return db.get(NotificationPreference,uid)

def enqueue(db,uid,sid,category,body='يوجد تحديث جديد في حلقات مشكاة ونور. افتح حسابك للاطلاع.'):
    u=db.get(User,uid);p=preference(db,uid)
    if not u or not u.active or not p or category not in json.loads(p.categories):return
    if p.push_enabled:
        for sub in db.scalars(select(PushSubscription).where(PushSubscription.user_id==uid)):
            db.add(NotificationJob(user_id=uid,student_id=sid,category=category,channel='push',destination=sub.subscription,body=body))
    if p.email_enabled and p.verified and p.email:
        db.add(NotificationJob(user_id=uid,student_id=sid,category=category,channel='email',destination=p.email,body=body))

@event.listens_for(Session,'before_flush')
def on_changes(db,context,instances):
    events=set()
    for obj in list(db.new)+list(db.dirty):
        if obj not in db.new and not db.is_modified(obj,include_collections=False):continue
        sid=getattr(obj,'student_id',None);category=None
        if isinstance(obj,HalaqaProgress):category='attendance' if inspect(obj).attrs.attendance.history.has_changes() else 'progress'
        elif isinstance(obj,Assignment):category='assignment'
        elif isinstance(obj,StudentCertificate):category='achievement'
        elif isinstance(obj,StudentMessage):category='message'
        elif isinstance(obj,OrganizedExam):category='exam'
        elif isinstance(obj,OrganizedResult):
            exam=db.get(OrganizedExam,obj.exam_id);sid=exam.student_id if exam else None;category='exam'
        elif isinstance(obj,AbsenceExcuse):category='attendance'
        if not sid or not category:continue
        s=db.get(HalaqaStudent,sid)
        if not s or not s.active:continue
        if s.user_id:events.add((s.user_id,sid,category))
        if s.user_id and isinstance(obj,HalaqaProgress) and any(inspect(obj).attrs[k].history.has_changes() for k in ('memorized','revision','memorization_score','tajweed_score')):
            events.add((s.user_id,sid,'progress'))
        if isinstance(obj,(StudentMessage,AbsenceExcuse)):
            from app.api.halaqat import _ring_ids_for, TEACHER_ROLE, SUPERVISOR_ROLE
            mid=db.get(Halaqa,s.halaqa_id).mosque_id
            for u in db.scalars(select(User).where(User.active.is_(True),User.role.in_(['owner',TEACHER_ROLE,SUPERVISOR_ROLE]))):
                if (u.role=='owner' or u.mosque_id==mid) and s.halaqa_id in _ring_ids_for(u,mid,db):events.add((u.id,sid,category))
            sender=getattr(obj,'sender_id',None) or getattr(obj,'submitted_by',None)
            events.discard((sender,sid,category))
    # Coalesce changes in one transaction per student/recipient and respect categories.
    sent=set()
    for uid,sid,category in sorted(events):
        p=preference(db,uid)
        if (uid,sid) not in sent and p and category in json.loads(p.categories):
            enqueue(db,uid,sid,category);sent.add((uid,sid))

def allowed(db,job):
    u=db.get(User,job.user_id)
    if not u or not u.active:return False
    p=preference(db,u.id)
    if job.category=='verification':return bool(p and not p.verified and p.email==job.destination and p.code_expires and p.code_expires>datetime.utcnow())
    if not p or job.category not in json.loads(p.categories):return False
    if job.channel=='email' and not (p.verified and p.email_enabled and p.email==job.destination):return False
    if job.channel=='push' and (not p.push_enabled or not db.scalar(select(PushSubscription.id).where(PushSubscription.user_id==u.id,PushSubscription.subscription==job.destination))):return False
    if job.student_id:
        s=db.get(HalaqaStudent,job.student_id)
        if not s or not s.active:return False
        if u.role=='halaqa_student':return s.user_id==u.id
        from app.api.halaqat import _ring_ids_for
        mid=db.get(Halaqa,s.halaqa_id).mosque_id
        return (u.role=='owner' or u.mosque_id==mid) and s.halaqa_id in _ring_ids_for(u,mid,db)
    return True

def send_email(destination,body):
    msg=EmailMessage();msg['From']=os.environ['SMTP_FROM'];msg['To']=destination;msg['Subject']='حلقات مشكاة ونور'
    msg.set_content(body+'\n\n'+public_url()+'/halaqat\nيمكن إيقاف التنبيهات من إعدادات حسابك.')
    mode=os.getenv('SMTP_SECURITY','starttls');port=int(os.getenv('SMTP_PORT','465' if mode=='ssl' else '587'))
    cls=smtplib.SMTP_SSL if mode=='ssl' else smtplib.SMTP
    with cls(os.environ['SMTP_HOST'],port,timeout=15,**({'context':ssl.create_default_context()} if mode=='ssl' else {})) as smtp:
        if mode!='ssl':smtp.starttls(context=ssl.create_default_context())
        if os.getenv('SMTP_USER'):smtp.login(os.environ['SMTP_USER'],os.environ.get('SMTP_PASSWORD',''))
        smtp.send_message(msg)

def deliver_one():
    """Claim with compare-and-swap; failures retry, including after process restart."""
    with SessionLocal() as db:
        now=datetime.utcnow()
        job=db.scalar(select(NotificationJob).where(NotificationJob.status.in_(['pending','sending']),NotificationJob.available_at<=now).order_by(NotificationJob.id).limit(1))
        if not job:return False
        old=job.available_at
        if not db.execute(update(NotificationJob).where(NotificationJob.id==job.id,NotificationJob.available_at==old).values(status='sending',available_at=now+timedelta(minutes=3),attempts=NotificationJob.attempts+1)).rowcount:return True
        db.commit();db.refresh(job)
        if not allowed(db,job):job.status='cancelled';job.body='';db.commit();return True
        try:
            if job.channel=='email':
                if not smtp_ready():raise RuntimeError('email_not_configured')
                send_email(job.destination,job.body)
            else:
                from pywebpush import webpush
                from py_vapid import Vapid
                subscription=json.loads(job.destination)
                if not valid_endpoint(subscription['endpoint']):raise RuntimeError('invalid_endpoint')
                key=keypair(db);db.commit()
                vapid=Vapid.from_pem(key.private.encode())
                webpush(subscription_info=subscription,data=json.dumps({'title':'حلقات مشكاة ونور','body':job.body,'tag':'notice-'+str(job.id),'url':'/halaqat'},ensure_ascii=False),vapid_private_key=vapid,vapid_claims={'sub':os.getenv('VAPID_SUBJECT',public_url() or 'mailto:admin@example.com')},timeout=15,ttl=86400)
            job.status='sent';job.body='';job.error=''
        except Exception as ex:
            code=getattr(getattr(ex,'response',None),'status_code',None)
            if code in (404,410) and job.channel=='push':
                for sub in db.scalars(select(PushSubscription).where(PushSubscription.user_id==job.user_id,PushSubscription.subscription==job.destination)):db.delete(sub)
                job.status='expired'
            else:job.status='failed' if job.attempts>=5 else 'pending'
            job.error=('http_'+str(code)) if code else type(ex).__name__
            job.available_at=now+timedelta(seconds=min(3600,30*2**job.attempts))
        db.commit();return True

def start_worker():
    stop=threading.Event()
    def work():
        while not stop.is_set():
            try:found=deliver_one()
            except Exception:
                log.warning('Notification outbox retry required');found=False
            stop.wait(1 if found else 10)
    t=threading.Thread(target=work,daemon=True);t.start();return stop,t
