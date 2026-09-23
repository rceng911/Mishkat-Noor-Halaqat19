from datetime import datetime, date
from sqlalchemy import Integer, String, Text, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class Assignment(Base):
    __tablename__ = 'student_assignments'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('halaqa_students.id'), index=True)
    due: Mapped[date] = mapped_column(Date)
    memorization: Mapped[str] = mapped_column(Text, default='')
    revision: Mapped[str] = mapped_column(Text, default='')
    instructions: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(20), default='pending')
    result_note: Mapped[str] = mapped_column(Text, default='')
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AlertRead(Base):
    __tablename__ = 'student_alert_reads'
    __table_args__ = (UniqueConstraint('user_id', 'alert_key'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    alert_key: Mapped[str] = mapped_column(String(160))


class ExamAppointment(Base):
    __tablename__ = 'student_exam_appointments'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('halaqa_students.id'), index=True)
    due: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(180))
    notes: Mapped[str] = mapped_column(Text, default='')
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))


class FeatureSetting(Base):
    __tablename__ = 'halaqat_feature_settings'
    mosque_id: Mapped[int] = mapped_column(ForeignKey('mosques.id'), primary_key=True)
    settings_json: Mapped[str] = mapped_column(Text, default='{}')
