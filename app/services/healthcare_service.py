import logging
import random
import string
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from app.models.database import Patient, Appointment, InsuranceProvider

class HealthcareService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.logger = logging.getLogger(__name__)
        
    async def check_appointment_availability(self, date: str, time: str, doctor: Optional[str] = None) -> Dict:
        """Check calendar availability and return options"""
        self.logger.info(f"Checking appointment availability for date={date}, time={time}, doctor={doctor}")
        
        # Simulate calendar lookup
        available_slots = []
        
        # Convert relative dates to actual dates
        target_date = self._parse_relative_date(date)
        
        # Generate time slots based on the requested time period
        time_slots = self._generate_time_slots(time)
        
        # Filter by doctor if specified
        doctors = ["Dr. Smith", "Dr. Johnson", "Dr. Williams", "Dr. Brown"]
        if doctor:
            available_doctors = [d for d in doctors if doctor.lower() in d.lower()]
            if not available_doctors:
                available_doctors = [random.choice(doctors)]
        else:
            available_doctors = doctors
            
        # Generate available slots
        for d in available_doctors:
            for t in time_slots:
                # Randomly determine if slot is available (70% chance for demo)
                if random.random() < 0.7:
                    available_slots.append({
                        "doctor": d,
                        "date": target_date.strftime("%Y-%m-%d"),
                        "time": t,
                        "available": True
                    })
        
        return {
            "requested_date": target_date.strftime("%Y-%m-%d"),
            "requested_time": time,
            "requested_doctor": doctor,
            "available_slots": available_slots[:5]  # Limit to 5 options
        }
    
    async def book_appointment(self, patient_info: Dict, appointment_details: Dict) -> Dict:
        """Book appointment and return confirmation"""
        try:
            # Check if patient exists
            patient = self._get_or_create_patient(patient_info)
            
            # Create appointment record
            confirmation_number = self._generate_confirmation_number()
            
            new_appointment = Appointment(
                patient_id=patient.id,
                doctor_name=appointment_details.get("doctor"),
                appointment_date=datetime.strptime(
                    f"{appointment_details.get('date')} {appointment_details.get('time')}", 
                    "%Y-%m-%d %H:%M"
                ),
                reason=appointment_details.get("reason"),
                status="scheduled",
                confirmation_number=confirmation_number,
                created_at=datetime.utcnow()
            )
            
            self.db.add(new_appointment)
            self.db.commit()
            
            return {
                "success": True,
                "confirmation_number": confirmation_number,
                "appointment_details": {
                    "patient_name": patient.name,
                    "doctor": new_appointment.doctor_name,
                    "date": new_appointment.appointment_date.strftime("%Y-%m-%d"),
                    "time": new_appointment.appointment_date.strftime("%H:%M"),
                    "reason": new_appointment.reason
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error booking appointment: {str(e)}")
            self.db.rollback()
            return {
                "success": False,
                "error": "Failed to book appointment"
            }
    
    async def verify_insurance(self, patient_info: Dict, insurance_details: Dict) -> Dict:
        """Verify insurance coverage"""
        self.logger.info(f"Verifying insurance for patient={patient_info.get('name')}, provider={insurance_details.get('provider')}")
        
        # Simulate insurance verification
        provider_name = insurance_details.get("provider")
        policy_number = insurance_details.get("policy_number")
        procedure = insurance_details.get("procedure")
        
        # Check if insurance provider is in our database
        provider = self._get_insurance_provider(provider_name)
        
        # If provider exists and is accepted
        if provider and provider.accepted:
            # Simulate coverage check
            coverage_percentage = random.randint(70, 100) if random.random() < 0.8 else random.randint(0, 50)
            deductible_remaining = random.randint(0, 2000)
            copay_amount = random.randint(10, 50) if coverage_percentage > 50 else random.randint(50, 200)
            authorization_required = random.random() < 0.3
            
            return {
                "is_covered": coverage_percentage > 0,
                "coverage_percentage": coverage_percentage,
                "deductible_remaining": deductible_remaining,
                "copay_amount": copay_amount,
                "authorization_required": authorization_required,
                "provider": provider_name,
                "procedure": procedure,
                "notes": f"Policy {policy_number} verified with {provider_name}."
            }
        else:
            return {
                "is_covered": False,
                "coverage_percentage": 0,
                "provider": provider_name,
                "procedure": procedure,
                "notes": f"Insurance provider {provider_name} is not accepted or policy {policy_number} could not be verified."
            }
    
    async def get_clinic_info(self, query_type: str) -> Dict:
        """Provide clinic information (hours, location, services)"""
        clinic_info = {
            "name": "Confido Health Clinic",
            "address": "123 Healthcare Ave, Medical District, CA 90210",
            "phone": "(555) 123-4567",
            "email": "info@confidohealth.com",
            "hours": {
                "Monday": "8:00 AM - 6:00 PM",
                "Tuesday": "8:00 AM - 6:00 PM",
                "Wednesday": "8:00 AM - 6:00 PM",
                "Thursday": "8:00 AM - 6:00 PM",
                "Friday": "8:00 AM - 5:00 PM",
                "Saturday": "9:00 AM - 2:00 PM",
                "Sunday": "Closed"
            },
            "services": [
                "Primary Care",
                "Preventive Medicine",
                "Pediatrics",
                "Women's Health",
                "Geriatrics",
                "Laboratory Services",
                "Vaccinations",
                "Minor Procedures"
            ],
            "doctors": [
                {"name": "Dr. Emily Smith", "specialty": "Family Medicine"},
                {"name": "Dr. Michael Johnson", "specialty": "Internal Medicine"},
                {"name": "Dr. Sarah Williams", "specialty": "Pediatrics"},
                {"name": "Dr. David Brown", "specialty": "Geriatrics"}
            ],
            "faqs": [
                {"question": "Do you accept new patients?", "answer": "Yes, we are currently accepting new patients. Please call our office to schedule an initial consultation."},
                {"question": "What insurance plans do you accept?", "answer": "We accept most major insurance plans including Blue Cross, Aetna, Cigna, and UnitedHealthcare."},
                {"question": "How do I refill my prescription?", "answer": "You can request prescription refills through our patient portal or by calling our office directly."},
                {"question": "How do I schedule a telehealth appointment?", "answer": "Telehealth appointments can be scheduled through our website or by calling our office."}
            ]
        }
        
        # Return specific information based on query type
        if query_type == "hours":
            return {"hours": clinic_info["hours"]}
        elif query_type == "location":
            return {"address": clinic_info["address"], "phone": clinic_info["phone"]}
        elif query_type == "services":
            return {"services": clinic_info["services"]}
        elif query_type == "doctors":
            return {"doctors": clinic_info["doctors"]}
        else:
            # Return general information
            return clinic_info
    
    def _generate_confirmation_number(self) -> str:
        """Generate unique appointment confirmation number"""
        # Format: LETTER + 7 digits (e.g., A1234567)
        letter = random.choice(string.ascii_uppercase)
        digits = ''.join(random.choices(string.digits, k=7))
        return f"{letter}{digits}"
    
    def _parse_relative_date(self, date_str: str) -> datetime:
        """Convert relative date strings to actual dates"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        if not date_str or date_str.lower() == "today":
            return today
        elif date_str.lower() == "tomorrow":
            return today + timedelta(days=1)
        elif date_str.lower() == "next week":
            return today + timedelta(days=7)
        elif date_str.lower() == "next month":
            # Approximate next month
            return today + timedelta(days=30)
        else:
            # Try to parse as YYYY-MM-DD
            try:
                return datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                # Default to tomorrow if parsing fails
                return today + timedelta(days=1)
    
    def _generate_time_slots(self, time_period: str) -> List[str]:
        """Generate time slots based on the requested time period"""
        if time_period.lower() == "morning":
            return ["8:00", "9:00", "10:00", "11:00"]
        elif time_period.lower() == "afternoon":
            return ["12:00", "13:00", "14:00", "15:00"]
        elif time_period.lower() == "evening":
            return ["16:00", "17:00", "18:00"]
        else:
            # Return all time slots
            return [f"{h}:00" for h in range(8, 19)]
    
    def _get_or_create_patient(self, patient_info: Dict) -> Patient:
        """Get existing patient or create a new one"""
        # Check if patient exists by name and either email or phone
        name = patient_info.get("name")
        email = patient_info.get("email")
        phone = patient_info.get("phone")
        
        query = self.db.query(Patient).filter(Patient.name == name)
        if email:
            query = query.filter(Patient.email == email)
        elif phone:
            query = query.filter(Patient.phone == phone)
            
        patient = query.first()
        
        if not patient:
            # Create new patient
            patient = Patient(
                name=name,
                email=email,
                phone=phone,
                date_of_birth=patient_info.get("date_of_birth"),
                insurance_provider=patient_info.get("insurance_provider"),
                policy_number=patient_info.get("policy_number"),
                created_at=datetime.utcnow()
            )
            self.db.add(patient)
            self.db.commit()
            
        return patient
    
    def _get_insurance_provider(self, provider_name: str) -> Optional[InsuranceProvider]:
        """Get insurance provider from database"""
        if not provider_name:
            return None
            
        # Try to find by name
        provider = self.db.query(InsuranceProvider).filter(
            InsuranceProvider.name.ilike(f"%{provider_name}%")
        ).first()
        
        if not provider:
            # For demo purposes, create a new provider with 80% chance of being accepted
            accepted = random.random() < 0.8
            provider = InsuranceProvider(
                name=provider_name,
                accepted=accepted,
                coverage_details="Standard coverage for most procedures."
            )
            self.db.add(provider)
            self.db.commit()
            
        return provider