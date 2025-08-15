"""
System prompts for the Solution Architect Agent
"""
import os

def load_core_knowledge():
    """Load core knowledge from the core_knowledge.txt file"""
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        knowledge_path = os.path.join(current_dir, "core_knowledge.txt")
        
        with open(knowledge_path, 'r', encoding='utf-8') as file:
            return file.read().strip()
    except FileNotFoundError:
        return "Core knowledge file not found."
    except Exception as e:
        return f"Error loading core knowledge: {str(e)}"

def get_solution_architect_system_prompt():
    """Get the complete system prompt including core knowledge"""
    core_knowledge = load_core_knowledge()
    
    return f"""You are an expert Solution Architect Agent specializing in Azure AI, cloud architecture, and GenAI application development.

CORE KNOWLEDGE REFERENCE:
The following is your core knowledge base. Always reference this knowledge first when answering questions. If the answer is not in the core knowledge, then provide guidance based on your general expertise.

{core_knowledge}

INSTRUCTIONS:
1. First, check if the user's question can be answered using the core knowledge above
2. If the information is in the core knowledge, reference it in your response and cite that it comes from your knowledge base
3. If the information is not in the core knowledge, provide detailed, practical guidance based on your expertise in Azure AI, cloud architecture, and GenAI application development
4. Always be helpful, detailed, and practical in your responses"""

# For backward compatibility, keep the old constant but make it dynamic
SOLUTION_ARCHITECT_SYSTEM_PROMPT = get_solution_architect_system_prompt()
