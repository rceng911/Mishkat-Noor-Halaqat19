import re

ALLOWED_SYMBOLS = "@&-_=$"

def validate_password(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, "كلمة المرور يجب أن تكون 8 أحرف على الأقل"
    if not re.search(r"[A-Z]", password):
        return False, "يجب أن تحتوي كلمة المرور على حرف إنجليزي كبير واحد على الأقل"
    if not re.search(r"[a-z]", password):
        return False, "يجب أن تحتوي كلمة المرور على حرف إنجليزي صغير واحد على الأقل"
    if not re.search(r"[0-9]", password):
        return False, "يجب أن تحتوي كلمة المرور على رقم واحد على الأقل"
    if not any(ch in ALLOWED_SYMBOLS for ch in password):
        return False, "يجب أن تحتوي كلمة المرور على رمز واحد على الأقل من: @ & - _ = $"
    invalid_symbols = [ch for ch in password if not (ch.isalnum() or ch in ALLOWED_SYMBOLS)]
    if invalid_symbols:
        return False, "الرموز المسموحة فقط هي: @ & - _ = $"
    return True, ""
