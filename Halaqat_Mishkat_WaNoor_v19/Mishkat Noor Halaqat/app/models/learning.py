from datetime import date,datetime
from sqlalchemy import Integer,String,Text,Date,DateTime,ForeignKey,UniqueConstraint,Boolean,Float
from sqlalchemy.orm import Mapped,mapped_column
from app.db.session import Base

class CompletionGoal(Base):
    __tablename__='completion_goals'
    student_id:Mapped[int]=mapped_column(ForeignKey('halaqa_students.id'),primary_key=True)
    title:Mapped[str]=mapped_column(String(180))
    unit:Mapped[str]=mapped_column(String(20))
    target:Mapped[float]=mapped_column(Float)
    completed:Mapped[float]=mapped_column(Float,default=0)
    start:Mapped[date]=mapped_column(Date)
    deadline:Mapped[date]=mapped_column(Date)
    notes:Mapped[str]=mapped_column(Text,default='')
    updated_by:Mapped[int]=mapped_column(ForeignKey('users.id'))

class RecitationMistake(Base):
    __tablename__='recitation_mistakes'
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    student_id:Mapped[int]=mapped_column(ForeignKey('halaqa_students.id'),index=True)
    day:Mapped[date]=mapped_column(Date)
    surah:Mapped[int]=mapped_column(Integer)
    ayah:Mapped[int]=mapped_column(Integer)
    kind:Mapped[str]=mapped_column(String(30))
    notes:Mapped[str]=mapped_column(Text,default='')
    resolved:Mapped[bool]=mapped_column(Boolean,default=False)
    recorded_by:Mapped[int]=mapped_column(ForeignKey('users.id'))

class HomePractice(Base):
    __tablename__='home_practices'
    __table_args__=(UniqueConstraint('assignment_id','day',name='uq_home_assignment_day'),)
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    student_id:Mapped[int]=mapped_column(ForeignKey('halaqa_students.id'),index=True)
    assignment_id:Mapped[int]=mapped_column(ForeignKey('student_assignments.id'))
    day:Mapped[date]=mapped_column(Date)
    minutes:Mapped[int]=mapped_column(Integer)
    notes:Mapped[str]=mapped_column(Text,default='')
    guardian_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class RecitationTurn(Base):
    __tablename__='recitation_turns'
    __table_args__=(UniqueConstraint('halaqa_id','day','student_id',name='uq_turn_student'),)
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    halaqa_id:Mapped[int]=mapped_column(ForeignKey('halaqat.id'),index=True)
    student_id:Mapped[int]=mapped_column(ForeignKey('halaqa_students.id'),index=True)
    day:Mapped[date]=mapped_column(Date)
    position:Mapped[int]=mapped_column(Integer)
    status:Mapped[str]=mapped_column(String(20),default='waiting')

class SubstituteTeacher(Base):
    __tablename__='substitute_teachers'
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    halaqa_id:Mapped[int]=mapped_column(ForeignKey('halaqat.id'),index=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    start:Mapped[date]=mapped_column(Date)
    end:Mapped[date]=mapped_column(Date)
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    assigned_by:Mapped[int]=mapped_column(ForeignKey('users.id'))

class Competition(Base):
    __tablename__='learning_competitions'
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    halaqa_id:Mapped[int]=mapped_column(ForeignKey('halaqat.id'),index=True)
    title:Mapped[str]=mapped_column(String(180))
    mode:Mapped[str]=mapped_column(String(20))
    unit:Mapped[str]=mapped_column(String(60))
    target:Mapped[float]=mapped_column(Float)
    start:Mapped[date]=mapped_column(Date)
    end:Mapped[date]=mapped_column(Date)
    reward:Mapped[str]=mapped_column(String(500),default='')
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    created_by:Mapped[int]=mapped_column(ForeignKey('users.id'))

class CompetitionEntry(Base):
    __tablename__='competition_entries'
    __table_args__=(UniqueConstraint('competition_id','student_id',name='uq_competition_student'),)
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    competition_id:Mapped[int]=mapped_column(ForeignKey('learning_competitions.id'))
    student_id:Mapped[int]=mapped_column(ForeignKey('halaqa_students.id'),index=True)
    value:Mapped[float]=mapped_column(Float,default=0)
    notes:Mapped[str]=mapped_column(Text,default='')
    status:Mapped[str]=mapped_column(String(20),default='empty')
    reviewed_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    awarded:Mapped[bool]=mapped_column(Boolean,default=False)
