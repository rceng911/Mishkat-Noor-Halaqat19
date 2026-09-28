"""Additive records for learning support, offline synchronization and delivery."""
from datetime import datetime, date
from sqlalchemy import String, Text, ForeignKey, Date, DateTime, Boolean, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base

class JuzMastery(Base):
    __tablename__='juz_mastery'
    __table_args__=(UniqueConstraint('student_id','juz'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    student_id:Mapped[int]=mapped_column(ForeignKey('halaqa_students.id'))
    juz:Mapped[int]=mapped_column(Integer)
    status:Mapped[str]=mapped_column(String(24))
    notes:Mapped[str]=mapped_column(Text,default='')
    approved_by:Mapped[int]=mapped_column(ForeignKey('users.id'))

class ReviewSchedule(Base):
    __tablename__='review_schedules'
    __table_args__=(UniqueConstraint('student_id','surah'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    student_id:Mapped[int]=mapped_column(ForeignKey('halaqa_students.id'))
    surah:Mapped[int]=mapped_column(Integer)
    last_review:Mapped[date|None]=mapped_column(Date,nullable=True)
    due:Mapped[date]=mapped_column(Date)
    interval:Mapped[int]=mapped_column(Integer,default=1)
    assignment_id:Mapped[int|None]=mapped_column(ForeignKey('student_assignments.id'),nullable=True)

class SupportPlan(Base):
    __tablename__='support_plans'
    id:Mapped[int]=mapped_column(primary_key=True)
    student_id:Mapped[int]=mapped_column(ForeignKey('halaqa_students.id'),index=True)
    title:Mapped[str]=mapped_column(String(180))
    start:Mapped[date]=mapped_column(Date)
    end:Mapped[date]=mapped_column(Date)
    tasks_json:Mapped[str]=mapped_column(Text)
    status:Mapped[str]=mapped_column(String(20),default='active')
    outcome:Mapped[str]=mapped_column(Text,default='')
    created_by:Mapped[int]=mapped_column(ForeignKey('users.id'))

class ExamBooking(Base):
    __tablename__='exam_bookings'
    exam_id:Mapped[int]=mapped_column(ForeignKey('organized_exams.id'),primary_key=True)
    student_id:Mapped[int]=mapped_column(ForeignKey('halaqa_students.id'))
    examiner_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    time_text:Mapped[str]=mapped_column(String(5))
    next_level:Mapped[str]=mapped_column(String(120),default='')
    approved:Mapped[bool]=mapped_column(Boolean,default=False)

class OfflineReceipt(Base):
    __tablename__='offline_receipts'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    student_id:Mapped[int]=mapped_column(ForeignKey('halaqa_students.id'))
    digest:Mapped[str]=mapped_column(String(64))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class PushKey(Base):
    __tablename__='push_keys'
    id:Mapped[int]=mapped_column(primary_key=True)
    private:Mapped[str]=mapped_column(Text)
    public:Mapped[str]=mapped_column(Text)

class NotificationPreference(Base):
    __tablename__='notification_preferences'
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),primary_key=True)
    email:Mapped[str]=mapped_column(String(254),default='')
    verified:Mapped[bool]=mapped_column(Boolean,default=False)
    email_enabled:Mapped[bool]=mapped_column(Boolean,default=False)
    push_enabled:Mapped[bool]=mapped_column(Boolean,default=True)
    categories:Mapped[str]=mapped_column(Text,default='["attendance","progress","assignment","achievement","message","exam"]')
    code_hash:Mapped[str]=mapped_column(String(64),default='')
    code_expires:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    attempts:Mapped[int]=mapped_column(Integer,default=0)
    last_sent:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)

class PushSubscription(Base):
    __tablename__='push_subscriptions'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    endpoint_hash:Mapped[str]=mapped_column(String(64),unique=True)
    subscription:Mapped[str]=mapped_column(Text)

class NotificationJob(Base):
    __tablename__='notification_jobs'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    student_id:Mapped[int|None]=mapped_column(ForeignKey('halaqa_students.id'),nullable=True)
    category:Mapped[str]=mapped_column(String(30))
    channel:Mapped[str]=mapped_column(String(10))
    destination:Mapped[str]=mapped_column(Text)
    body:Mapped[str]=mapped_column(Text)
    status:Mapped[str]=mapped_column(String(20),default='pending')
    attempts:Mapped[int]=mapped_column(Integer,default=0)
    available_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    error:Mapped[str]=mapped_column(String(100),default='')
