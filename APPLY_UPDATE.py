#!/usr/bin/env python3
"""Apply the role/dashboard/approval update without deleting existing features.

Usage:
    python APPLY_UPDATE.py "C:\\path\\to\\Mishkat Noor Halaqat"

If no path is supplied, the script looks for the current project folder nearby.
A timestamped backup of every touched existing file is created before changes.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAYLOAD = HERE / "payload"


def find_project() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).expanduser().resolve()
    candidates = [
        Path.cwd(),
        Path.cwd() / "Mishkat Noor Halaqat",
        HERE.parent / "Mishkat Noor Halaqat",
        HERE / "Mishkat Noor Halaqat",
    ]
    for candidate in candidates:
        if (candidate / "app" / "main.py").is_file() and (candidate / "web" / "templates" / "halaqat.html").is_file():
            return candidate.resolve()
    entered = input("أدخل مسار مجلد Mishkat Noor Halaqat: ").strip().strip('"')
    return Path(entered).expanduser().resolve()


def require_project(root: Path) -> None:
    required = [
        root / "app" / "main.py",
        root / "app" / "models" / "__init__.py",
        root / "web" / "templates" / "halaqat.html",
        root / "web" / "static" / "halaqat.js",
    ]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise SystemExit("المجلد المختار ليس نسخة المشروع المتوقعة. ملفات ناقصة:\n- " + "\n- ".join(missing))


def backup_file(root: Path, backup: Path, rel: str) -> None:
    src = root / rel
    if src.exists():
        dst = backup / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"تعذر العثور على موضع التحديث: {label}. لم يتم حذف أي ملف.")
    return text.replace(old, new, 1)


def patch_models(root: Path) -> None:
    path = root / "app" / "models" / "__init__.py"
    text = path.read_text(encoding="utf-8")
    line = "from .access import HalaqaChangeRequest\n"
    if line not in text:
        text = text.rstrip() + "\n" + line
    path.write_text(text, encoding="utf-8")


def patch_main(root: Path) -> None:
    path = root / "app" / "main.py"
    text = path.read_text(encoding="utf-8")
    old_router = '''from app.api.advancement import router as advancement_router\nfrom app.api.notifications import router as notifications_router\napp.include_router(advancement_router)\napp.include_router(notifications_router)'''
    new_router = '''from app.api.advancement import router as advancement_router\nfrom app.api.notifications import router as notifications_router\nfrom app.api.access import router as access_router, portal_kind, ROLE_LABELS\napp.include_router(advancement_router)\napp.include_router(notifications_router)\napp.include_router(access_router)'''
    text = replace_once(text, old_router, new_router, "تسجيل access router")

    old_portal = '''@app.get("/halaqat")\ndef portal(request: Request):\n    u = user_for(request)\n    if not u:\n        return RedirectResponse("/login", status_code=303)\n    return templates.TemplateResponse(request=request, name="halaqat.html", context={\n        "title": "حلقات مشكاة ونور", "show_version": u.role == "owner", "app_version": settings.app_version\n    })'''
    new_portal = '''def _dashboard_path(user):\n    kind = portal_kind(user)\n    return f"/dashboard/{kind}" if kind != "unknown" else "/login"\n\n\ndef _dashboard_page(request: Request, expected: str):\n    u = user_for(request)\n    if not u:\n        return RedirectResponse("/login", status_code=303)\n    actual = portal_kind(u)\n    if actual != expected:\n        return JSONResponse({\n            "detail": "هذه الواجهة غير مصرح بها لهذا الحساب",\n            "dashboard": _dashboard_path(u),\n        }, status_code=403)\n    return templates.TemplateResponse(request=request, name="halaqat.html", context={\n        "title": f"حلقات مشكاة ونور - {ROLE_LABELS.get(actual, actual)}",\n        "show_version": u.role == "owner",\n        "app_version": settings.app_version,\n        "portal_role": actual,\n        "role_label": ROLE_LABELS.get(actual, actual),\n    })\n\n\n@app.get("/halaqat")\ndef portal(request: Request):\n    u = user_for(request)\n    if not u:\n        return RedirectResponse("/login", status_code=303)\n    return RedirectResponse(_dashboard_path(u), status_code=303)\n\n\n@app.get("/dashboard/owner")\ndef owner_dashboard(request: Request):\n    return _dashboard_page(request, "owner")\n\n\n@app.get("/dashboard/supervisor")\ndef supervisor_dashboard(request: Request):\n    return _dashboard_page(request, "supervisor")\n\n\n@app.get("/dashboard/teacher")\ndef teacher_dashboard(request: Request):\n    return _dashboard_page(request, "teacher")\n\n\n@app.get("/dashboard/guardian")\ndef guardian_dashboard(request: Request):\n    return _dashboard_page(request, "guardian")\n\n\n@app.get("/dashboard/student")\ndef student_dashboard(request: Request):\n    return _dashboard_page(request, "student")'''
    text = replace_once(text, old_portal, new_portal, "مسارات لوحات الأدوار")
    path.write_text(text, encoding="utf-8")


def patch_template(root: Path) -> None:
    path = root / "web" / "templates" / "halaqat.html"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '<link rel="stylesheet" href="/static/calm.css?build=app">',
        '<link rel="stylesheet" href="/static/calm.css?build=app">\n<link rel="stylesheet" href="/static/role-ui.css?build=21">',
        "CSS الصلاحيات",
    )
    text = replace_once(
        text,
        '<main class="halaqat-shell" id="halaqatApp">',
        '<main class="halaqat-shell" id="halaqatApp" data-portal-role="{{ portal_role|default(\'\') }}">',
        "وسم الدور",
    )
    if 'المسجد أو الجهة<select id="halaqatMosque"' in text:
        text = text.replace('المسجد أو الجهة<select id="halaqatMosque"', 'الفرع / الجهة<select id="halaqatMosque"', 1)
    text = replace_once(
        text,
        '<script src="/static/halaqat.js?build=20.4"></script>',
        '<script src="/static/halaqat.js?build=20.4"></script>\n<script src="/static/role-ui.js?build=21"></script>',
        "JavaScript الصلاحيات",
    )
    path.write_text(text, encoding="utf-8")


def copy_payload(root: Path) -> None:
    for src in PAYLOAD.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(PAYLOAD)
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def main() -> None:
    root = find_project()
    require_project(root)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / f"_backup_before_role_update_{stamp}"
    touched = [
        "app/main.py",
        "app/models/__init__.py",
        "web/templates/halaqat.html",
        "app/api/access.py",
        "app/models/access.py",
        "web/static/role-ui.js",
        "web/static/role-ui.css",
        "tests/test_role_access.py",
    ]
    existed_before = {rel: (root / rel).exists() for rel in touched}
    for rel in touched:
        backup_file(root, backup, rel)
    try:
        patch_models(root)
        patch_main(root)
        patch_template(root)
        copy_payload(root)
    except Exception as exc:
        # Roll back every touched path. Existing files are restored; newly added
        # update files are removed. The backup remains available for inspection.
        for rel in touched:
            dst = root / rel
            saved = backup / rel
            if saved.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(saved, dst)
            elif not existed_before[rel] and dst.exists():
                dst.unlink()
        print(f"فشل التحديث وتمت استعادة الملفات الأصلية: {exc}")
        print(f"النسخة الاحتياطية موجودة في: {backup}")
        raise SystemExit(1)
    print("تم تطبيق تحديث الواجهات والصلاحيات بدون حذف المزايا الحالية.")
    print(f"المشروع: {root}")
    print(f"النسخة الاحتياطية: {backup}")
    print("الخطوة التالية: ثبّت المتطلبات ثم شغّل: python -m pytest -q")


if __name__ == "__main__":
    main()
