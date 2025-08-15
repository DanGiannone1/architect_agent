#azure-ai-projects==1.0.0
#opentelemetry-instrumentation-openai-v2==2.1b0

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from dotenv import load_dotenv
import os

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
print(f"✅ Connection string obtained: {connection_string[:50]}...")

# Set up tracing
os.environ["AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED"] = "true"
OpenAIInstrumentor().instrument()
configure_azure_monitor(connection_string=connection_string)
print("✅ Tracing configured")

# Get OpenAI client
openai_client = project_client.get_openai_client(
    api_version="2024-02-01"
)
print("✅ OpenAI client created")

print("\n" + "="*60)
print("🔥 AZURE AI PROJECTS - LLM DEMO")
print("="*60)

# =============================================================================
# EXAMPLE 1: NON-STREAMING LLM CALL
# =============================================================================
print("\n📝 EXAMPLE 1: Non-Streaming LLM Call")
print("-" * 40)

try:
    print("🔄 Making non-streaming chat completion...")
    
    response = openai_client.chat.completions.create(
        model=model_deployment_name,
        messages=[
            {"role": "system", "content": "You are a helpful AI assistant."},
            {"role": "user", "content": "What is Azure AI Foundry? Give me a brief overview."}
        ],
        temperature=0,
        max_tokens=500,
        # stream=False is the default, so no need to specify
    )
    
    print("✅ Non-streaming call successful!")
    print("\n📋 Response:")
    print("-" * 30)
    print(response.choices[0].message.content)
    print("-" * 30)
    
    # Show response metadata
    print(f"📊 Usage - Prompt tokens: {response.usage.prompt_tokens}")
    print(f"📊 Usage - Completion tokens: {response.usage.completion_tokens}")
    print(f"📊 Usage - Total tokens: {response.usage.total_tokens}")
    print(f"🏁 Finish reason: {response.choices[0].finish_reason}")
    
except Exception as e:
    print(f"❌ Error in non-streaming call: {e}")
    import traceback
    traceback.print_exc()

# =============================================================================
# EXAMPLE 2: STREAMING LLM CALL
# =============================================================================
print("\n\n📺 EXAMPLE 2: Streaming LLM Call")
print("-" * 40)

def handle_streaming_response(stream):
    """
    Robust handler for Azure OpenAI streaming responses
    """
    full_response = ""
    
    try:
        for chunk in stream:
            # Safe navigation through the chunk structure
            if (hasattr(chunk, 'choices') and 
                chunk.choices and 
                len(chunk.choices) > 0):
                
                choice = chunk.choices[0]
                
                if (hasattr(choice, 'delta') and 
                    choice.delta and 
                    hasattr(choice.delta, 'content') and 
                    choice.delta.content is not None):
                    
                    content = choice.delta.content
                    print(content, end="", flush=True)
                    full_response += content
                
                # Check for finish reason
                if (hasattr(choice, 'finish_reason') and 
                    choice.finish_reason == 'stop'):
                    print(f"\n✅ Stream completed with reason: {choice.finish_reason}")
                    break
                    
    except Exception as stream_error:
        print(f"\n❌ Stream processing error: {stream_error}")
        
    return full_response

try:
    print("🔄 Starting streaming chat completion...")
    
    stream = openai_client.chat.completions.create(
        model=model_deployment_name,
        messages=[
            {"role": "system", "content": "You are a helpful AI assistant that provides detailed explanations."},
            {"role": "user", "content": "Explain the key benefits of using Azure AI Foundry for AI development projects. Be detailed."}
        ],
        temperature=0,
        max_tokens=1000,
        stream=True  # Enable streaming
    )
    
    print("✅ Streaming started! Response:")
    print("-" * 50)
    
    response_content = handle_streaming_response(stream)
    
    print("\n" + "-" * 50)
    print("✅ Streaming complete!")
    print(f"📊 Total response length: {len(response_content)} characters")
    
except Exception as e:
    print(f"❌ Error in streaming call: {e}")
    import traceback
    traceback.print_exc()

# =============================================================================
# EXAMPLE 3: SIMPLE STREAMING (Alternative Approach)
# =============================================================================
print("\n\n⚡ EXAMPLE 3: Simple Streaming Approach")
print("-" * 40)

try:
    print("🔄 Simple streaming example...")
    
    stream = openai_client.chat.completions.create(
        model=model_deployment_name,
        messages=[
            {"role": "user", "content": "Count from 1 to 10 and explain each number briefly."}
        ],
        temperature=0,
        max_tokens=500,
        stream=True
    )
    
    print("Response:")
    print("-" * 20)
    
    # Simple streaming loop with basic error handling
    for chunk in stream:
        try:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'content') and delta.content:
                    print(delta.content, end="", flush=True)
        except (AttributeError, IndexError):
            continue  # Skip malformed chunks
    
    print("\n" + "-" * 20)
    print("✅ Simple streaming complete!")
    
except Exception as e:
    print(f"❌ Error in simple streaming: {e}")

# =============================================================================
# EXAMPLE 4: CONVERSATION WITH CONTEXT
# =============================================================================
print("\n\n💬 EXAMPLE 4: Multi-turn Conversation")
print("-" * 40)

try:
    # Simulate a conversation with context
    conversation_messages = [
        {"role": "system", "content": "You are a helpful AI assistant specializing in Azure services."},
        {"role": "user", "content": "What is Azure AI Foundry?"},
        {"role": "assistant", "content": "Azure AI Foundry is Microsoft's comprehensive platform for building, training, and deploying AI applications..."},
        {"role": "user", "content": "How does it compare to other AI platforms?"}
    ]
    
    print("🔄 Making conversation call with context...")
    
    response = openai_client.chat.completions.create(
        model=model_deployment_name,
        messages=conversation_messages,
        temperature=0.3,  # Slightly more creative
        max_tokens=600
    )
    
    print("✅ Conversation call successful!")
    print("\n💭 Assistant's response:")
    print("-" * 30)
    print(response.choices[0].message.content)
    print("-" * 30)
    
except Exception as e:
    print(f"❌ Error in conversation call: {e}")

# =============================================================================
# SUMMARY
# =============================================================================
print("\n\n🎉 DEMO SUMMARY")
print("="*50)
print("✅ Non-streaming LLM call - Complete response at once")
print("✅ Streaming LLM call - Real-time response generation")
print("✅ Simple streaming - Minimal error handling")
print("✅ Multi-turn conversation - Context preservation")
print("\n🔍 Check your Azure AI Foundry portal → Tracing tab to see all traces!")
print("📖 All calls are automatically traced with OpenTelemetry")
