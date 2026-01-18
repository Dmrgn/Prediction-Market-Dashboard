# Backboard Agent Integration Specification

## Overview

This specification outlines the integration of `backboard-sdk` into the existing FastAPI WebSocket architecture. The goal is to provide a persistent, memory-enabled AI Agent service that users can interact with directly through the dashboard.

## Architecture

### Current System
- **FastAPI** backend with WebSocket support
- **SubscriptionManager** handling market data subscriptions
- **StateManager** managing market state
- WebSocket endpoint at `/ws` with operations: `subscribe_market`, `unsubscribe_market`

### New Components
1. **AgentService** - Manages Backboard client lifecycle and assistant operations
2. **Extended WebSocket Protocol** - Add agent-specific operations
3. **Thread Management** - Per-connection conversation state

---

## 1. Agent Service Layer

### Location
`backend/app/services/agent.py`

### Class: `AgentService`

Encapsulates the Backboard SDK client and provides high-level agent operations.

```python
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
        self.client = BackboardClient(api_key=os.getenv("BACKBOARD"))
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
```

---

## 2. WebSocket Protocol Extension

### Current Operations
- `subscribe_market` - Subscribe to market updates
- `unsubscribe_market` - Unsubscribe from market updates

### New Operations

#### `agent_init`
Initialize agent and create a conversation thread.

**Request:**
```json
{
  "op": "agent_init"
}
```

**Response:**
```json
{
  "type": "agent_ready",
  "thread_id": "thread_abc123",
  "assistant_id": "asst_xyz789"
}
```

#### `agent_message`
Send a message to the agent.

**Request:**
```json
{
  "op": "agent_message",
  "content": "What are the trending markets today?",
  "thread_id": "thread_abc123"  // Optional, uses connection's current thread if omitted
}
```

**Response (Streaming):**
Multiple messages will be sent as the agent responds:

```json
{
  "type": "agent_response",
  "payload": {
    "type": "content_streaming",
    "content": "Based on current data, the trending markets are..."
  }
}
```

```json
{
  "type": "agent_response",
  "payload": {
    "type": "memory_retrieved",
    "memories": [
      {
        "content": "User prefers crypto markets",
        "timestamp": "2026-01-15T10:30:00Z"
      }
    ]
  }
}
```

```json
{
  "type": "agent_response",
  "payload": {
    "type": "response_complete",
    "message_id": "msg_123"
  }
}
```

---

## 3. API Implementation

### Location
`backend/app/api.py`

### Changes to WebSocket Endpoint

```python
from .services.agent import AgentService

# Initialize service (done in main.py lifespan, accessed via app.state)

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, request: Request):
    sub_manager = SubscriptionManager()
    await websocket.accept()
    
    # Agent state for this connection
    current_thread_id = None
    
    # Get agent service from app state
    agent_service = request.app.state.agent
    
    try:
        while True:
            data = await websocket.receive_json()
            op = data.get("op")
            
            # ===== AGENT OPERATIONS =====
            
            if op == "agent_init":
                try:
                    # Ensure assistant is initialized
                    if not agent_service.assistant_id:
                        await agent_service.initialize()
                    
                    # Create new thread for this connection
                    thread = await agent_service.create_thread()
                    current_thread_id = thread.thread_id
                    
                    await websocket.send_json({
                        "type": "agent_ready",
                        "thread_id": current_thread_id,
                        "assistant_id": agent_service.assistant_id
                    })
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Failed to initialize agent: {str(e)}"
                    })

            elif op == "agent_message":
                try:
                    prompt = data.get("content")
                    thread_id = data.get("thread_id") or current_thread_id
                    
                    if not prompt:
                        await websocket.send_json({
                            "type": "error",
                            "error": "No content provided"
                        })
                        continue
                    
                    if not thread_id:
                        await websocket.send_json({
                            "type": "error",
                            "error": "No active thread_id. Send 'agent_init' first."
                        })
                        continue

                    # Stream agent response
                    async for chunk in agent_service.stream_chat(thread_id, prompt):
                        await websocket.send_json({
                            "type": "agent_response",
                            "payload": chunk
                        })
                        
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Agent error: {str(e)}"
                    })
            
            # ===== EXISTING MARKET OPERATIONS =====
            
            elif op == "subscribe_market":
                market_id = data.get("market_id")
                if market_id:
                    await sub_manager.subscribe(market_id, websocket)
            
            elif op == "unsubscribe_market":
                market_id = data.get("market_id")
                if market_id:
                    await sub_manager.unsubscribe(market_id, websocket)
                    
    except WebSocketDisconnect:
        await sub_manager.unsubscribe_from_all(websocket)
```

