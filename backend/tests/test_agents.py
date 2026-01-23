
import asyncio
import os
import sys
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

load_dotenv()

from app.ai.llm_service import LLMService
from app.ai.agent import AgentService
from app.state import StateManager

async def test_llm_service():
    print("\n--- Testing LLMService ---")
    try:
        llm = LLMService()
        state = StateManager()
        
        # Track some fake execution
        print("1. Tracking execution...")
        await llm.track_execution(
            command_id="open-chart",
            params={"marketId": "0x123abc"},
            state_manager=state
        )
        
        # Test suggestions
        print("2. Requesting suggestions for 'open-order-book'...")
        params = [{"name": "marketId", "type": "market"}]
        suggestions = await llm.suggest_params(
            command_id="open-order-book",
            params=params,
            state_manager=state
        )
        print(f"Suggestions: {suggestions}")
    except Exception as e:
        print(f"LLMService Error: {e}")

async def test_agent_service():
    print("\n--- Testing AgentService ---")
    try:
        agent = AgentService()
        print("1. Initializing...")
        assistant_id = await agent.initialize()
        print(f"Assistant ID: {assistant_id}")
        
        print("2. Creating thread...")
        thread = await agent.create_thread()
        thread_id = thread.thread_id
        print(f"Thread ID: {thread_id}")
        
        print("3. Running agent step for 'Open a chart for Bitcoin'...")
        commands = [
            {"id": "open-chart", "label": "Open Chart", "params": [{"name": "marketId", "type": "market"}]},
            {"id": "search-markets", "label": "Search Markets", "params": [{"name": "query", "type": "text"}]}
        ]
        step = await agent.run_agent_step(
            thread_id=thread_id,
            prompt="Open a chart for Bitcoin",
            commands=commands
        )
        print(f"Agent Step Result: {step}")
    except Exception as e:
        print(f"AgentService Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_llm_service())
    asyncio.run(test_agent_service())
