from sqlalchemy import create_engine, text, inspect
from app.db.migrations import ensure_v10_schema


def test_upgrade_preserves_old_students_and_is_repeatable():
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE halaqa_students (id INTEGER PRIMARY KEY, full_name VARCHAR(180))'))
        db.execute(text('CREATE TABLE halaqa_account_requests (id INTEGER PRIMARY KEY)'))
        db.execute(text("INSERT INTO halaqa_students VALUES (1, 'طالب قديم')"))
    ensure_v10_schema(engine)
    ensure_v10_schema(engine)
    with engine.connect() as db:
        assert db.execute(text('SELECT full_name FROM halaqa_students')).scalar() == 'طالب قديم'
        columns = {c['name'] for c in inspect(db).get_columns('halaqa_students')}
        assert {'birth_date', 'school_grade', 'guardian_relation', 'current_memorization'} <= columns
    engine.dispose()


def test_full_legacy_schema_upgrade_and_history(tmp_path):
    """Recreate the shipped schema before v10 columns/tables, then upgrade twice."""
    from sqlalchemy import MetaData
    from app.db.session import Base
    from app.models import User, HalaqaStudent, HalaqaProgress, HalaqaSupervisor
    from sqlalchemy.orm import Session
    legacy = MetaData()
    extra_tables = {'juz_mastery','review_schedules','support_plans','exam_bookings','offline_receipts','push_keys','notification_preferences','push_subscriptions','notification_jobs','completion_goals','recitation_mistakes','home_practices','recitation_turns','substitute_teachers','learning_competitions','competition_entries','quran_records','ring_calendars','ring_calendar_exceptions','absence_excuses','student_messages','student_thread_reads','ring_announcements','organized_exams','organized_exam_results','student_import_previews','halaqa_supervisors', 'student_assignments', 'student_alert_reads', 'student_exam_appointments', 'halaqat_feature_settings'}
    extra_columns = {'users': {'account_type','phone','staff_notes'}, 'halaqa_students': {'national_id','recipient_type','guardian_relation','birth_date','school_grade','current_memorization'}, 'halaqa_account_requests': {'national_id','recipient_type','review_note','guardian_relation','birth_date','school_grade','current_memorization'}}
    for table in Base.metadata.sorted_tables:
        if table.name in extra_tables: continue
        copy = table.to_metadata(legacy)
        for name in extra_columns.get(table.name, set()): copy._columns.remove(copy.c[name])
    e = create_engine('sqlite:///'+str(tmp_path/'legacy.db'))
    legacy.create_all(e)
    with e.begin() as c:
        c.execute(legacy.tables['mosques'].insert(), {'id':1,'name':'مسجد قديم'})
        c.execute(legacy.tables['users'].insert(), [dict(id=1,email='owner@test.invalid',username='owner',full_name='مالك',password_hash='hash',role='owner',mosque_id=1),dict(id=2,email='student@test.invalid',username='student',full_name='طالب',password_hash='hash',role='halaqa_student',mosque_id=1)])
        c.execute(legacy.tables['halaqat'].insert(),dict(id=1,mosque_id=1,name='حلقة قديمة',supervisor_id=1))
        c.execute(legacy.tables['halaqa_students'].insert(),dict(id=1,halaqa_id=1,user_id=2,full_name='طالب قديم'))
        from datetime import date
        c.execute(legacy.tables['halaqa_progress'].insert(),dict(student_id=1,day=date(2026,9,1),created_by=1,memorized='الفاتحة',memorized_amount=1))
    Base.metadata.create_all(e)
    ensure_v10_schema(e); ensure_v10_schema(e)
    with Session(e) as db:
        assert db.get(HalaqaStudent,1).full_name=='طالب قديم'
        assert db.get(HalaqaStudent,1).recipient_type=='guardian'
        assert db.get(User,2).account_type=='guardian'
        assert db.get(HalaqaProgress,1).memorized=='الفاتحة'
        assert len(db.query(HalaqaSupervisor).all())==1
    e.dispose()
