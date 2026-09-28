import re
import unicodedata

def normalize_username(value):
    return unicodedata.normalize("NFKC", value or "").strip().casefold()

def validate_username(value):
    value = normalize_username(value)
    if any(ch.isspace() for ch in value):
        suggestion = re.sub(r"\s+", "_", value)
        return False, f"اسم المستخدم لا يقبل المسافات. استبدلها بالشرطة السفلية، مثل: {suggestion}"
    if not 3 <= len(value) <= 30 or not re.fullmatch(r"[\w-]+", value, re.UNICODE):
        return False, "اسم المستخدم من 3 إلى 30 حرفًا عربيًا أو إنجليزيًا أو رقمًا مع _ أو -، دون مسافات"
    return True, ""

