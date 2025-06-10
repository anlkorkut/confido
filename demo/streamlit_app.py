import streamlit as st
import requests
import io
import json
import os
import tempfile
from datetime import datetime, timedelta
import base64
from pathlib import Path

# Set page configuration
st.set_page_config(
    page_title="Healthcare Voice Assistant Demo",
    page_icon="🏥",
    layout="wide"
)

# Function to convert audio bytes to base64 for HTML playback
def get_audio_base64(audio_bytes):
    audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
    return audio_base64

# Function to create an HTML audio player
def get_audio_player_html(audio_base64):
    audio_html = f"""
    <audio controls autoplay>
        <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
        Your browser does not support the audio element.
    </audio>
    """
    return audio_html

# Function to process audio file
def process_audio(api_url, audio_file, session_id=None):
    files = {'audio_file': audio_file}
    data = {}
    if session_id:
        data['session_id'] = session_id
    
    try:
        response = requests.post(f"{api_url}/api/v1/voice/process", files=files, data=data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error processing audio: {str(e)}")
        return None

# Function to book appointment
def book_appointment(api_url, appointment_data):
    try:
        response = requests.post(f"{api_url}/api/v1/appointments/book", json=appointment_data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error booking appointment: {str(e)}")
        return None

# Function to verify insurance
def verify_insurance(api_url, insurance_data):
    try:
        response = requests.post(f"{api_url}/api/v1/insurance/verify", json=insurance_data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error verifying insurance: {str(e)}")
        return None

# Function to get clinic information
def get_clinic_info(api_url, query_type=None):
    params = {}
    if query_type:
        params['query_type'] = query_type
        
    try:
        response = requests.get(f"{api_url}/api/v1/clinic/info", params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error getting clinic information: {str(e)}")
        return None

def main():
    st.title("🏥 Healthcare Voice Assistant Demo")
    st.markdown("Upload audio files to test the voice assistant capabilities")
    
    # Sidebar configuration
    with st.sidebar:
        st.header("Configuration")
        api_url = st.text_input("API URL", "http://localhost:8000")
        
        # Check API connection
        if st.button("Test Connection"):
            try:
                response = requests.get(f"{api_url}/health")
                if response.status_code == 200:
                    st.success("✅ Connected to API")
                    st.json(response.json())
                else:
                    st.error(f"❌ Failed to connect: Status code {response.status_code}")
            except requests.exceptions.RequestException as e:
                st.error(f"❌ Connection error: {str(e)}")
        
        st.divider()
        st.markdown("### Sample Audio Files")
        
        # Check if sample audio files exist
        sample_dir = Path(__file__).parent / "sample_audio"
        if sample_dir.exists():
            sample_files = list(sample_dir.glob("*.wav"))
            if sample_files:
                st.info(f"Found {len(sample_files)} sample audio files")
                for file in sample_files:
                    if st.button(f"Use {file.name}"):
                        with open(file, "rb") as f:
                            st.session_state.sample_audio = {
                                "name": file.name,
                                "content": f.read()
                            }
                        st.experimental_rerun()
            else:
                st.warning("No sample audio files found in demo/sample_audio/")
        else:
            st.warning("Sample audio directory not found")
    
    # Main interface tabs
    tab1, tab2, tab3 = st.tabs(["Voice Interaction", "Appointment Booking", "Insurance Verification"])
    
    with tab1:
        st.subheader("Upload Audio File")
        
        # Check if we have a sample audio from the sidebar
        if hasattr(st.session_state, 'sample_audio'):
            st.info(f"Using sample audio: {st.session_state.sample_audio['name']}")
            uploaded_file = st.session_state.sample_audio['content']
            # Clear the sample audio from session state
            del st.session_state.sample_audio
        else:
            uploaded_file = st.file_uploader("Choose an audio file", type=['wav', 'mp3', 'ogg'])
        
        # Session management
        if 'session_id' not in st.session_state:
            st.session_state.session_id = None
            st.session_state.conversation_history = []
        
        col1, col2 = st.columns(2)
        with col1:
            use_session = st.checkbox("Continue conversation", value=st.session_state.session_id is not None)
        with col2:
            if st.button("Reset conversation"):
                st.session_state.session_id = None
                st.session_state.conversation_history = []
                st.success("Conversation reset")
        
        if uploaded_file and st.button("Process Audio"):
            with st.spinner("Processing audio..."):
                # Save uploaded file to a temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
                    if isinstance(uploaded_file, bytes):
                        temp_file.write(uploaded_file)
                    else:
                        temp_file.write(uploaded_file.read())
                    temp_path = temp_file.name
                
                # Process the audio file
                with open(temp_path, "rb") as audio_file:
                    result = process_audio(
                        api_url, 
                        audio_file, 
                        session_id=st.session_state.session_id if use_session else None
                    )
                
                # Clean up the temporary file
                os.unlink(temp_path)
                
                if result:
                    # Update session state
                    st.session_state.session_id = result["session_id"]
                    
                    # Add to conversation history
                    st.session_state.conversation_history.append({
                        "user": result["transcription"],
                        "assistant": result["response_text"],
                        "audio_url": result["response_audio_url"],
                        "intent": result["intent"],
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    })
                    
                    # Display results
                    st.success("Audio processed successfully!")
                    
                    # Get audio response
                    try:
                        audio_response = requests.get(f"{api_url}{result['response_audio_url']}")
                        if audio_response.status_code == 200:
                            audio_base64 = get_audio_base64(audio_response.content)
                            st.markdown(get_audio_player_html(audio_base64), unsafe_allow_html=True)
                    except requests.exceptions.RequestException as e:
                        st.error(f"Error fetching audio response: {str(e)}")
        
        # Display conversation history
        if st.session_state.conversation_history:
            st.subheader("Conversation History")
            for i, exchange in enumerate(st.session_state.conversation_history):
                with st.expander(f"Exchange {i+1} - {exchange['timestamp']} (Intent: {exchange['intent']})"):
                    st.markdown("**You said:**")
                    st.write(exchange["user"])
                    st.markdown("**Assistant responded:**")
                    st.write(exchange["assistant"])
    
    with tab2:
        st.subheader("Direct Appointment Booking")
        
        # Form for appointment booking
        with st.form("appointment_form"):
            # Patient information
            st.markdown("### Patient Information")
            patient_id = st.number_input("Patient ID", min_value=1, value=1)
            
            # Appointment details
            st.markdown("### Appointment Details")
            doctor_options = ["Dr. Emily Smith", "Dr. Michael Johnson", "Dr. Sarah Williams", "Dr. David Brown"]
            doctor_name = st.selectbox("Doctor", doctor_options)
            
            date_col, time_col = st.columns(2)
            with date_col:
                appointment_date = st.date_input("Date", value=datetime.now() + timedelta(days=1))
            with time_col:
                appointment_time = st.time_input("Time", value=datetime.strptime("09:00", "%H:%M").time())
            
            reason = st.text_area("Reason for Visit", "Annual checkup")
            
            submit_button = st.form_submit_button("Book Appointment")
            
            if submit_button:
                # Combine date and time
                appointment_datetime = datetime.combine(appointment_date, appointment_time)
                
                # Prepare appointment data
                appointment_data = {
                    "patient_id": patient_id,
                    "doctor_name": doctor_name,
                    "appointment_date": appointment_datetime.isoformat(),
                    "reason": reason,
                    "status": "scheduled"
                }
                
                # Book appointment
                with st.spinner("Booking appointment..."):
                    result = book_appointment(api_url, appointment_data)
                    
                    if result:
                        st.success("Appointment booked successfully!")
                        st.json(result)
    
    with tab3:
        st.subheader("Insurance Verification")
        
        # Form for insurance verification
        with st.form("insurance_form"):
            # Patient information
            st.markdown("### Patient Information")
            patient_name = st.text_input("Patient Name", "John Doe")
            dob = st.date_input("Date of Birth", value=datetime.now() - timedelta(days=365*30))
            
            # Insurance details
            st.markdown("### Insurance Details")
            insurance_options = ["Blue Cross Blue Shield", "Aetna", "Cigna", "UnitedHealthcare"]
            insurance_provider = st.selectbox("Insurance Provider", insurance_options)
            policy_number = st.text_input("Policy Number", "ABC123456789")
            
            # Service details
            st.markdown("### Service Details")
            service_col, code_col = st.columns(2)
            with service_col:
                service_description = st.text_input("Service Description", "Annual physical examination")
            with code_col:
                procedure_code = st.text_input("Procedure Code (optional)", "99385")
            
            submit_button = st.form_submit_button("Verify Insurance")
            
            if submit_button:
                # Prepare insurance data
                insurance_data = {
                    "patient_name": patient_name,
                    "date_of_birth": dob.isoformat(),
                    "insurance_provider": insurance_provider,
                    "policy_number": policy_number,
                    "service_description": service_description,
                    "procedure_code": procedure_code
                }
                
                # Verify insurance
                with st.spinner("Verifying insurance..."):
                    result = verify_insurance(api_url, insurance_data)
                    
                    if result:
                        if result["is_covered"]:
                            st.success(f"Service is covered ({result['coverage_percentage']}%)")
                        else:
                            st.error("Service is not covered")
                        
                        # Display details
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("Coverage Percentage", f"{result.get('coverage_percentage', 0)}%")
                            st.metric("Deductible Remaining", f"${result.get('deductible_remaining', 0)}")
                        with col2:
                            st.metric("Copay Amount", f"${result.get('copay_amount', 0)}")
                            st.metric("Authorization Required", "Yes" if result.get("authorization_required") else "No")
                        
                        if result.get("notes"):
                            st.info(result["notes"])

    # Footer
    st.divider()
    st.markdown("### Clinic Information")
    
    if st.button("View Clinic Information"):
        with st.spinner("Loading clinic information..."):
            clinic_info = get_clinic_info(api_url)
            
            if clinic_info:
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.subheader("Contact")
                    st.write(f"**Name:** {clinic_info.get('name')}")
                    st.write(f"**Address:** {clinic_info.get('address')}")
                    st.write(f"**Phone:** {clinic_info.get('phone')}")
                    st.write(f"**Email:** {clinic_info.get('email')}")
                
                with col2:
                    st.subheader("Hours")
                    hours = clinic_info.get('hours', {})
                    for day, time in hours.items():
                        st.write(f"**{day}:** {time}")
                
                with col3:
                    st.subheader("Services")
                    services = clinic_info.get('services', [])
                    for service in services:
                        st.write(f"• {service}")
                
                st.subheader("Doctors")
                doctors = clinic_info.get('doctors', [])
                doctor_cols = st.columns(len(doctors) if len(doctors) > 0 else 1)
                for i, doctor in enumerate(doctors):
                    with doctor_cols[i]:
                        st.write(f"**{doctor.get('name')}**")
                        st.write(f"*{doctor.get('specialty')}*")
                
                st.subheader("FAQs")
                faqs = clinic_info.get('faqs', [])
                for i, faq in enumerate(faqs):
                    with st.expander(faq.get('question', f'Question {i+1}')):
                        st.write(faq.get('answer', 'No answer provided'))

if __name__ == "__main__":
    main()
