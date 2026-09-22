from app.models import AuditLog
from app.services.session_store import get_session, COOKIE

def session(request):
    return get_session(request.cookies.get(COOKIE))

def audit(db, user_id, mosque_id, action, details=""):
    db.add(AuditLog(user_id=user_id, mosque_id=mosque_id, action=action, details=details))


def audit_change(db,user_id,mosque_id,action,entity,before,after):
    import json
    audit(db,user_id,mosque_id,action,json.dumps({'entity':entity,'before':before,'after':after},ensure_ascii=False,default=str))
