import logging
import uuid
from typing import Dict, List
from datetime import datetime

from app.services.openai_wrapper import OpenAIWrapper
from app.services.healthcare_service import HealthcareService
from app.config import settings

class ConversationManager:
    def __init__(self, openai_wrapper: OpenAIWrapper, healthcare_service: HealthcareService):
        self.openai_wrapper = openai_wrapper
        self.healthcare_service = healthcare_service
        self.system_prompt = self._build_system_prompt()
        self.conversation_states = {}
        self.logger = logging.getLogger(__name__)
        
    def _build_system_prompt(self) -> str:
        """Comprehensive system prompt for healthcare assistant"""
        return f"""
        You are a professional AI voice assistant for {settings.clinic_name} healthcare facility.
        
        ROLE & OBJECTIVES:
        - Handle appointment scheduling, insurance verification, and clinic FAQs
        - Be PROACTIVE and DECISIVE in handling appointment scheduling
        - Maintain a warm, professional, and empathetic tone
        - Ask ONE question at a time and wait for responses
        - Stay focused on administrative tasks only
        
        CRITICAL MEMORY INSTRUCTIONS:
        - NEVER ask for information that the user has already provided
        - ALWAYS remember previous answers and use them in your responses
        - TRACK what information you've already collected
        - FOCUS on collecting only missing information
        - NEVER restart the conversation flow or forget previous context
        
        CONVERSATION FLOW RULES:
        1. GREETING: Always greet warmly and identify yourself as an AI assistant
        2. INTENT IDENTIFICATION: Immediately recognize appointment scheduling requests
        3. INFORMATION GATHERING: Collect ONLY missing details, one question at a time
        4. PROCESSING: Check calendar availability and IMMEDIATELY BOOK appointments when slots are available
        5. CONFIRMATION: Clearly confirm booked appointments with all details
        6. CLOSING: End courteously with next steps
        
        APPOINTMENT SCHEDULING - CRITICAL INSTRUCTIONS:
        - When a user mentions scheduling an appointment, IMMEDIATELY identify this as an appointment request
        - Extract name, preferred date/time, and reason for visit from the initial request
        - If the user has already provided their name, NEVER ask for it again
        - If the user has already provided a date/time, NEVER ask for it again
        - If you have enough information, check availability and BOOK THE APPOINTMENT
        - If an available slot is found, CONFIRM THE BOOKING and provide the confirmation details
        - Do not ask for intent again if appointment scheduling intent is already clear
        - Assume the user wants to book an appointment if they mention scheduling, booking, or making an appointment
        
        BEHAVIORAL GUIDELINES:
        - Never provide medical advice
        - If asked about unrelated topics, politely redirect
        - Handle misunderstandings gracefully
        - Offer human transfer for complex issues
        - Keep responses concise and clear
        
        APPOINTMENT SCHEDULING REQUIREMENTS:
        - Patient name and contact information
        - Preferred date and time
        - Reason for visit or doctor preference
        
        INSURANCE VERIFICATION REQUIREMENTS:
        - Patient name and date of birth
        - Insurance provider and policy number
        - Specific procedure or service to verify
        
        Remember: You are the first point of contact - create a positive experience!
        """
            
    async def process_conversation_turn(self, session_id: str, user_input: str) -> str:
        """Process a single conversation turn"""
        # Create a new session if it doesn't exist
        if session_id not in self.conversation_states:
            session_id = session_id or str(uuid.uuid4())
            self.conversation_states[session_id] = {
                "messages": [
                    {"role": "system", "content": self.system_prompt}
                ],
                "intent": None,
                "collected_data": {},
                "last_updated": datetime.utcnow(),
                "appointment_booked": False,
                "processing_stage": "initial"
            }
            
        # Add user message to conversation history
        self.conversation_states[session_id]["messages"].append({"role": "user", "content": user_input})
        
        # Determine intent if not already set
        if not self.conversation_states[session_id]["intent"]:
            # Check for appointment keywords in the message
            if any(word in user_input.lower() for word in ["appointment", "schedule", "book", "visit", "see doctor", "checkup"]):
                intent = "appointment"
            else:
                intent = await self._determine_intent(user_input)
            
            self.conversation_states[session_id]["intent"] = intent
            self.logger.info("Identified intent: %s for session %s", intent, session_id)
            
            # Add intent confirmation to conversation
            if intent == "appointment":
                self.conversation_states[session_id]["messages"].append({
                    "role": "system", 
                    "content": "The user wants to schedule an appointment. Extract all relevant information and proceed with booking."
                })
        
        # Process based on intent
        if self.conversation_states[session_id]["intent"] == "appointment":
            # Check if appointment is already booked
            if not self.conversation_states[session_id].get("appointment_booked", False):
                # Extract appointment info from all messages so far
                appointment_info = await self._extract_appointment_info(self.conversation_states[session_id]["messages"])
                
                # Update collected data
                self.conversation_states[session_id]["collected_data"].update(appointment_info)
                
                # Log the current state of collected data
                self.logger.info("Current appointment data: %s", self.conversation_states[session_id]["collected_data"])
                
                # Check if we have all required information for booking
                required_fields = ["patient_name", "date", "time"]
                has_required_fields = all(field in self.conversation_states[session_id]["collected_data"] for field in required_fields)
                
                # If we have enough information to check availability and book
                if has_required_fields:
                    # Check availability
                    availability = await self.healthcare_service.check_appointment_availability(
                        date=self.conversation_states[session_id]["collected_data"].get("date"),
                        time=self.conversation_states[session_id]["collected_data"].get("time"),
                        doctor=self.conversation_states[session_id]["collected_data"].get("doctor")
                    )
                    
                    # Add availability context to the conversation
                    self.conversation_states[session_id]["messages"].append({
                        "role": "system", 
                        "content": f"Available appointment slots: {availability}"
                    })
                    
                    # If slots are available, book the first available slot
                    if availability.get("available_slots") and len(availability["available_slots"]) > 0:
                        slot = availability["available_slots"][0]
                        
                        # Get patient name and contact from collected data
                        patient_name = self.conversation_states[session_id]["collected_data"].get("patient_name", "Patient")
                        contact = self.conversation_states[session_id]["collected_data"].get("contact", "555-123-4567")
                        
                        # Book the appointment
                        booking_result = await self.healthcare_service.book_appointment(
                            patient_info={
                                "name": patient_name,
                                "contact": contact
                            },
                            appointment_details={
                                "doctor": slot["doctor"],
                                "date": slot["date"],
                                "time": slot["time"],
                                "reason": self.conversation_states[session_id]["collected_data"].get("reason", "General checkup")
                            }
                        )
                        
                        # Mark appointment as booked
                        self.conversation_states[session_id]["appointment_booked"] = True
                        self.conversation_states[session_id]["processing_stage"] = "booked"
                        
                        # Add booking confirmation to conversation
                        self.conversation_states[session_id]["messages"].append({
                            "role": "system", 
                            "content": f"Appointment booked successfully: {booking_result}. Make sure to clearly confirm the booking details to the user including patient name, doctor, date, time, and confirmation number."
                        })
                        
                        # Update collected data with booking details
                        self.conversation_states[session_id]["collected_data"]["booking"] = booking_result
                    else:
                        # No slots available
                        self.conversation_states[session_id]["messages"].append({
                            "role": "system", 
                            "content": "No appointment slots available for the requested time. Suggest alternative times."
                        })
                else:
                    # We don't have all required information yet
                    missing_fields = [field for field in required_fields if field not in self.conversation_states[session_id]["collected_data"]]
                    self.conversation_states[session_id]["messages"].append({
                        "role": "system", 
                        "content": f"Still need to collect: {', '.join(missing_fields)}. Ask for this information politely."
                    })
                
        elif self.conversation_states[session_id]["intent"] == "insurance":
            # Extract insurance info if enough context is available
            insurance_info = self._extract_insurance_info(self.conversation_states[session_id]["messages"])
            if insurance_info and len(insurance_info) >= 3:  # If we have enough information
                # Verify insurance
                verification = await self.healthcare_service.verify_insurance(
                    patient_info={"name": insurance_info.get("patient_name", "Patient")},
                    insurance_details={
                        "provider": insurance_info.get("provider"),
                        "policy_number": insurance_info.get("policy_number"),
                        "procedure": insurance_info.get("procedure")
                    }
                )
                
                # Add this context to the conversation
                self.conversation_states[session_id]["messages"].append({
                    "role": "system", 
                    "content": f"Insurance verification result: {verification}"
                })
                
                # Update collected data
                self.conversation_states[session_id]["collected_data"].update(insurance_info)
                
        elif self.conversation_states[session_id]["intent"] == "faq":
            # Extract the specific FAQ query
            faq_query = self._extract_faq_query(user_input)
            if faq_query:
                # Get clinic info
                clinic_info = await self.healthcare_service.get_clinic_info(faq_query)
                
                # Add this context to the conversation
                self.conversation_states[session_id]["messages"].append({
                    "role": "system", 
                    "content": f"Clinic information: {clinic_info}"
                })
        
        # Generate AI response
        response = await self.openai_wrapper.chat_complete(
            messages=self.conversation_states[session_id]["messages"]
        )
        
        # Add AI response to conversation history
        self.conversation_states[session_id]["messages"].append({"role": "assistant", "content": response})
        
        # Update last updated timestamp
        self.conversation_states[session_id]["last_updated"] = datetime.utcnow()
        
        return response
    
    async def _determine_intent(self, user_input: str) -> str:
        """Classify user intent (appointment, insurance, faq)"""
        # Use OpenAI to classify intent
        messages = [
            {"role": "system", "content": "You are a healthcare intent classifier. Classify the user's message into one of these categories: 'appointment', 'insurance', 'faq', or 'other'. Respond with ONLY the category name."}, 
            {"role": "user", "content": user_input}
        ]
        
        intent = await self.openai_wrapper.chat_complete(messages=messages)
        intent = intent.lower().strip()
        
        # Map to valid intents or default to faq
        intent_map = {
            "appointment": "appointment",
            "insurance": "insurance",
            "faq": "faq",
            "other": "faq"
        }
        
        return intent_map.get(intent, "faq")
    
    async def _extract_appointment_info(self, conversation_history: List) -> Dict:
        """Extract appointment details from conversation using OpenAI"""
        # Combine all user messages
        user_messages = " ".join([msg["content"] for msg in conversation_history if msg["role"] == "user"])
        
        # Use OpenAI to extract structured information with a stronger prompt
        extraction_prompt = [
            {"role": "system", "content": """You are an AI assistant that extracts appointment information from conversations.
                Extract ALL of the following fields if present in ANY part of the conversation: 
                - patient_name (the full name of the patient)
                - contact (phone number or email)
                - date (convert relative dates like 'tomorrow', 'next week' to actual dates)
                - time (specific times or periods like morning, afternoon, evening)
                - doctor (any doctor name mentioned)
                - reason (reason for the appointment)
                - insurance (insurance provider name if mentioned)
                
                Be THOROUGH and extract information from the ENTIRE conversation history.
                If information appears multiple times, use the most recent or most specific mention.
                Respond with ONLY a JSON object containing these fields. If a field is not present, exclude it."""},
            {"role": "user", "content": user_messages}
        ]
        
        try:
            extraction_result = await self.openai_wrapper.chat_complete(messages=extraction_prompt)
            
            # Try to parse the JSON response
            import json
            try:
                appointment_info = json.loads(extraction_result)
                self.logger.info("Extracted appointment info: %s", appointment_info)
                
                # Ensure we have at least some basic information
                if not appointment_info:
                    appointment_info = {}
                    
                # Set defaults for demo if missing
                if "date" not in appointment_info and "tomorrow" in user_messages.lower():
                    appointment_info["date"] = "tomorrow"
                elif "date" not in appointment_info and "next week" in user_messages.lower():
                    appointment_info["date"] = "next week"
                elif "date" not in appointment_info:
                    # Default to tomorrow for demo purposes
                    from datetime import datetime, timedelta
                    tomorrow = datetime.now() + timedelta(days=1)
                    appointment_info["date"] = tomorrow.strftime("%Y-%m-%d")
                    
                if "time" not in appointment_info:
                    if "morning" in user_messages.lower():
                        appointment_info["time"] = "09:00"
                    elif "afternoon" in user_messages.lower():
                        appointment_info["time"] = "14:00"
                    elif "evening" in user_messages.lower():
                        appointment_info["time"] = "17:00"
                    else:
                        # Default to morning for demo purposes
                        appointment_info["time"] = "10:00"
                        
                if "doctor" not in appointment_info:
                    if "dr." in user_messages.lower() or "doctor" in user_messages.lower():
                        # Try to extract doctor name with simple pattern matching
                        import re
                        doctor_match = re.search(r"dr\.?\s+([a-z]+)", user_messages.lower())
                        if doctor_match:
                            doctor_name = doctor_match.group(1)
                            appointment_info["doctor"] = f"Dr. {doctor_name.title()}"
                        else:
                            appointment_info["doctor"] = "Dr. Smith"  # Default for demo
                    else:
                        appointment_info["doctor"] = "Dr. Smith"  # Default for demo
                        
                # Ensure we have a patient name
                if "patient_name" not in appointment_info:
                    # Try to extract a name from the conversation
                    import re
                    # Look for phrases like "my name is John Smith" or "this is John Smith"
                    name_match = re.search(r"(my name is|this is|i am|i'm)\s+([a-z\s]+)", user_messages.lower())
                    if name_match:
                        patient_name = name_match.group(2).strip().title()
                        appointment_info["patient_name"] = patient_name
                    else:
                        appointment_info["patient_name"] = "Patient"  # Default for demo
                        
                # Ensure we have contact information
                if "contact" not in appointment_info:
                    # Try to extract phone number with pattern matching
                    import re
                    phone_match = re.search(r"(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})", user_messages)
                    if phone_match:
                        appointment_info["contact"] = phone_match.group(1)
                    else:
                        appointment_info["contact"] = "555-123-4567"  # Default for demo
                    
                return appointment_info
                
            except json.JSONDecodeError:
                self.logger.warning("Failed to parse extraction result as JSON: %s", extraction_result)
        except Exception as e:
            self.logger.error("Error extracting appointment info: %s", str(e))
            
        # Fallback to basic extraction
        appointment_info = {}
        
        # Very basic extraction as fallback
        if "tomorrow" in user_messages.lower():
            appointment_info["date"] = "tomorrow"
        elif "next week" in user_messages.lower():
            appointment_info["date"] = "next week"
        else:
            # Default to tomorrow for demo purposes
            from datetime import datetime, timedelta
            tomorrow = datetime.now() + timedelta(days=1)
            appointment_info["date"] = tomorrow.strftime("%Y-%m-%d")
            
        if "morning" in user_messages.lower():
            appointment_info["time"] = "09:00"
        elif "afternoon" in user_messages.lower():
            appointment_info["time"] = "14:00"
        elif "evening" in user_messages.lower():
            appointment_info["time"] = "17:00"
        else:
            # Default to morning for demo purposes
            appointment_info["time"] = "10:00"
            
        # Try to extract doctor name with simple pattern matching
        import re
        doctor_match = re.search(r"dr\.?\s+([a-z]+)", user_messages.lower())
        if doctor_match:
            doctor_name = doctor_match.group(1)
            appointment_info["doctor"] = f"Dr. {doctor_name.title()}"
        else:
            appointment_info["doctor"] = "Dr. Smith"  # Default for demo
            
        # Try to extract a name from the conversation
        name_match = re.search(r"(my name is|this is|i am|i'm)\s+([a-z\s]+)", user_messages.lower())
        if name_match:
            patient_name = name_match.group(2).strip().title()
            appointment_info["patient_name"] = patient_name
        else:
            appointment_info["patient_name"] = "Patient"  # Default for demo
            
        # Try to extract phone number
        phone_match = re.search(r"(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})", user_messages)
        if phone_match:
            appointment_info["contact"] = phone_match.group(1)
        else:
            appointment_info["contact"] = "555-123-4567"  # Default for demo
            
        return appointment_info
    
    def _extract_insurance_info(self, conversation_history: List) -> Dict:
        """Extract insurance details from conversation"""
        # Simplified extraction logic - in production, use function calling with OpenAI
        insurance_info = {}
        
        # Combine all user messages
        user_messages = " ".join([msg["content"] for msg in conversation_history if msg["role"] == "user"])
        
        # Very basic extraction (would be more sophisticated in production)
        if "blue cross" in user_messages.lower():
            insurance_info["provider"] = "Blue Cross Blue Shield"
        elif "aetna" in user_messages.lower():
            insurance_info["provider"] = "Aetna"
        elif "cigna" in user_messages.lower():
            insurance_info["provider"] = "Cigna"
        elif "united" in user_messages.lower():
            insurance_info["provider"] = "UnitedHealthcare"
            
        # Extract policy number (simplified)
        if "policy" in user_messages.lower() and "number" in user_messages.lower():
            # This is a simplification - in production, use regex or NER
            insurance_info["policy_number"] = "123456789"  # Default for demo
            
        # Extract procedure (simplified)
        if "checkup" in user_messages.lower():
            insurance_info["procedure"] = "annual checkup"
        elif "x-ray" in user_messages.lower():
            insurance_info["procedure"] = "x-ray"
        elif "surgery" in user_messages.lower():
            insurance_info["procedure"] = "surgery"
            
        return insurance_info
    
    def _extract_faq_query(self, user_input: str) -> str:
        """Extract FAQ query type from user input"""
        user_input = user_input.lower()
        
        if any(word in user_input for word in ["hour", "open", "close", "time"]):
            return "hours"
        elif any(word in user_input for word in ["location", "address", "direction", "where"]):
            return "location"
        elif any(word in user_input for word in ["service", "offer", "provide", "treatment"]):
            return "services"
        elif any(word in user_input for word in ["doctor", "physician", "specialist", "provider"]):
            return "doctors"
        else:
            return "general"