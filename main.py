from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import hashlib
import secrets
import os
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError

from app.core.config import ROOT, settings
from app.db.session import engine, Base, SessionLocal
from app.db.migrations import ensure_v10_schema
from app.models import User, Mosque, AuthSession, LoginAttempt
from app.api.halaqat import router, PORTAL_ROLES
from app.api.student_file import router as student_router
from app.api.routes import audit, session
from app.services.session_store import create_session, delete_session, COOKIE
from app.services.auth import hash_password, verify_password
from app.services.account_policy import normalize_username, validate_username
from app.services.password_policy import validate_password

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    ensure_v10_schema(engine)
    # Singleton organization serializes the one-time owner setup.
    with SessionLocal() as db:
        if not db.get(Mosque, 1):
            db.add(Mosque(id=1, name="جهة التحفيظ"))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
    from app.services.notifications import start_worker
    worker = start_worker() if os.getenv('NOTIFICATION_WORKER', '1' if settings.secure_cookie else '0') == '1' else None
    try:
        yield
    finally:
        if worker:
            worker[0].set()
            worker[1].join(timeout=2)

app = FastAPI(title="حلقات مشكاة ونور", version=settings.app_version, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=str(ROOT / "web" / "static")), name="static")
templates = Jinja2Templates(directory=str(ROOT / "web" / "templates"))
app.include_router(router)
app.include_router(student_router)
from app.api.followup import router as followup_router
app.include_router(followup_router)
from app.api.development import router as development_router
app.include_router(development_router)
from app.api.management import router as management_router
app.include_router(management_router)
from app.api.learning import router as learning_router
app.include_router(learning_router)
from app.api.advancement import router as advancement_router
from app.api.notifications import router as notifications_router
app.include_router(advancement_router)
app.include_router(notifications_router)

@app.get('/sw.js')
def service_worker():
    from fastapi.responses import FileResponse
    return FileResponse(ROOT / 'web' / 'static' / 'sw.js', media_type='application/javascript', headers={'Service-Worker-Allowed':'/', 'Cache-Control':'no-cache'})

@app.get('/offline')
def offline_page():
    from fastapi.responses import FileResponse
    return FileResponse(ROOT / 'web' / 'static' / 'offline.html',media_type='text/html')

def user_for(request):
    s = session(request)
    if not s:
        return None
    with SessionLocal() as db:
        u = db.get(User, s.user_id)
        return u if u and u.active else None

def has_owner():
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.role == "owner")) is not None

def page(request, mode, error="", status=200, required=False):
    return templates.TemplateResponse(request=request, name="auth.html", context={
        "title": {"login": "تسجيل الدخول", "setup": "إعداد المالك", "security": "تغيير رمز الدخول"}[mode],
        "mode": mode, "error": error, "required": required, "production": settings.secure_cookie
    }, status_code=status)

def signed_in_response(user_id, url, remember=False):
    lifetime_hours = settings.remember_days * 24 if remember else settings.session_hours
    token = create_session(user_id, lifetime_hours)
    response = RedirectResponse(url, status_code=303)
    cookie_options = {"httponly": True, "secure": settings.secure_cookie, "samesite": "lax"}
    if remember:
        cookie_options["max_age"] = lifetime_hours * 3600
    response.set_cookie(COOKIE, token, **cookie_options)
    return response

@app.middleware("http")
async def security_boundary(request, call_next):
    path = request.url.path
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin") or request.headers.get("referer")
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "طلب من موقع آخر غير مسموح"}, status_code=403)
        if origin and urlsplit(origin).netloc != request.url.netloc:
            return JSONResponse({"detail": "مصدر الطلب غير مسموح"}, status_code=403)
    if path not in ("/login", "/logout", "/account/security", "/healthz") and not path.startswith("/static/"):
        u = user_for(request)
        if u and u.force_password_change:
            if path.startswith("/api/"):
                return JSONResponse({"detail": "غيّر الرمز المؤقت أولًا", "redirect": "/account/security"}, status_code=403)
            return RedirectResponse("/account/security", status_code=303)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    if not path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    if settings.secure_cookie:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response

@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return JSONResponse({"detail": "يوجد سجل بنفس البيانات أو تحديث متزامن؛ حدّث الصفحة وحاول مجددًا"}, status_code=409)

@app.get("/healthz")
def health():
    try:
        with SessionLocal() as db:
            db.execute(select(1))
        return {"ok": True}
    except Exception:
        return JSONResponse({"ok": False}, status_code=503)

@app.get("/")
def home(request: Request):
    return RedirectResponse("/setup" if not has_owner() else "/halaqat" if user_for(request) else "/login", status_code=303)

@app.get("/setup")
def setup_page(request: Request):
    return RedirectResponse("/login", status_code=303) if has_owner() else page(request, "setup")

