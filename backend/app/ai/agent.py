"""Agent service for managing Backboard AI integration."""

import os
from backboard import BackboardClient
from typing import AsyncGenerator, Optional

class AgentService:
    """
    Manages the Backboard AI Agent lifecycle.
    Handles assistant creation, thread management, and streaming chat.
    """
    
    def __init__(self):
        """Initialize the Backboard client."""
        api_key = os.getenv("BACKBOARD")
        if not api_key:
            raise ValueError("BACKBOARD_API_KEY environment variable is required")
        
        self.client = BackboardClient(api_key=api_key)
        self.assistant_id: Optional[str] = None

    async def initialize(self, assistant_id: Optional[str] = None):
        """
        Ensures an assistant exists for the application.
        
        Args:
            assistant_id: Optional existing assistant ID to reuse
            
        Returns:
            The assistant ID (created or reused)
        """
        if assistant_id:
            # Reuse existing assistant from environment/config
            self.assistant_id = assistant_id
            print(f"[AgentService] Reusing assistant: {assistant_id}")
        else:
            # Create new assistant
            assistant = await self.client.create_assistant(
                name="Dashboard Assistant",
                system_prompt=(
                    "You are an AI agent integrated into a financial prediction market dashboard. "
                    "You have access to user history and market context. "
                    "Help users analyze markets, understand trends, and make informed decisions. "
                    "Be concise but informative. Remember user preferences across conversations."
                )
            )
            self.assistant_id = assistant.assistant_id
            print(f"[AgentService] Created new assistant: {self.assistant_id}")
        
        return self.assistant_id

    async def create_thread(self) -> dict:
        """
        Create a new conversation thread.
        
        Returns:
            Thread object with thread_id
            
        Raises:
            RuntimeError: If assistant is not initialized
        """
        if not self.assistant_id:
            raise RuntimeError("Assistant not initialized. Call initialize() first.")
        
        thread = await self.client.create_thread(self.assistant_id)
        print(f"[AgentService] Created thread: {thread.thread_id}")
        return thread

    async def stream_chat(
        self, 
        thread_id: str, 
        content: str
    ) -> AsyncGenerator[dict, None]:
        """
        Send a message and stream the response.
        
        Args:
            thread_id: The conversation thread ID
            content: User's message content
            
        Yields:
            Streaming response chunks from Backboard
            
        Raises:
            RuntimeError: If assistant is not initialized
        """
        if not self.assistant_id:
            raise RuntimeError("Assistant not initialized. Call initialize() first.")
        
        async for chunk in await self.client.add_message(
            thread_id=thread_id,
            content=content,
            memory="Auto",  # Enable automatic memory management
            stream=True
        ):
            yield chunk