---

## 4. Application Lifecycle

### Location
`backend/app/main.py`

### Changes

```python
from .services.agent import AgentService

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    state = StateManager()
    
    # Initialize connectors (existing code)
    global poly_connector, kalshi_connector
    poly_connector = PolymarketConnector(state)
    kalshi_connector = KalshiConnector(state)
    
    # Initialize Agent Service
    agent_service = AgentService()
    
    # Load assistant ID from environment or create new
    assistant_id = os.getenv("BACKBOARD_ASSISTANT_ID")
    await agent_service.initialize(assistant_id)
    
    # Store in app state for API access
    app.state.poly = poly_connector
    app.state.kalshi = kalshi_connector
    app.state.agent = agent_service
    
    # ... rest of existing startup code ...
    
    yield
    
    # Shutdown
    # TODO: Cleanup if needed
```

---

## 5. Environment Configuration

### Required Variables

```bash
# Backboard API Configuration
BACKBOARD=your_api_key_here

# Optional: Reuse existing assistant (recommended for production)
BACKBOARD_ASSISTANT_ID=asst_your_assistant_id
```

### Notes
- If `BACKBOARD_ASSISTANT_ID` is not set, a new assistant will be created on each server restart
- For production, create an assistant once, then set the ID in environment variables
- The assistant maintains memory across threads, so reusing it preserves learned context

---

## 6. Frontend Integration Example

### JavaScript/TypeScript

```typescript
// Initialize WebSocket
const socket = new WebSocket('ws://localhost:8000/ws');

let currentThreadId: string | null = null;

// 1. Initialize agent on connection
socket.onopen = () => {
  socket.send(JSON.stringify({ op: 'agent_init' }));
};

// 2. Handle incoming messages
socket.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch (data.type) {
    case 'agent_ready':
      currentThreadId = data.thread_id;
      console.log('Agent ready with thread:', currentThreadId);
      break;
      
    case 'agent_response':
      handleAgentChunk(data.payload);
      break;
      
    case 'error':
      console.error('Error:', data.error);
      break;
      
    // ... handle market updates ...
  }
};

// 3. Handle streaming chunks
function handleAgentChunk(chunk: any) {
  switch (chunk.type) {
    case 'content_streaming':
      // Append to UI
      appendToChat(chunk.content);
      break;
      
    case 'memory_retrieved':
      // Show indicator that agent is using context
      showMemoryIndicator(chunk.memories.length);
      break;
      
    case 'response_complete':
      // Mark message as complete
      finishMessage(chunk.message_id);
      break;
  }
}

// 4. Send message to agent
function sendMessage(text: string) {
  socket.send(JSON.stringify({
    op: 'agent_message',
    content: text,
    thread_id: currentThreadId
  }));
}
```

---

## 7. Error Handling

### Service-Level Errors

```python
try:
    async for chunk in agent_service.stream_chat(thread_id, prompt):
        await websocket.send_json({
            "type": "agent_response",
            "payload": chunk
        })
except Exception as e:
    # Don't kill the WebSocket connection
    # Send error to client instead
    await websocket.send_json({
        "type": "error",
        "error": f"Agent error: {str(e)}"
    })
```

