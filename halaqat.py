"""Persistent Quran-circle data and controlled account requests.

These tables deliberately keep student data separate from the mosque display
records.  Every row is scoped to a mosque and all account creation is audited
through the existing owner/session boundary.
"""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Halaqa(Base):
    __tablename__ = "halaqat"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mosque_id: Mapped[int] = mapped_column(ForeignKey("mosques.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    schedule: Mapped[str] = mapped_column(String(500), default="")
    supervisor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HalaqaTeacher(Base):
    __tablename__ = "halaqa_teachers"
    __table_args__ = (UniqueConstraint("halaqa_id", "user_id", name="uq_halaqa_teacher"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    halaqa_id: Mapped[int] = mapped_column(ForeignKey("halaqat.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HalaqaSupervisor(Base):
    __tablename__ = "halaqa_supervisors"
    __table_args__ = (UniqueConstraint("halaqa_id", "user_id", name="uq_halaqa_supervisor"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    halaqa_id: Mapped[int] = mapped_column(ForeignKey("halaqat.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HalaqaStudent(Base):
    __tablename__ = "halaqa_students"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    halaqa_id: Mapped[int] = mapped_column(ForeignKey("halaqat.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(180))
    recipient_type: Mapped[str] = mapped_column(String(20), default="guardian")
    guardian_name: Mapped[str] = mapped_column(String(180), default="")
    guardian_phone: Mapped[str] = mapped_column(String(40), default="")
    guardian_relation: Mapped[str] = mapped_column(String(60), default="")
    national_id: Mapped[str] = mapped_column(String(30), default="")
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    school_grade: Mapped[str] = mapped_column(String(120), default="")
    current_memorization: Mapped[str] = mapped_column(String(250), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    level: Mapped[str] = mapped_column(String(120), default="مبتدئ")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HalaqaAccountRequest(Base):
    __tablename__ = "halaqa_account_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mosque_id: Mapped[int] = mapped_column(ForeignKey("mosques.id"), index=True)
    request_type: Mapped[str] = mapped_column(String(20), index=True)  # teacher | student
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    halaqa_id: Mapped[int | None] = mapped_column(ForeignKey("halaqat.id"), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(180))
    recipient_type: Mapped[str] = mapped_column(String(20), default="guardian")
    review_note: Mapped[str] = mapped_column(Text, default="")
    requested_username: Mapped[str] = mapped_column(String(80), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    guardian_name: Mapped[str] = mapped_column(String(180), default="")
    guardian_phone: Mapped[str] = mapped_column(String(40), default="")
    guardian_relation: Mapped[str] = mapped_column(String(60), default="")
    national_id: Mapped[str] = mapped_column(String(30), default="")
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    school_grade: Mapped[str] = mapped_column(String(120), default="")
    current_memorization: Mapped[str] = mapped_column(String(250), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HalaqaProgress(Base):
    __tablename__ = "halaqa_progress"
    __table_args__ = (UniqueConstraint("student_id", "day", name="uq_halaqa_progress_day"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("halaqa_students.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    attendance: Mapped[str] = mapped_column(String(20), default="present")
    memorized: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    memorized_amount: Mapped[float] = mapped_column(Float, default=0)
    memorized_unit: Mapped[str] = mapped_column(String(20), default="page")
    revision_amount: Mapped[float] = mapped_column(Float, default=0)
    revision_unit: Mapped[str] = mapped_column(String(20), default="page")
    memorization_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tajweed_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mistakes: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class StudentPlan(Base):
    __tablename__ = "student_plans"
    student_id: Mapped[int] = mapped_column(ForeignKey("halaqa_students.id"), primary_key=True)
    memorization_unit: Mapped[str] = mapped_column(String(20), default="page")
    memorization_amount: Mapped[float] = mapped_column(Float, default=1)
    revision_unit: Mapped[str] = mapped_column(String(20), default="page")
    revision_amount: Mapped[float] = mapped_column(Float, default=2)
    sessions_per_week: Mapped[int] = mapped_column(Integer, default=5)
    start_surah: Mapped[str] = mapped_column(String(120), default="")
    start_ayah: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_surah: Mapped[str] = mapped_column(String(120), default="")
    end_ayah: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class StudentExam(Base):
    __tablename__ = "student_exams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("halaqa_students.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(180))
    score: Mapped[float] = mapped_column(Float)
    total: Mapped[float] = mapped_column(Float)
    next_level: Mapped[str] = mapped_column(String(120), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class StudentCertificate(Base):
    __tablename__ = "student_certificates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("halaqa_students.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    achievement: Mapped[str] = mapped_column(Text)
    memorization_scope: Mapped[str] = mapped_column(String(250), default="")
    mastery_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    student_name: Mapped[str] = mapped_column(String(180), default="")
    student_national_id: Mapped[str] = mapped_column(String(30), default="")
    issued_on: Mapped[date] = mapped_column(Date)
    issued_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
