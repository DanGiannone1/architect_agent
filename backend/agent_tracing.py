from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from dotenv import load_dotenv
import os
import time
from opentelemetry import trace

load_dotenv()

# Enable content recording for agents
os.environ["AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED"] = "true"

# Initialize project client
project_client = AIProjectClient(
    credential=DefaultAzureCredential(),
    endpoint=os.environ["PROJECT_ENDPOINT"],
)

# Get Application Insights connection string
connection_string = project_client.telemetry.get_application_insights_connection_string()

if not connection_string:
    print("Application Insights is not enabled. Enable by going to Tracing in your Azure AI Foundry project.")
    exit()

# Configure Azure Monitor tracing
configure_azure_monitor(connection_string=connection_string)

# Instrument OpenAI SDK (agents use OpenAI under the hood)
OpenAIInstrumentor().instrument()

# Get tracer for custom spans
tracer = trace.get_tracer(__name__)

from azure.ai.agents.telemetry import AIAgentsInstrumentor
AIAgentsInstrumentor().instrument()

# Start tracing
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("example-tracing"):
    agent = project_client.agents.create_agent(
        model=os.environ["MODEL_DEPLOYMENT_NAME"],
        name="my-assistant",
        instructions="You are a helpful assistant"
    )
    thread = project_client.agents.threads.create()
    message = project_client.agents.messages.create(
        thread_id=thread.id, role="user", content="Tell me a joke about horses"
    )
    run = project_client.agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)

with tracer.start_as_current_span("example-tracing"):
    # Create agent
    agent = project_client.agents.create_agent(
        model=os.environ["MODEL_DEPLOYMENT_NAME"],
        name="my-assistant",
        instructions="You are a helpful assistant"
    )
    print(f"✅ Created agent: {agent.id}")
    
    # Create thread (FIXED: use nested API structure)
    thread = project_client.agents.threads.create()
    print(f"✅ Created thread: {thread.id}")
    
    # Create message (FIXED: use nested API structure)
    message = project_client.agents.messages.create(
        thread_id=thread.id, 
        role="user", 
        content="Tell me a joke"
    )
    print(f"✅ Created message: {message.id}")
    
    # Create run (FIXED: use nested API structure)
    run = project_client.agents.runs.create(
        thread_id=thread.id, 
        agent_id=agent.id
    )
    print(f"✅ Created run: {run.id}")
    
    # Optional: Wait for completion and get the response
    print("⏳ Waiting for agent response...")
    while run.status in ["queued", "in_progress"]:
        time.sleep(2)
        run = project_client.agents.runs.get(thread_id=thread.id, run_id=run.id)
        print(f"Run status: {run.status}")
    
    if run.status == "completed":
        # Get the agent's joke
        messages = project_client.agents.messages.list(thread_id=thread.id)
        for msg in messages:
            if msg.role == "assistant" and msg.run_id == run.id:
                joke = msg.content[0].text.value
                print(f"🤖 Agent's joke: {joke}")
                break
    else:
        print(f"❌ Run ended with status: {run.status}")
    
    # Optional: Cleanup
    try:
        project_client.agents.delete_agent(agent.id)
        print(f"🗑️ Cleaned up agent: {agent.id}")
    except Exception as e:
        print(f"⚠️ Could not clean up: {e}")

print("\n✅ Agent tracing example completed!")
print("📊 Check Azure AI Foundry portal → Tracing tab to see traces under 'example-tracing' span")