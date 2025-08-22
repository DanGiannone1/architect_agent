from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
import asyncio
import uvicorn
import uuid
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from dotenv import load_dotenv
import os
import urllib.parse
from prompts import get_solution_architect_system_prompt, get_production_readiness_system_prompt, get_checklist_generation_prompt, get_intent_analysis_prompt, get_response_analysis_prompt

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
#openai_client = project_client.get_openai_client(api_version="2024-02-01")
openai_client = project_client.get_openai_client(api_version="2024-08-01-preview")

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

class ProductionReadinessRequest(BaseModel):
    service: str
    messages: List[Message] = []

class ChecklistItem(BaseModel):
    item: str
    status: str  # "pending", "implemented", "needs_attention", "not_applicable"
    user_response: str = ""
    recommendation: str = ""
    importance: str = ""
    description: str = ""

class ChecklistItemData(BaseModel):
    """Individual checklist item data for structured output"""
    item: str
    importance: str
    description: str

class ChecklistGeneration(BaseModel):
    """Structured output for checklist generation"""
    service_name: str
    checklist_items: List[ChecklistItemData]

class UserIntentAnalysis(BaseModel):
    """Structured output for analyzing user intent"""
    intent: str  # "add_services", "continue_to_review", "unclear"
    detected_services: List[str] = []
    confidence: float  # 0.0 to 1.0

class UserResponseAnalysis(BaseModel):
    """Structured output for analyzing user response during checklist review - was the recommended item implemented or not"""
    implemented: str # "implemented", "needs_attention"

class ServiceProgress(BaseModel):
    service_name: str
    checklist_items: List[ChecklistItem] = []
    current_item_index: int = 0
    is_complete: bool = False

# In-memory storage for demo purposes (replace with CosmosDB later)
conversations: Dict[str, List[Message]] = {}
production_mode: bool = False
current_service: str = ""
services_list: List[str] = []
service_progress: List[ServiceProgress] = []
current_service_index: int = 0
conversation_phase: str = "collecting_services"  # "collecting_services", "reviewing_services", "complete"

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
    return {"status": "healthy", "timestamp": "2025-08-21T00:00:00Z"}

