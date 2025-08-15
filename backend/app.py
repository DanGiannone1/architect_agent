from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
import asyncio
import uvicorn
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from dotenv import load_dotenv
import os
import urllib.parse
from prompts import get_solution_architect_system_prompt

app = FastAPI(title="Solution Architect Agent API", version="1.0.0")

# Load environment variables
load_dotenv()

# Get environment variables
endpoint = os.getenv("PROJECT_ENDPOINT")
model_deployment_name = os.getenv("MODEL_DEPLOYMENT_NAME")

if not endpoint or not model_deployment_name:
    raise ValueError("PROJECT_ENDPOINT and MODEL_DEPLOYMENT_NAME must be set in environment")

# Initialize Azure AI Project client
project_client = AIProjectClient(
    credential=DefaultAzureCredential(),
    endpoint=endpoint,
)

# Get Application Insights connection string
connection_string = project_client.telemetry.get_application_insights_connection_string()

# Set up tracing
os.environ["AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED"] = "true"
OpenAIInstrumentor().instrument()
configure_azure_monitor(connection_string=connection_string)

# Get OpenAI client
openai_client = project_client.get_openai_client(api_version="2024-02-01")

# Add CORS middleware to allow frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class Message(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: Optional[str] = None

class ChatRequest(BaseModel):
    messages: List[Message]
    stream: bool = False

class ChatResponse(BaseModel):
    message: Message
    conversation_id: Optional[str] = None

# In-memory storage for demo purposes (replace with CosmosDB later)
conversations: Dict[str, List[Message]] = {}

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "Solution Architect Agent API is running", 
        "version": "1.0.0",
        "azure_ai_enabled": True
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": "2025-08-06T00:00:00Z"}

@app.post("/api/chat", response_model=ChatResponse)
async def chat_completion(request: ChatRequest):
    """
    Handle chat completion requests using Azure AI Foundry
    """
    try:
        # Get the last user message
        user_messages = [msg for msg in request.messages if msg.role == "user"]
        if not user_messages:
            raise HTTPException(status_code=400, detail="No user message found")
        
        # Convert request messages to Azure AI format
        azure_messages = [
            {"role": "system", "content": get_solution_architect_system_prompt()},
        ]
        
        for msg in request.messages:
            azure_messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        response = openai_client.chat.completions.create(
            model=model_deployment_name,
            messages=azure_messages,
            temperature=0.7,
            max_tokens=1500
        )
        
        assistant_response = response.choices[0].message.content
        
        # Create response message
        response_message = Message(
            role="assistant",
            content=assistant_response
        )
        
        return ChatResponse(
            message=response_message,
            conversation_id="dummy-conversation-id"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing chat request: {str(e)}")

@app.post("/api/chat/stream")
async def chat_completion_stream(request: ChatRequest):
    """
    Handle streaming chat completion requests using Azure AI Foundry
    """
    def generate_stream():  # Regular function, not async
        try:
            # Get the last user message
            user_messages = [msg for msg in request.messages if msg.role == "user"]
            if not user_messages:
                yield f"data: {json.dumps({'error': 'No user message found'})}\n\n"
                return
            
            # Convert request messages to Azure AI format
            azure_messages = [
                {"role": "system", "content": get_solution_architect_system_prompt()},
            ]
            
            for msg in request.messages:
                azure_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
            
            print("🔄 Starting Azure AI streaming...")
            
            # Create streaming response
            stream = openai_client.chat.completions.create(
                model=model_deployment_name,
                messages=azure_messages,
                temperature=0.7,
                max_tokens=1500,
                stream=True
            )
            
            # Stream the response - EXACTLY like working Gemini example
            for chunk in stream:
                try:
                    if (hasattr(chunk, 'choices') and 
                        chunk.choices and 
                        len(chunk.choices) > 0):
                        
                        choice = chunk.choices[0]
                        
                        if (hasattr(choice, 'delta') and 
                            choice.delta and 
                            hasattr(choice.delta, 'content') and 
                            choice.delta.content is not None):
                            
                            text = choice.delta.content
                            data_chunk = json.dumps({'chunk': text})
                            yield f"data: {data_chunk}\n\n"
                            print(f"📤 Yielding chunk: {repr(text)}")
                        
                        # Check for finish reason
                        if (hasattr(choice, 'finish_reason') and 
                            choice.finish_reason == 'stop'):
                            print("✅ Stream completed")
                            break
                            
                except (AttributeError, IndexError):
                    continue  # Skip malformed chunks
                
            # Signal end exactly like working example
            yield "data: [DONE]\n\n"
            print("📤 Sent [DONE] signal")
                
        except Exception as e:
            print(f"❌ Stream error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "http://localhost:3000",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "X-Accel-Buffering": "no",  # Disable proxy buffering
        }
    )

@app.get("/api/conversations")
async def get_conversations():
    """
    Get all conversations (dummy endpoint)
    """
    return {
        "conversations": [
            {
                "id": "conv-1",
                "title": "Getting Started",
                "last_message": "Hello! How can I help you today?",
                "timestamp": "2025-08-06T00:00:00Z"
            },
            {
                "id": "conv-2", 
                "title": "Azure AI Questions",
                "last_message": "Azure AI Foundry is a comprehensive platform...",
                "timestamp": "2025-08-05T12:00:00Z"
            }
        ]
    }

@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """
    Get a specific conversation by ID (dummy endpoint)
    """
    return {
        "id": conversation_id,
        "messages": [
            {
                "role": "assistant",
                "content": "Hello! How can I help you today?",
                "timestamp": "2025-08-06T00:00:00Z"
            }
        ]
    }

@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """
    Delete a specific conversation (dummy endpoint)
    """
    return {"message": f"Conversation {conversation_id} deleted successfully"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)