"""Version 15 workflows; new tables preserve the installed v14 schema."""
from datetime import datetime, date
from sqlalchemy import Integer, String, Text, Date, DateTime, ForeignKey, UniqueConstraint, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base

class QuranRecord(Base):
    __tablename__='quran_records'
    __table_args__=(UniqueConstraint('student_id','surah'),)
    id: Mapped[int]=mapped_column(primary_key=True)
    student_id: Mapped[int]=mapped_column(ForeignKey('halaqa_students.id'),index=True)
    surah: Mapped[int]=mapped_column(Integer)
    status: Mapped[str]=mapped_column(String(24))
    notes: Mapped[str]=mapped_column(Text,default='')
    approved_by: Mapped[int]=mapped_column(ForeignKey('users.id'))
    updated_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class RingCalendar(Base):
    __tablename__='ring_calendars'
    halaqa_id: Mapped[int]=mapped_column(ForeignKey('halaqat.id'),primary_key=True)
    weekdays_json: Mapped[str]=mapped_column(Text,default='[]')
    time_text: Mapped[str]=mapped_column(String(100),default='')

class CalendarException(Base):
    __tablename__='ring_calendar_exceptions'
    __table_args__=(UniqueConstraint('halaqa_id','day'),)
    id: Mapped[int]=mapped_column(primary_key=True)
    halaqa_id: Mapped[int]=mapped_column(ForeignKey('halaqat.id'),index=True)
    day: Mapped[date]=mapped_column(Date)
    held: Mapped[bool]=mapped_column(Boolean,default=False)
    reason: Mapped[str]=mapped_column(String(500),default='')

class AbsenceExcuse(Base):
    __tablename__='absence_excuses'
    __table_args__=(UniqueConstraint('student_id','day'),)
    id: Mapped[int]=mapped_column(primary_key=True)
    student_id: Mapped[int]=mapped_column(ForeignKey('halaqa_students.id'),index=True)
    day: Mapped[date]=mapped_column(Date)
    reason: Mapped[str]=mapped_column(Text)
    status: Mapped[str]=mapped_column(String(20),default='pending')
    submitted_by: Mapped[int]=mapped_column(ForeignKey('users.id'))
    reviewed_by: Mapped[int | None]=mapped_column(ForeignKey('users.id'),nullable=True)
    review_note: Mapped[str]=mapped_column(Text,default='')
    updated_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class StudentMessage(Base):
    __tablename__='student_messages'
    id: Mapped[int]=mapped_column(primary_key=True)
    student_id: Mapped[int]=mapped_column(ForeignKey('halaqa_students.id'),index=True)
    sender_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    body: Mapped[str]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class ThreadRead(Base):
    __tablename__='student_thread_reads'
    __table_args__=(UniqueConstraint('student_id','user_id'),)
    id: Mapped[int]=mapped_column(primary_key=True)
    student_id: Mapped[int]=mapped_column(ForeignKey('halaqa_students.id'))
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    last_id: Mapped[int]=mapped_column(Integer,default=0)

class Announcement(Base):
    __tablename__='ring_announcements'
    id: Mapped[int]=mapped_column(primary_key=True)
    mosque_id: Mapped[int]=mapped_column(ForeignKey('mosques.id'),index=True)
    halaqa_id: Mapped[int | None]=mapped_column(ForeignKey('halaqat.id'),nullable=True)
    title: Mapped[str]=mapped_column(String(180))
    body: Mapped[str]=mapped_column(Text)
    expires: Mapped[date | None]=mapped_column(Date,nullable=True)
    active: Mapped[bool]=mapped_column(Boolean,default=True)
    created_by: Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class OrganizedExam(Base):
    __tablename__='organized_exams'
    id: Mapped[int]=mapped_column(primary_key=True)
    student_id: Mapped[int]=mapped_column(ForeignKey('halaqa_students.id'),index=True)
    title: Mapped[str]=mapped_column(String(180))
    syllabus: Mapped[str]=mapped_column(Text)
    due: Mapped[date]=mapped_column(Date)
    repeat_days: Mapped[int]=mapped_column(Integer,default=0)
    pass_percent: Mapped[float]=mapped_column(Float,default=70)
    criteria_json: Mapped[str]=mapped_column(Text)
    status: Mapped[str]=mapped_column(String(20),default='scheduled')
    next_exam_id: Mapped[int | None]=mapped_column(ForeignKey('organized_exams.id'),nullable=True)
    created_by: Mapped[int]=mapped_column(ForeignKey('users.id'))

class OrganizedResult(Base):
    __tablename__='organized_exam_results'
    exam_id: Mapped[int]=mapped_column(ForeignKey('organized_exams.id'),primary_key=True)
    day: Mapped[date]=mapped_column(Date)
    scores_json: Mapped[str]=mapped_column(Text)
    notes: Mapped[str]=mapped_column(Text,default='')
    passed: Mapped[bool]=mapped_column(Boolean)
    legacy_exam_id: Mapped[int]=mapped_column(ForeignKey('student_exams.id'))
    assessed_by: Mapped[int]=mapped_column(ForeignKey('users.id'))

class ImportPreview(Base):
    __tablename__='student_import_previews'
    token: Mapped[str]=mapped_column(String(64),primary_key=True)
    mosque_id: Mapped[int]=mapped_column(ForeignKey('mosques.id'))
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    halaqa_id: Mapped[int]=mapped_column(ForeignKey('halaqat.id'))
    rows_json: Mapped[str]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    consumed: Mapped[bool]=mapped_column(Boolean,default=False)
