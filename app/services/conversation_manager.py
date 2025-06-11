import logging
import json
import re
import uuid
import random
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from app.services.openai_wrapper import OpenAIWrapper
from app.services.healthcare_service import HealthcareService

class ConversationManager:
    """State-based conversation manager for healthcare appointment booking"""
    
    def __init__(self, openai_wrapper: OpenAIWrapper, healthcare_service: HealthcareService):
        self.openai_wrapper = openai_wrapper
        self.healthcare_service = healthcare_service
        self.conversation_states = {}
        self.logger = logging.getLogger(__name__)
        
    def _normalize_doctor(self, raw: str) -> str:
        """Normalize doctor names to standard format (Dr. LastName)"""
        raw = raw.strip()
        raw = re.sub(r"^(Dr\.?|Doctor|Mrs\.?|Ms\.?|Mr\.?)\s+", "", raw, flags=re.I)
        # Title-case last name only
        parts = raw.split()
        last = parts[-1].capitalize()
        return f"Dr. {last}"
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for the conversation"""
        return """
You are a polite, efficient voice receptionist for Acme Family Clinic.  
Your goal is to book appointments in as few conversational turns as possible, without ever asking the same question twice.

If availability_checked is true, never say "I will check availability."
Immediately inform the caller of the result (is_available) and ask for confirmation.

If confirmed is true, reply with a booking confirmation:
"Your appointment is booked... You will receive an email shortly."

IMPORTANT RULES FOR STATE MANAGEMENT:
1. NEVER replace a non-null field in state with null. If you think a value is wrong, ask for confirmation instead of blanking it.
2. Always maintain the full conversation state across turns.
3. If the user provides new information, add it to the state but preserve existing information.
4. If the user corrects information, update only that specific field.
5. When all appointment details are collected, check availability and proceed to confirmation.
6. Do NOT write or modify availability_checked or is_available; those keys are backend-only.

IMPORTANT: DO NOT include any JSON syntax, code blocks, or technical formatting in your spoken responses. 
The user should only hear natural, conversational language.

When a user provides appointment details (date, time, doctor), always check availability before confirming.

CRITICAL: When you receive availability information, IMMEDIATELY communicate it to the user. 
Do not say you will check availability if you already have the result.

For appointment scheduling:
1. Collect patient name, doctor preference, date, and time
2. Check availability for the requested slot
3. If available, confirm the appointment
4. If not available, suggest alternative times (e.g., "Dr. Jackson is not available at 1 PM on June 4th, but has openings at 10 AM, 12 PM, and 2 PM that day.")

Keep responses brief and conversational. Echo user data for clarity ("Thanks, Anil. I'll check if Dr. Jackson is available on June 4th at 1 PM.").

When the user provides multiple pieces of information at once (like name, date, and time), acknowledge all of them and proceed to the next required information.

Never ask for information that the user has already provided.

For your internal tracking only (not to be spoken), maintain a state dictionary with these fields:
- task: "appointment" or "insurance"
- first_name: user's first name if provided
- full_name: user's full name if provided
- doctor: doctor name if provided
- date: appointment date if provided
- time: appointment time if provided
- confirmed: boolean indicating if the appointment is confirmed
- availability_checked: boolean indicating if availability was checked
- is_available: boolean indicating if the requested slot is available

You must respond only with a JSON object matching {"assistant": "...", "debug_state": {...}}.