@app.post("/api/production-readiness", response_model=ChatResponse)
async def production_readiness_chat(request: ProductionReadinessRequest):
    """
    Handle production readiness conversations with a specific Azure service
    """
    try:
        global production_mode, current_service, services_list, conversation_phase, current_service_index
        
        # Set production mode and current service
        production_mode = True
        current_service = request.service
        
        # If no messages provided, start the conversation
        if not request.messages:
            services_list = [request.service]
            conversation_phase = "collecting_services"
            
            initial_message = f"""Hello! I'm your Production Readiness Assistant. My role is to review Azure services being deployed as part of your project and provide specific guidance based on Microsoft best practices and our internal knowledge base.

                                I see you're currently looking for production advice for **{request.service}**. Are there other Azure services that are part of your overall architecture that you'd like me to review as well?

                                Please let me know if you have additional services, or type 'continue' if {request.service} is the only service you'd like me to review today."""

            response_message = Message(
                role="assistant",
                content=initial_message
            )
            
            return ChatResponse(
                message=response_message,
                conversation_id="production-readiness"
            )
        
        # Get the latest user message
        user_messages = [msg for msg in request.messages if msg.role == "user"]
        if not user_messages:
            raise HTTPException(status_code=400, detail="No user message found")
        
        latest_user_message = user_messages[-1]
        user_input = latest_user_message.content.lower().strip()
        
        # Handle different conversation phases
        if conversation_phase == "collecting_services":
            # Use LLM to analyze user intent instead of keyword matching
            intent_analysis = await analyze_user_intent(latest_user_message.content)
            
            if intent_analysis.intent == "add_services":
                # Add detected services
                for service in intent_analysis.detected_services:
                    if service not in services_list:
                        services_list.append(service)
                
                response_content = f"Great! I've added {', '.join(intent_analysis.detected_services)} to our review list. So we'll be reviewing: **{', '.join(services_list)}**.\n\nAre there any other services, or would you like to start the systematic review?"
            
            elif intent_analysis.intent == "continue_to_review":
                # Start the systematic review
                await initialize_services_progress(services_list)
                conversation_phase = "reviewing_services"
                current_service_index = 0
                
                first_service = services_list[0]
                checklist_items = await get_service_checklist_items(first_service)
                
                items_list = "\n".join([f"{i+1}. **{item.item}** - {item.importance}" for i, item in enumerate(checklist_items)])
                
                response_content = f"""Perfect! Let's walk through each service systematically to see where you are and what needs to be done.

                                    **Starting with {first_service}**

                                    Here are the key production readiness items I recommend we review:

                                    {items_list}

                                    Let's start with the first one: **{checklist_items[0].item}**

                                    {checklist_items[0].importance}

                                    Have you implemented {checklist_items[0].item.lower()} for your {first_service}?"""
            
            else:
                response_content = "I didn't detect any specific Azure services in your response. Could you please list the specific Azure services you'd like me to review, or type 'continue' to start reviewing the services we already have?"
        
        elif conversation_phase == "reviewing_services":
            # Handle answers about specific checklist items
            current_item = get_current_checklist_item()
            current_service_obj = get_current_service_progress()
            
            if not current_item or not current_service_obj:
                response_content = "I seem to have lost track of where we are. Let me know if you'd like to start over."
            else:
                # Process the user's response about the current item
                current_item.user_response = latest_user_message.content
                
                # Use LLM to analyze user intent instead of keyword matching
                intent_analysis = await analyze_user_response(latest_user_message.content)
                
                # Determine status based on user response
                if intent_analysis.implemented == "implemented":
                    current_item.status = "implemented"
                    current_item.recommendation = "Great! This is properly implemented."
                elif intent_analysis.implemented == "needs_attention":
                    current_item.status = "needs_attention"
                    current_item.recommendation = f"Consider implementing this - {current_item.importance.lower()}"
                else:
                    current_item.status = "needs_attention"
                    current_item.recommendation = "Please clarify the implementation status of this item."
                
                # Move to next item
                advance_to_next_item()
                
                # Check what's next
                next_item = get_current_checklist_item()
                next_service = get_current_service_progress()
                
                if conversation_phase == "complete":
                    # All services completed
                    response_content = f"Excellent! We've completed the review of all your services.\n\n{generate_final_summary()}"
                
                elif next_service and next_service.service_name != current_service_obj.service_name:
                    # Moving to next service
                    new_service = next_service.service_name
                    checklist_items = next_service.checklist_items
                    
                    items_list = "\n".join([f"{i+1}. **{item.item}** - {item.importance}" for i, item in enumerate(checklist_items)])
                    
                    response_content = f"""Great progress on {current_service_obj.service_name}! Now let's move to **{new_service}**.

                                        Here are the key production readiness items for {new_service}:

                                        {items_list}

                                        Let's start with: **{checklist_items[0].item}**

                                        {checklist_items[0].importance}

                                        Have you implemented {checklist_items[0].item.lower()} for your {new_service}?"""
                
                elif next_item:
                    # Next item in same service
                    response_content = f"""Thanks for that information about {current_item.item.lower()}.

                                        Next item: **{next_item.item}**

                                        {next_item.importance}

                                        Have you implemented {next_item.item.lower()} for your {current_service_obj.service_name}?"""
                
                else:
                    response_content = "Something went wrong with tracking our progress. Let me know if you'd like to continue."
        
        else:
            response_content = "I'm not sure how to help with that. Type 'summary' to see your production readiness summary."
        
        # Create response message
        response_message = Message(
            role="assistant",
            content=response_content
        )
        
        return ChatResponse(
            message=response_message,
            conversation_id="production-readiness"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in production readiness chat: {str(e)}")

async def analyze_user_intent(user_message: str) -> UserIntentAnalysis:
    """Use LLM to analyze user intent during service collection phase"""
    try:
        response = openai_client.beta.chat.completions.parse(
            model=model_deployment_name,
            messages=[
                {"role": "system", "content": get_intent_analysis_prompt()},
                {"role": "user", "content": user_message}
            ],
            response_format=UserIntentAnalysis,
            temperature=0.1,
            max_tokens=500
        )
        
        response_content = response.choices[0].message.parsed
        
        return response_content

    except Exception as e:
        print(f"Error analyzing user intent: {e}")
        return UserIntentAnalysis(
            intent="unclear",
            detected_services=[],
            confidence=0.1
        )

async def analyze_user_response(user_message: str) -> UserResponseAnalysis:
    """Use LLM to analyze user response of whether a service recommendation was implemented or not"""
    try:
        response = openai_client.beta.chat.completions.parse(
            model=model_deployment_name,
            messages=[
                {"role": "system", "content": get_response_analysis_prompt()},
                {"role": "user", "content": user_message}
            ],
            response_format=UserResponseAnalysis,
            temperature=0.1,
            max_tokens=500
        )
        
        response_content = response.choices[0].message.parsed
        
        return response_content

    except Exception as e:
        print(f"Error analyzing user intent: {e}")
        return UserResponseAnalysis(
            intent="unclear",
            detected_services=[],
            confidence=0.1
        )

@app.get("/api/production-readiness/summary")
async def get_production_summary():
    """
    Get the current production readiness summary
    """
    try:
        if not service_progress:
            return {"summary": "No production readiness session in progress."}
        
        summary = generate_final_summary()
        
        return {
            "summary": summary,
            "services": [
                {
                    "name": service.service_name,
                    "is_complete": service.is_complete,
                    "items": [
                        {
                            "item": item.item,
                            "status": item.status,
                            "user_response": item.user_response,
                            "recommendation": item.recommendation,
                            "importance": item.importance
                        }
                        for item in service.checklist_items
                    ]
                }
                for service in service_progress
            ],
            "conversation_phase": conversation_phase
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting production summary: {str(e)}")

async def get_service_checklist_items(service: str) -> List[ChecklistItem]:
    """Dynamically generate production readiness checklist items for a specific service using LLM with structured outputs"""
    try:
        # Use the LLM to generate checklist items based on core knowledge with structured output
        response = openai_client.beta.chat.completions.parse(
            model=model_deployment_name,
            messages=[
                {"role": "system", "content": get_checklist_generation_prompt(service)}
            ],
            response_format=ChecklistGeneration,
            temperature=0.1,
            max_tokens=1000
        )
        
        # Get the parsed structured output
        checklist_generation = response.choices[0].message.parsed
        
        # Convert ChecklistGeneration to List[ChecklistItem]
        checklist_items = []
        for item_data in checklist_generation.checklist_items:
            item = ChecklistItem(
                item=item_data.item,
                importance=item_data.importance,
                description=item_data.description,
                status="pending"
            )
            checklist_items.append(item)
        
        return checklist_items
    
    except Exception as e:
        print(f"Error generating checklist for {service}: {e}")
        # Fallback checklist
        return [
            ChecklistItem(
                item=f"Production readiness assessment for {service}",
                importance="Review based on Azure best practices and core knowledge",
                description="Comprehensive review of this service for production deployment",
                status="pending"
            )
        ]

async def initialize_services_progress(services: List[str]):
    """Initialize progress tracking for all services"""
    global service_progress
    service_progress = []
    for service in services:
        checklist = await get_service_checklist_items(service)
        progress = ServiceProgress(
            service_name=service,
            checklist_items=checklist
        )
        service_progress.append(progress)

def get_current_service_progress() -> Optional[ServiceProgress]:
    """Get the current service being reviewed"""
    global current_service_index, service_progress
    if current_service_index < len(service_progress):
        return service_progress[current_service_index]
    return None

def get_current_checklist_item() -> Optional[ChecklistItem]:
    """Get the current checklist item being discussed"""
    current_service = get_current_service_progress()
    if current_service and current_service.current_item_index < len(current_service.checklist_items):
        return current_service.checklist_items[current_service.current_item_index]
    return None

def advance_to_next_item():
    """Move to the next checklist item or service"""
    global current_service_index, conversation_phase
    
    current_service = get_current_service_progress()
    if not current_service:
        return
    
    current_service.current_item_index += 1
    
    # Check if we've completed all items for this service
    if current_service.current_item_index >= len(current_service.checklist_items):
        current_service.is_complete = True
        current_service_index += 1
        
        # Check if we've completed all services
        if current_service_index >= len(service_progress):
            conversation_phase = "complete"

def generate_final_summary() -> str:
    """Generate the final summary table of all services and their status"""
    summary = "## Production Readiness Summary\n\n"
    
    for service in service_progress:
        summary += f"### {service.service_name}\n"
        
        implemented = []
        needs_attention = []
        
        for item in service.checklist_items:
            if item.status == "implemented":
                implemented.append(f"✅ {item.item}")
            elif item.status == "needs_attention":
                needs_attention.append(f"⚠️ {item.item} - {item.recommendation}")
            elif item.status == "not_applicable":
                implemented.append(f"➖ {item.item} (Not Applicable)")
        
        if implemented:
            summary += "**Implemented:**\n"
            for item in implemented:
                summary += f"- {item}\n"
            summary += "\n"
        
        if needs_attention:
            summary += "**Needs Attention:**\n"
            for item in needs_attention:
                summary += f"- {item}\n"
            summary += "\n"
        
        summary += "---\n\n"
    
    # Overall statistics
    total_items = sum(len(service.checklist_items) for service in service_progress)
    implemented_items = sum(1 for service in service_progress for item in service.checklist_items if item.status == "implemented")
    attention_items = sum(1 for service in service_progress for item in service.checklist_items if item.status == "needs_attention")
    
    summary += f"**Overall Progress:** {implemented_items}/{total_items} items implemented ({round(implemented_items/total_items*100, 1)}%)\n"
    summary += f"**Items needing attention:** {attention_items}\n"
    
    return summary

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