import json
from sqlalchemy import select
from app.models import RingCalendar, CalendarException

def meeting_day(db, rid, day):
    exception=db.scalar(select(CalendarException).where(CalendarException.halaqa_id==rid,CalendarException.day==day))
    if exception: return exception.held
    row=db.get(RingCalendar,rid)
    # Missing calendar means unknown, never an automatic absence warning.
    return row is not None and day.weekday() in json.loads(row.weekdays_json)

def resolved_attendance(db,sid,day,value):
    from app.models import AbsenceExcuse
    if value=='absent' and db.scalar(select(AbsenceExcuse.id).where(AbsenceExcuse.student_id==sid,AbsenceExcuse.day==day,AbsenceExcuse.status=='approved')):
        return 'excused'
    return value