### Client-Side Error Display

Frontend should handle:
- Network errors (WebSocket disconnect)
- Agent initialization failures
- Message sending failures
- Timeout errors (if agent takes too long)

---

## 8. Security Considerations

### Authentication
- **TODO**: Add JWT/Session validation before allowing `agent_init`
- Validate user identity before creating threads
- Consider rate-limiting agent messages per user

### Data Privacy
- Thread IDs are session-specific, not user-specific
- Backboard handles memory isolation via assistant/thread architecture
- Consider logging/auditing agent interactions for compliance

### API Key Management
- Store `BACKBOARD` securely in environment
- Never expose API key to frontend
- Implement proper secret rotation procedures

---

## 9. Performance & Scaling

### Thread Management
- Each WebSocket connection = one thread
- Threads are lightweight (Backboard-managed)
- Consider cleanup of old/inactive threads

### Assistant Singleton
- One assistant serves all users
- Memory is per-thread, not per-assistant
- Backboard's "Auto" memory mode handles cross-thread context

### Streaming Optimization
- Chunks are sent immediately as received
- No buffering on backend
- Frontend should handle rapid updates efficiently

---

## 10. Testing Strategy

### Unit Tests
- Test `AgentService.initialize()` with/without assistant_id
- Test `AgentService.create_thread()`
- Mock Backboard SDK responses

### Integration Tests
- Test WebSocket `agent_init` operation
- Test WebSocket `agent_message` streaming
- Verify error handling doesn't crash connection
- Test concurrent market subscriptions + agent chat

### Manual Testing
1. Initialize agent: Send `agent_init`, verify `agent_ready` response
2. Send message: Verify streaming chunks arrive
3. Send follow-up: Verify context is maintained
4. Test errors: Send invalid data, verify graceful error response
5. Test mixed operations: Subscribe to market + chat with agent simultaneously

---

## 11. Production Deployment Checklist

- [ ] Set `BACKBOARD` in production environment
- [ ] Create production assistant and set `BACKBOARD_ASSISTANT_ID`
- [ ] Implement user authentication on WebSocket endpoint
- [ ] Add rate limiting for agent messages
- [ ] Set up monitoring/logging for agent interactions
- [ ] Configure proper CORS settings
- [ ] Test error recovery and connection stability
- [ ] Document API key rotation procedures
- [ ] Set up alerts for API quota limits

---

## 12. Future Enhancements

### Phase 2 Features
- **Multi-modal responses**: Support for charts, market cards in agent responses
- **Proactive notifications**: Agent can push relevant market alerts
- **Tool calling**: Agent can query market data directly
- **User profiles**: Persistent user preferences beyond conversation memory
- **Analytics**: Track agent usage, popular queries, satisfaction

### Advanced Memory
- Store thread IDs in user database for conversation resumption
- Implement conversation history API
- Support exporting/importing conversation context

---

## Appendix: Backboard SDK Reference

### Key Methods

```python
# Create client
client = BackboardClient(api_key="...")

# Create assistant
assistant = await client.create_assistant(
    name="...",
    system_prompt="..."
)

# Create thread
thread = await client.create_thread(assistant_id)

# Send message (streaming)
async for chunk in await client.add_message(
    thread_id="...",
    content="...",
    memory="Auto",
    stream=True
):
    # Handle chunk
    pass
```

### Chunk Types
- `content_streaming` - Text chunks being generated
- `memory_retrieved` - Relevant memories retrieved from past conversations
- `response_complete` - Message generation finished
- `error` - Error occurred during processing

---

## Summary

This integration adds a powerful AI agent to the dashboard without disrupting existing functionality. The WebSocket protocol is extended, not replaced, maintaining backward compatibility with market subscriptions while adding conversational AI capabilities.

**Key Benefits:**
- Memory-enabled conversations across sessions
- Streaming responses for better UX
- Isolated per-connection thread state
- Graceful error handling
- Production-ready architecture
