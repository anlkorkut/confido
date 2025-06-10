# Healthcare Voice Assistant

An AI-powered healthcare voice assistant that handles appointment scheduling, insurance verification, and clinic FAQs through natural voice interactions. The system processes pre-recorded audio files and generates spoken responses using state-of-the-art AI technologies.

## Features

- **Appointment Scheduling**: Book appointments with doctors based on availability
- **Insurance Verification**: Verify insurance coverage for procedures
- **Clinic FAQs**: Answer common questions about the clinic
- **Voice Processing**: Convert speech to text and text to speech
- **Natural Conversation**: Engage in natural dialogue with patients

## Technology Stack

- Python 3.11+
- FastAPI web framework with async support
- OpenAI GPT-4o for conversation handling
- OpenAI Whisper API for speech-to-text
- Google Cloud Text-to-Speech API
- SQLite with SQLAlchemy ORM
- Poetry for dependency management
- Streamlit for demo dashboard

## Setup

### Prerequisites

- Python 3.11 or higher
- Poetry package manager
- OpenAI API key
- Google Cloud credentials with Text-to-Speech API enabled

### Installation

1. Clone the repository

```bash
git clone https://github.com/yourusername/healthcare-voice-assistant.git
cd healthcare-voice-assistant
```

2. Set up environment variables

```bash
cp .env.example .env
```

Edit the `.env` file with your API keys and configuration.

3. Install dependencies

```bash
make install
```

4. Set up the database

```bash
make setup-db
```

## Usage

### Running the API Server

```bash
make run
```

The API will be available at http://localhost:8000

### Running the Demo Dashboard

```bash
make demo
```

The Streamlit dashboard will be available at http://localhost:8501

### API Endpoints

- `POST /api/v1/voice/process`: Process voice interactions
- `POST /api/v1/appointments/book`: Book appointments directly
- `POST /api/v1/insurance/verify`: Verify insurance coverage
- `GET /api/v1/clinic/info`: Get clinic information
- `WebSocket /ws/voice`: Real-time voice interaction

## Development

### Running Tests

```bash
make test
```

### Code Formatting

```bash
make format
```

### Linting

```bash
make lint
```

### Cleaning Up

```bash
make clean
```

## License

MIT