@app.post("/setup")
def setup(request: Request, organization: str=Form(...), full_name: str=Form(...), username: str=Form(...),
          password: str=Form(...), confirm_password: str=Form(...), setup_token: str=Form("")):
    if settings.secure_cookie and (not settings.setup_token or not secrets.compare_digest(setup_token, settings.setup_token)):
        return page(request, "setup", "رمز إعداد المالك غير صحيح", 403)
    username = normalize_username(username)
    valid, error = validate_username(username)
    if not valid:
        return page(request, "setup", error, 422)
    valid, error = validate_password(password)
    if not valid or len(password) > 128:
        return page(request, "setup", error or "الرمز طويل جدًا", 422)
    if password != confirm_password:
        return page(request, "setup", "كلمتا المرور غير متطابقتين", 422)
    if not 2 <= len(full_name.strip()) <= 180 or not 2 <= len(organization.strip()) <= 180:
        return page(request, "setup", "أدخل اسمك واسم جهة التحفيظ", 422)
    with SessionLocal() as db:
        org = db.scalar(select(Mosque).where(Mosque.id == 1).with_for_update())
        if db.scalar(select(User.id).where(User.role == "owner")):
            return RedirectResponse("/login", status_code=303)
        org.name = organization.strip()
        u = User(email="owner@accounts.invalid", username=username, full_name=full_name.strip(), password_hash=hash_password(password), role="owner", mosque_id=1)
        db.add(u); db.flush()
        audit(db, u.id, 1, "owner_setup")
        db.commit()
        uid = u.id
    return signed_in_response(uid, "/halaqat")

@app.get("/login")
def login_page(request: Request):
    return RedirectResponse("/setup", status_code=303) if not has_owner() else page(request, "login")

@app.post("/login")
def login(request: Request, identity: str=Form(...), password: str=Form(...), remember_me: str=Form("")):
    identity = normalize_username(identity)
    key = hashlib.sha256(identity.encode()).hexdigest()
    now = datetime.utcnow()
    with SessionLocal() as db:
        attempt = db.get(LoginAttempt, key)
        if attempt and attempt.failures >= 10 and attempt.last_attempt > now - timedelta(minutes=15):
            return page(request, "login", "محاولات كثيرة؛ حاول بعد 15 دقيقة أو تواصل مع المالك", 429)
        u = db.scalar(select(User).where(User.username == identity, User.active.is_(True)))
        if len(password) > 128 or not u or not verify_password(password, u.password_hash):
            if not attempt:
                attempt = LoginAttempt(key=key, failures=0); db.add(attempt)
            if attempt.last_attempt and attempt.last_attempt < now - timedelta(minutes=15):
                attempt.failures = 0
            attempt.failures += 1; attempt.last_attempt = now; db.commit()
            return page(request, "login", "اسم المستخدم أو الرمز غير صحيح", 401)
        if attempt:
            db.delete(attempt)
        audit(db, u.id, u.mosque_id, "login")
        db.commit()
        uid, required = u.id, u.force_password_change
    return signed_in_response(uid, "/account/security" if required else "/halaqat", remember_me == "1")

@app.get("/account/security")
def password_page(request: Request):
    u = user_for(request)
    return page(request, "security", required=u.force_password_change) if u else RedirectResponse("/login", status_code=303)

@app.post("/account/security")
def password_update(request: Request, current_password: str=Form(...), new_password: str=Form(...), confirm_password: str=Form(...)):
    u = user_for(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    error = ""
    valid, policy_error = validate_password(new_password)
    if not verify_password(current_password, u.password_hash):
        error = "الرمز الحالي غير صحيح"
    elif new_password != confirm_password:
        error = "الرمزان الجديدان غير متطابقين"
    elif not valid or len(new_password) > 128:
        error = policy_error or "الرمز طويل جدًا"
    elif verify_password(new_password, u.password_hash):
        error = "اختر رمزًا مختلفًا عن الرمز الحالي"
    if error:
        return page(request, "security", error, 422, required=u.force_password_change)
    active_session = session(request)
    remember = bool(active_session and active_session.expires_at > datetime.utcnow() + timedelta(hours=settings.session_hours + 1))
    with SessionLocal() as db:
        current = db.get(User, u.id)
        current.password_hash = hash_password(new_password)
        current.force_password_change = False
        db.execute(delete(AuthSession).where(AuthSession.user_id == u.id))
        audit(db, u.id, u.mosque_id, "password_changed")
        db.commit()
    return signed_in_response(u.id, "/halaqat", remember)

@app.post("/logout")
def logout(request: Request):
    delete_session(request.cookies.get(COOKIE))
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE)
    return response

@app.get("/halaqat")
def portal(request: Request):
    u = user_for(request)
    if not u:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request=request, name="halaqat.html", context={
        "title": "حلقات مشكاة ونور", "show_version": u.role == "owner", "app_version": settings.app_version
    })
