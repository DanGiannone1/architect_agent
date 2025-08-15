# GenAI Chatbot Application

A production-grade GenAI chatbot application with a FastAPI backend and Next.js frontend.

## Architecture

- **Backend**: FastAPI with Python (located in `/backend`)
- **Frontend**: Next.js with TypeScript (located in `/frontend`)
- **Database**: CosmosDB (integration in progress)

## Quick Start

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
.venv\Scripts\activate  # On Windows
```

3. Install dependencies:
```bash
pip install -r ../requirements.txt
```

4. Run the FastAPI server:
```bash
python app.py
```

The API will be available at http://localhost:8000

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Run the development server:
```bash
npm run dev
```

The frontend will be available at http://localhost:3000

## API Endpoints

- `GET /` - Health check
- `GET /health` - Health status
- `POST /api/chat` - Chat completion (non-streaming)
- `POST /api/chat/stream` - Chat completion (streaming)
- `GET /api/conversations` - Get all conversations
- `GET /api/conversations/{id}` - Get specific conversation
- `DELETE /api/conversations/{id}` - Delete conversation

## Features

### Current Features
- ✅ Basic chat interface
- ✅ Real-time messaging
- ✅ Conversation sidebar
- ✅ Responsive design
- ✅ FastAPI backend with CORS
- ✅ Dummy AI responses

### Planned Features
- 🔄 Azure AI integration (using existing `foundry.py`)
- 🔄 CosmosDB integration for conversation storage
- 🔄 User authentication
- 🔄 Conversation persistence
- 🔄 Streaming responses
- 🔄 Message history

## Development

### Backend Development
The backend uses FastAPI with dummy responses. To integrate with Azure AI:
1. Use the existing `foundry.py` as reference
2. Replace dummy responses with actual AI calls
3. Implement conversation storage with CosmosDB

### Frontend Development
The frontend is built with Next.js and Tailwind CSS. Key components:
- Chat interface with message bubbles
- Sidebar for conversation history
- Real-time typing indicators
- Responsive design

## Environment Variables

Create a `.env` file in the root directory with:
```
PROJECT_ENDPOINT=your_azure_ai_endpoint
MODEL_DEPLOYMENT_NAME=your_model_deployment
```