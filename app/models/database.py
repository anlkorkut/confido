from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import datetime

from app.config import settings

Base = declarative_base()

class Patient(Base):
    __tablename__ = "patients"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20))
    email = Column(String(100))
    date_of_birth = Column(DateTime)
    insurance_provider = Column(String(100))
    policy_number = Column(String(50))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    appointments = relationship("Appointment", back_populates="patient")
    
class Appointment(Base):
    __tablename__ = "appointments"
    
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    doctor_name = Column(String(100))
    appointment_date = Column(DateTime)
    reason = Column(Text)
    status = Column(String(20), default="scheduled")
    confirmation_number = Column(String(20), unique=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    patient = relationship("Patient", back_populates="appointments")
    
class InsuranceProvider(Base):
    __tablename__ = "insurance_providers"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    accepted = Column(Boolean, default=True)
    coverage_details = Column(Text)
    
class ConversationLog(Base):
    __tablename__ = "conversation_logs"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String(100))
    user_input = Column(Text)
    ai_response = Column(Text)
    intent = Column(String(50))
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

# Database connection
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Function to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()