Example response format (this is for your internal use only, never read this format aloud):
{"assistant": "Thanks for calling, Anil! I'll check if Dr. Jackson is available on June 4th at 1 PM.", "debug_state": {"task":"appointment","first_name":"Anil","doctor":"Dr. Jackson","date":"2025-06-04","time":"13:00"}}
"""
    
    def _initialize_state(self) -> Dict[str, Any]:
        """Initialize the conversation state with default values"""
        return {
            "task": None,
            "first_name": None,
            "full_name": None,
            "doctor": None,
            "date": None,
            "time": None,
            "insurance_provider": None,
            "insurance_number": None,
            "confirmed": False,
            "appointment_id": None,
            "is_available": None,
            "availability_checked": False
        }
    
    async def process_conversation_turn(self, session_id: str, user_input: str) -> str:
        """Process a single turn of conversation"""
        # Initialize conversation state if this is a new session
        if session_id not in self.conversation_states:
            self.logger.info(f"New session: {session_id} - Initializing conversation state")
            self.conversation_states[session_id] = {
                "messages": [
                    {"role": "system", "content": self._build_system_prompt()}
                ],
                "state": self._initialize_state(),
                "last_updated": datetime.utcnow()
            }
        else:
            self.logger.info(f"Continuing existing session: {session_id}")
            # Log the current state for debugging
            current_state = self.conversation_states[session_id]["state"]
            self.logger.info(f"Current state before processing: {current_state}")
        
        # For new sessions with no user input, generate initial greeting
        if not user_input:
            self.logger.info(f"No user input for session {session_id}, generating greeting")
            return await self._generate_response(session_id)
        
        # Check for confirmation in user input
        current_state = self.conversation_states[session_id]["state"]
        if self._is_confirmation(user_input) and current_state.get("is_available") and not current_state.get("confirmed"):
            self.logger.info(f"Detected confirmation in user input: '{user_input}'")
            # Update confirmation status in state
            self.conversation_states[session_id]["state"]["confirmed"] = True
            # Add confirmation message to inform the AI
            self.conversation_states[session_id]["messages"].append({
                "role": "system",
                "content": "User has confirmed the appointment. Please proceed with finalizing the booking."
            })
            self.logger.info(f"Updated confirmation status to True for session {session_id}")
        
        # Extract appointment information from user input
        state_updates = self._extract_info_from_input(user_input)
        
        # Update state with extracted information
        if state_updates:
            current_state = self.conversation_states[session_id]["state"]
            for key, value in state_updates.items():
                # Update if field is empty or user is correcting information
                correction_indicators = ["actually", "correction", "instead", "not", "wrong"]
                is_correction = any(indicator in user_input.lower() for indicator in correction_indicators)
                
                # Detect changes before updating
                date_changed = "date" in state_updates and state_updates["date"] != current_state.get("date")
                time_changed = "time" in state_updates and state_updates["time"] != current_state.get("time")
                
                # Update state with extracted information
                if current_state.get(key) is None or is_correction:
                    self.logger.info(f"Updated state field '{key}' to '{value}'")
                    current_state[key] = value
            
            # Set task to appointment if date or time is mentioned
            if "date" in state_updates or "time" in state_updates:
                current_state["task"] = "appointment"
                
            # If user supplied a NEW date or time, invalidate previous availability
            if date_changed or time_changed:
                self.logger.info(f"Date or time changed, resetting availability flags")
                current_state["availability_checked"] = False
                current_state["is_available"] = None
                current_state.pop("available_slots", None)
            
            # Check appointment availability if we have all required information
            if all(current_state.get(field) for field in ["doctor", "date", "time"]) and current_state.get("is_available") is None:
                availability = await self.healthcare_service.check_appointment_availability(
                    date=current_state["date"],
                    time=current_state["time"],
                    doctor=current_state["doctor"]
                )
                
                # Debug the availability response
                self.logger.info(f"Received availability response: {availability}, type: {type(availability)}, keys: {availability.keys() if isinstance(availability, dict) else 'Not a dict'}")
                
                # Update state with availability info
                current_state["is_available"] = availability.get("is_available", False)
                current_state["available_slots"] = availability.get("available_slots", [])
                
                # Log alternative times for better debugging
                if isinstance(current_state["available_slots"], list) and len(current_state["available_slots"]) > 0:
                    if isinstance(current_state["available_slots"][0], dict):
                        # Extract times from the slot objects
                        alternative_times = [int(slot["time"].split(":")[0]) for slot in current_state["available_slots"] if slot.get("available", False)]
                        self.logger.info(f"Alternative times for {current_state['doctor']} on {current_state['date']}: {alternative_times}")
                current_state["availability_checked"] = True
                
                # Add availability info as a system message
                availability_msg = f"Appointment with {current_state['doctor']} on {current_state['date']} at {current_state['time']} is {'available' if current_state['is_available'] else 'not available'}."
                self.logger.info(f"Session {session_id} - {availability_msg}")
                
                self.conversation_states[session_id]["messages"].append({
                    "role": "system",
                    "content": availability_msg
                })
                
                # If not available, provide alternative times
                if not availability:
                    alt_times = await self._get_alternative_times(current_state["doctor"], current_state["date"])
                    if alt_times:
                        alt_times_str = ", ".join([f"{h}:00" for h in alt_times])
                        alt_times_msg = f"Alternative available times for {current_state['doctor']} on {current_state['date']}: {alt_times_str}. Please suggest these times to the user."
                        
                        # Add as a system message
                        self.conversation_states[session_id]["messages"].append({
                            "role": "system",
                            "content": alt_times_msg
                        })
        
        # Add user message to conversation history
        self.logger.info(f"Session {session_id} - User input: '{user_input}'")
        self.conversation_states[session_id]["messages"].append({"role": "user", "content": user_input})
        
        # Generate and return response
        return await self._generate_response(session_id)
    
    async def _generate_response(self, session_id: str) -> str:
        """Generate a response from the assistant based on the current conversation state"""
        # Generate AI response
        response = await self.openai_wrapper.chat_complete(
            messages=self.conversation_states[session_id]["messages"]
        )
        
        self.logger.info(f"Raw AI response: {response}")
        
        # Parse the JSON response
        try:
            # The response might already be a dict or a JSON string
            if isinstance(response, dict):
                response_data = response
            else:
                response_data = json.loads(response)
                
            assistant_response = response_data.get("assistant", "")
            debug_state = response_data.get("debug_state", {})
            
            # Update the state from the debug_state
            try:
                # Check if debug_state is already a dict or a JSON string
                if isinstance(debug_state, dict):
                    updated_state = debug_state
                else:
                    updated_state = json.loads(debug_state)
                
                # Remove any premature availability flags injected by the LLM
                for key in ["availability_checked", "is_available"]:
                    updated_state.pop(key, None)
                    
                # Normalize doctor name if present
                if updated_state.get("doctor"):
                    updated_state["doctor"] = self._normalize_doctor(updated_state["doctor"])
                    
                self.conversation_states[session_id]["state"] = updated_state
                self.logger.info(f"Updated state: {updated_state}")
            except (json.JSONDecodeError, TypeError, AttributeError) as e:
                self.logger.error(f"Failed to parse debug_state: {debug_state}. Error: {str(e)}")
                updated_state = {}
                
                # Automatic safeguard for inconsistent state
                state = self.conversation_states[session_id]["state"]
                if state.get("availability_checked") and state.get("is_available") is None:
                    # Automatic safeguard
                    self.logger.warning("availability_checked==True but is_available is None; forcing re-check.")
                    state["availability_checked"] = False
                
                # ------------------------------------------------------------------
                # RUN CHECK IF NEEDED - Before finalizing assistant response
                # ------------------------------------------------------------------
                state = self.conversation_states[session_id]["state"]
                need_check = (
                    state.get("task") == "appointment"
                    and all(state.get(k) for k in ["doctor", "date", "time"])
                    and state.get("is_available") is None
                )
                
                if need_check:
                    # Normalize doctor name before checking availability
                    state["doctor"] = self._normalize_doctor(state["doctor"])
                    
                    availability = await self.healthcare_service.check_appointment_availability(
                        date=state["date"],
                        time=state["time"],
                        doctor=state["doctor"]
                    )
                    
                    # Debug the availability response
                    self.logger.info(f"Received availability response: {availability}, type: {type(availability)}, keys: {availability.keys() if isinstance(availability, dict) else 'Not a dict'}")
                    
                    state["availability_checked"] = True
                    state["is_available"] = availability.get("is_available", False)
                    state["available_slots"] = availability.get("available_slots", [])
                    
                    # Log alternative times for better debugging
                    if isinstance(state["available_slots"], list) and len(state["available_slots"]) > 0:
                        if isinstance(state["available_slots"][0], dict):
                            # Extract times from the slot objects
                            alternative_times = [int(slot["time"].split(":")[0]) for slot in state["available_slots"] if slot.get("available", False)]
                            self.logger.info(f"Alternative times for {state['doctor']} on {state['date']}: {alternative_times}")
                    
                    # ------------------------------------------------------------------
                    # BUILD ASSISTANT RESPONSE HERE — overrides GPT text
                    # ------------------------------------------------------------------
                    if state["is_available"]:
                        assistant_response = (
                            f"{state['doctor']} is free on {state['date']} at {state['time']}. "
                            "Shall I book it for you?"
                        )
                    else:
                        alt = state.get("available_slots") or await self._get_alternative_times(
                            state["doctor"], state["date"]
                        )
                        if isinstance(alt, list) and len(alt) > 0 and isinstance(alt[0], dict):
                            # Extract times from slot objects
                            times = ", ".join([slot["time"] for slot in alt if slot.get("available", False) and slot["doctor"] == state["doctor"]])
                        else:
                            times = ", ".join(f"{h}:00" for h in alt) if alt else "no other times today"
                            
                        assistant_response = (
                            f"Unfortunately {state['doctor']} is not available then. "
                            f"He has openings at {times}. Which one works best?"
                        )
                
                # If availability was checked previously, always override the assistant response
                elif state.get("availability_checked") and assistant_response.lower().startswith("thanks"):
                    # Backend decides what to say – never reuse GPT's "Thanks, … I'll check" lines
                    if state["is_available"]:
                        assistant_response = (
                            f"{state['doctor']} is free on {state['date']} at {state['time']}. "
                            "Shall I book it for you?"
                        )
                    else:
                        alt = state.get("available_slots") or await self._get_alternative_times(
                            state["doctor"], state["date"]
                        )
                        if isinstance(alt, list) and len(alt) > 0 and isinstance(alt[0], dict):
                            # Extract times from slot objects
                            times = ", ".join([slot["time"] for slot in alt if slot.get("available", False) and slot["doctor"] == state["doctor"]])
                        else:
                            times = ", ".join(f"{h}:00" for h in alt) if alt else "no other times today"
                            
                        assistant_response = (
                            f"Unfortunately {state['doctor']} is not available then. "
                            f"He has openings at {times}. Which one works best?"
                        )
                
                # if state is confirmed and not yet booked, do the booking here
                if state.get("confirmed") and not state.get("appointment_id"):
                    booking = await self.healthcare_service.book_appointment(
                        patient_info={"name": state.get("full_name") or state.get("first_name")},
                        appointment_details={
                            "doctor": state.get("doctor"),
                            "date": state.get("date"),
                            "time": state.get("time"),
                        },
                    )
                    state["appointment_id"] = booking.get("appointment_id", "AP" + str(random.randint(10000, 99999)))
                    assistant_response = (
                        f"Perfect — your appointment with {state['doctor']} on "
                        f"{state['date']} at {state['time']} is confirmed. "
                        "You'll receive an email shortly."
                    )
            
            return assistant_response
            
        except (json.JSONDecodeError, TypeError) as e:
            self.logger.error(f"Failed to parse AI response as JSON: {response}. Error: {str(e)}")
            # Fallback: return the raw response
            self.conversation_states[session_id]["messages"].append({
                "role": "assistant", 
                "content": response
            })
            return response
    
    def _extract_info_from_input(self, user_input: str) -> Dict[str, Any]:
        """Extract appointment and patient information from user input"""
        state_updates = {}
        
        # Extract name
        name_match = re.search(r"(?:my name is|I'm|I am) ([A-Z][a-z]+(?: [A-Z][a-z]+)*)", user_input)
        if name_match:
            full_name = name_match.group(1)
            state_updates["full_name"] = full_name
            # Extract first name
            first_name = full_name.split()[0]
            state_updates["first_name"] = first_name
        
        # Extract doctor
        doctor_match = re.search(r"(?:Dr\.?|Doctor|Mrs\.?|Ms\.?|Mr\.?) ([A-Z][a-z]+(?: [A-Z][a-z]+)*)", user_input)
        if doctor_match:
            state_updates["doctor"] = self._normalize_doctor(doctor_match.group(0))
        
        # Extract date
        months = ["january", "february", "march", "april", "may", "june", "july", 
                 "august", "september", "october", "november", "december"]
        month_pattern = "|".join(months)
        
        # Match patterns like "June 4th" or "June 4"
        date_match = re.search(rf"({month_pattern}) (\d+)(?:st|nd|rd|th)?", user_input, re.IGNORECASE)
        if date_match:
            month_name = date_match.group(1).lower()
            day = int(date_match.group(2))
            month_num = months.index(month_name) + 1
            year = datetime.now().year
            # Format as YYYY-MM-DD
            state_updates["date"] = f"{year}-{month_num:02d}-{day:02d}"
        
        # Extract time
        time_match = re.search(r"(\d{1,2})(?::?(\d{2}))? ?([ap]\.?m\.?|o'clock)", user_input, re.IGNORECASE)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            period = time_match.group(3).lower()
            
            # Convert to 24-hour format
            if "p" in period and hour < 12:
                hour += 12
            elif "a" in period and hour == 12:
                hour = 0
                
            # Format as HH:MM
            state_updates["time"] = f"{hour:02d}:{minute:02d}"
        
        # Extract task
        if "appointment" in user_input.lower() or "book" in user_input.lower() or "schedule" in user_input.lower():
            state_updates["task"] = "appointment"
        elif "insurance" in user_input.lower() or "verify" in user_input.lower() or "coverage" in user_input.lower():
            state_updates["task"] = "insurance"
        
        # Check for confirmation
        if re.search(r"\b(yes|correct|right|exactly|confirm|book it|that's right)\b", user_input.lower()):
            state_updates["confirmed"] = True
            
        return state_updates
    
    async def _check_appointment_availability(self, doctor: str, date_str: str, time_str: str) -> bool:
        """Check if the requested appointment slot is available"""
        try:
            # In a real implementation, this would call the healthcare service
            # For now, we'll use a mock schedule
            self.logger.info(f"Checking availability for {doctor} on {date_str} at {time_str}")
            
            # Parse the date and time
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            time_parts = time_str.split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0
            
            # Mock schedule - define available slots for different doctors
            mock_schedule = {
                # Format: doctor_name: {date: [available_hours]}
                "Dr. Jackson": {
                    "2025-06-04": [9, 10, 14, 16],  # Available at 9am, 10am, 2pm, 4pm
                    "2025-06-05": [11, 13, 15],      # Available at 11am, 1pm, 3pm
                },
                "Mrs. Jackson": {
                    "2025-06-04": [10, 12, 14],      # Available at 10am, 12pm, 2pm
                    "2025-06-05": [9, 11, 15],       # Available at 9am, 11am, 3pm
                },
                "Dr. Smith": {
                    "2025-06-04": [9, 11, 13, 15],   # Available at 9am, 11am, 1pm, 3pm
                    "2025-06-05": [10, 12, 14, 16],  # Available at 10am, 12pm, 2pm, 4pm
                }
            }
            
            # Normalize doctor name for lookup (remove "Dr." prefix if present)
            normalized_doctor = doctor.strip()
            
            # Check if the doctor exists in our mock schedule
            if normalized_doctor not in mock_schedule:
                self.logger.info(f"Doctor {normalized_doctor} not found in schedule, defaulting to available")
                return True
                
            # Check if the date exists in the doctor's schedule
            if date_str not in mock_schedule[normalized_doctor]:
                self.logger.info(f"Date {date_str} not found in {normalized_doctor}'s schedule, defaulting to unavailable")
                return False
                
            # Check if the hour is in the available hours for that doctor and date
            is_available = hour in mock_schedule[normalized_doctor][date_str]
            
            self.logger.info(f"Appointment availability for {normalized_doctor} on {date_str} at {hour}:00: {is_available}")
            return is_available
            
        except Exception as e:
            self.logger.error(f"Error checking appointment availability: {str(e)}")
            # Log the full exception for debugging
            self.logger.exception("Exception details:")
            # Default to available in case of error
            return True
    
    async def _get_alternative_times(self, doctor: str, date_str: str) -> list:
        """Get alternative available times for a doctor on a specific date"""
        try:
            # Use the same mock schedule from _check_appointment_availability
            mock_schedule = {
                # Format: doctor_name: {date: [available_hours]}
                "Dr. Jackson": {
                    "2025-06-04": [9, 10, 14, 16],  # Available at 9am, 10am, 2pm, 4pm
                    "2025-06-05": [11, 13, 15],      # Available at 11am, 1pm, 3pm
                },
                "Mrs. Jackson": {
                    "2025-06-04": [10, 12, 14],      # Available at 10am, 12pm, 2pm
                    "2025-06-05": [9, 11, 15],       # Available at 9am, 11am, 3pm
                },
                "Dr. Smith": {
                    "2025-06-04": [9, 11, 13, 15],   # Available at 9am, 11am, 1pm, 3pm
                    "2025-06-05": [10, 12, 14, 16],  # Available at 10am, 12pm, 2pm, 4pm
                }
            }
            
            # Normalize doctor name for lookup
            normalized_doctor = doctor.strip()
            
            # Check if the doctor exists in our mock schedule
            if normalized_doctor not in mock_schedule:
                self.logger.info(f"Doctor {normalized_doctor} not found in schedule for alternative times")
                return []
                
            # Check if the date exists in the doctor's schedule
            if date_str not in mock_schedule[normalized_doctor]:
                self.logger.info(f"Date {date_str} not found in {normalized_doctor}'s schedule for alternative times")
                return []
                
            # Return the available hours
            available_hours = mock_schedule[normalized_doctor][date_str]
            self.logger.info(f"Alternative times for {normalized_doctor} on {date_str}: {available_hours}")
            return available_hours
            
        except Exception as e:
            self.logger.error(f"Error getting alternative times: {str(e)}")
            self.logger.exception("Exception details:")
            return []
    
    def _check_confirmation(self, user_input: str) -> bool:
        """Legacy method for backward compatibility"""
        return self._is_confirmation(user_input)
        
    def _is_confirmation(self, user_input: str) -> bool:
        """Check if the user input contains confirmation"""
        # Handle empty input
        if not user_input or user_input.strip() == "":
            return False
            
        # Convert to lowercase for case-insensitive matching
        user_input_lower = user_input.lower().strip()
        
        # If this is an initial greeting or appointment request, it's not a confirmation
        if re.search(r"\b(hi|hello|book|schedule|appointment|like to|would like|need to|want to)\b.*\b(appointment|booking)\b", user_input_lower):
            return False
            
        # Common positive confirmation phrases
        positive_phrases = [
            "yes", "yeah", "yep", "correct", "right", "ok", "okay", "sure", 
            "confirm", "confirmed", "sounds good", "that's right", "that is right", 
            "that works", "proceed", "go ahead", "works for me", "that works for me", 
            "sounds good to me", "that time works", "perfect", "great"
        ]
        
        # Common negative phrases
        negative_phrases = ["no", "nope", "not", "don't", "do not", "cancel", "stop", "incorrect", "wrong"]
        
        # Check for exact matches first (single-word responses)
        if user_input_lower in positive_phrases:
            return True
            
        # Check for negative phrases that would override positive ones
        for phrase in negative_phrases:
            if re.search(r"\b" + re.escape(phrase) + r"\b", user_input_lower):
                return False
                
        # Check for positive phrases with word boundaries
        for phrase in positive_phrases:
            if re.search(r"\b" + re.escape(phrase) + r"\b", user_input_lower):
                return True
        
        # Additional regex patterns for phrases like "works for me"
        if re.search(r"\b(works\s+for\s+me|that\s+works|sounds\s+good|perfect)\b", user_input_lower):
            return True
                
        # For more complex confirmation patterns, be more conservative
        try:
            # Only consider these as confirmations if they're not part of a longer sentence
            if len(user_input_lower.split()) <= 5 and re.search(r"\b(confirm|proceed|go ahead)\b", user_input_lower):
                return True
        except Exception as e:
            self.logger.error(f"Error in regex search: {str(e)}")
            
        return False
    
    def _extract_appointment_info(self, session_id: str) -> Dict[str, Any]:
        """Extract appointment information from the conversation state"""
        state = self.conversation_states[session_id]["state"]
        return {
            "patient_name": state.get("full_name") or state.get("first_name") or "Patient",
            "doctor": state.get("doctor") or "Doctor",
            "date": state.get("date") or datetime.now().strftime("%Y-%m-%d"),
            "time": state.get("time") or "09:00",
            "confirmed": state.get("confirmed", False)
        }
    
    def _extract_insurance_info(self, session_id: str) -> Dict[str, Any]:
        """Extract insurance information from the conversation state"""
        state = self.conversation_states[session_id]["state"]
        return {
            "patient_name": state.get("full_name") or state.get("first_name") or "Patient",
            "insurance_provider": state.get("insurance_provider") or "Insurance Provider",
            "insurance_number": state.get("insurance_number") or "Insurance Number",
            "confirmed": state.get("confirmed", False)
        }
