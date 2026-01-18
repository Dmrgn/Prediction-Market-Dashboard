# Backend Specification: Agent-Powered Parameter Suggestions

## Overview

This specification defines the backend infrastructure for AI-powered command parameter suggestions. The system tracks user command executions, builds contextual understanding via the Backboard agent, and provides intelligent parameter suggestions when users interact with the command palette.

## Architecture

### System Components

```
┌──────────────────────────────────────────────────────────┐
│ WebSocket API (/ws)                                      │
│  - agent_track_execution: Record command usage          │
│  - agent_suggest_params: Request parameter suggestions  │
└──────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────┐
│ Command History Manager                                  │
│  - In-memory circular buffer (last 50 executions)        │
│  - Per-connection tracking                               │
│  - Context serialization for agent                       │
└──────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────┐
│ AgentService (Backboard SDK)                            │
│  - Receives execution history as context                │
│  - Generates suggestions via LLM                         │
│  - Returns structured parameter suggestions             │
└──────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────┐
│ WebSocket Response                                       │
│  - param_suggestions event                               │
│  - Structured suggestion data                            │
└──────────────────────────────────────────────────────────┘
```

---

## WebSocket Protocol Extensions

### Operation 1: `agent_track_execution`

Track command executions for learning and context building.

**Request:**
```json
{
  "op": "agent_track_execution",
  "command_id": "query-market",
  "params": {
    "marketId": "0x123abc..."
  },
  "timestamp": "2026-01-17T19:30:00Z"
}
```

**Response:** (Acknowledgment - optional)
```json
{
  "type": "execution_tracked",
  "command_id": "query-market"
}
```

**Behavior:**
- Store execution in per-connection command history
- Maintain circular buffer (max 50 executions)
- No immediate agent interaction (passive tracking)
- Fast, non-blocking operation

---

### Operation 2: `agent_suggest_params`

Request parameter suggestions for a specific command.

**Request:**
```json
{
  "op": "agent_suggest_params",
  "command_id": "query-market",
  "params": [
    {
      "name": "marketId",
      "type": "market"
    }
  ],
  "current_params": {},
  "request_id": "query-market-1737149400123"
}
```

**Response:**
```json
{
  "type": "param_suggestions",
  "command_id": "query-market",
  "request_id": "query-market-1737149400123",
  "suggestions": {
    "marketId": {
      "type": "market_list",
      "options": [
        {
          "value": "0x123abc...",
          "label": "Trump 2024 Election",
          "description": "polymarket • Recently queried",
          "reason": "You searched this 5 minutes ago"
        },
        {
          "value": "0x456def...",
          "label": "ETH Price Dec 31",
          "description": "polymarket • Frequently used",
          "reason": "You've opened this market 3 times today"
        }
      ],
      "reasoning": "Based on your recent activity and search patterns"
    }
  }
}
```

**For text/select parameters:**
```json
{
  "type": "param_suggestions",
  "command_id": "open-news-feed",
  "request_id": "open-news-feed-1737149400456",
  "suggestions": {
    "query": {
      "type": "direct",
      "value": "Trump election markets",
      "reasoning": "Based on your recent market searches"
    }
  }
}
```

**Error Response:**
```json
{
  "type": "error",
  "error": "Failed to generate suggestions: <reason>",
  "request_id": "query-market-1737149400123"
}
```

---

## Implementation

### 1. Command History Manager

Create a new service to manage command execution history.

**Location:** `backend/app/services/command_history.py`

```python
from collections import deque
from typing import Dict, List, Optional
from datetime import datetime
import json

class CommandExecution:
    """Represents a single command execution."""
    
    def __init__(
        self,
        command_id: str,
        params: Dict[str, str],
        timestamp: str
    ):
        self.command_id = command_id
        self.params = params
        self.timestamp = timestamp
    
    def to_dict(self) -> dict:
        return {
            "command_id": self.command_id,
            "params": self.params,
            "timestamp": self.timestamp
        }


class CommandHistoryManager:
    """
    Manages command execution history per WebSocket connection.
    Maintains a circular buffer of recent executions for context.
    """
    
    def __init__(self, max_size: int = 50):
        """
        Initialize the history manager.
        
        Args:
            max_size: Maximum number of executions to store
        """
        self.max_size = max_size
        self.history: deque[CommandExecution] = deque(maxlen=max_size)
    
    def track_execution(
        self,
        command_id: str,
        params: Dict[str, str],
        timestamp: Optional[str] = None
    ) -> None:
        """
        Track a command execution.
        
        Args:
            command_id: The command identifier
            params: The parameters used
            timestamp: ISO timestamp (auto-generated if not provided)
        """
        if not timestamp:
            timestamp = datetime.utcnow().isoformat() + "Z"
        
        execution = CommandExecution(command_id, params, timestamp)
        self.history.append(execution)
        
        print(f"[CommandHistory] Tracked: {command_id} (total: {len(self.history)})")
    
    def get_recent_executions(
        self,
        limit: Optional[int] = None,
        command_id: Optional[str] = None
    ) -> List[CommandExecution]:
        """
        Get recent command executions.
        
        Args:
            limit: Maximum number to return
            command_id: Filter by specific command (optional)
        
        Returns:
            List of CommandExecution objects (most recent first)
        """
        filtered = list(self.history)
        
        if command_id:
            filtered = [e for e in filtered if e.command_id == command_id]
        
        # Reverse to get most recent first
        filtered.reverse()
        
        if limit:
            filtered = filtered[:limit]
        
        return filtered
    
    def build_context_string(
        self,
        command_id: str,
        limit: int = 10
    ) -> str:
        """
        Build a context string for the agent.
        
        Args:
            command_id: The command to generate suggestions for
            limit: Maximum number of recent executions to include
        
        Returns:
            Formatted context string for the agent
        """
        recent = self.get_recent_executions(limit=limit)
        
        if not recent:
            return "No command execution history available."
        
        # Build context
        lines = ["Recent command executions:"]
        
        for i, execution in enumerate(recent, 1):
            params_str = json.dumps(execution.params)
            lines.append(
                f"{i}. {execution.command_id} - {params_str} ({execution.timestamp})"
            )
        
        # Add specific context for the requested command
        same_command = [e for e in recent if e.command_id == command_id]
        if same_command:
            lines.append(f"\nPrevious executions of '{command_id}':")
            for i, execution in enumerate(same_command[:5], 1):
                params_str = json.dumps(execution.params)
                lines.append(f"  {i}. {params_str} ({execution.timestamp})")
        
        return "\n".join(lines)
    
    def get_statistics(self) -> Dict:
        """Get statistics about command usage."""
        command_counts: Dict[str, int] = {}
        param_frequencies: Dict[str, Dict[str, int]] = {}
        
        for execution in self.history:
            # Count commands
            command_counts[execution.command_id] = (
                command_counts.get(execution.command_id, 0) + 1
            )
            
            # Count parameter values
            for param_name, param_value in execution.params.items():
                if param_name not in param_frequencies:
                    param_frequencies[param_name] = {}
                
                param_frequencies[param_name][param_value] = (
                    param_frequencies[param_name].get(param_value, 0) + 1
                )
        
        return {
            "total_executions": len(self.history),
            "command_counts": command_counts,
            "param_frequencies": param_frequencies
        }
```

---

### 2. Agent Service Enhancement

Update `AgentService` to support parameter suggestions.

**Location:** `backend/app/ai/agent.py`

Add new method to AgentService:

```python
async def suggest_params(
    self,
    thread_id: str,
    command_id: str,
    params: List[Dict[str, str]],
    context: str,
    current_params: Optional[Dict[str, str]] = None
) -> Dict:
    """
    Generate parameter suggestions for a command.
    
    Args:
        thread_id: The conversation thread ID
        command_id: The command to suggest params for
        params: List of parameter definitions [{"name": "marketId", "type": "market"}]
        context: Command execution history context
        current_params: Current parameter values (optional)
    
    Returns:
        Dictionary of parameter suggestions
    """
    if not self.assistant_id:
        raise RuntimeError("Assistant not initialized. Call initialize() first.")
    
    # Build prompt for the agent
    prompt = self._build_suggestion_prompt(
        command_id,
        params,
        context,
        current_params
    )
    
    # Get suggestion from agent (non-streaming)
    response = await self.client.add_message(
        thread_id=thread_id,
        content=prompt,
        memory="Auto",
        stream=False
    )
    
    # Parse agent response into structured format
    suggestions = self._parse_suggestions(response, params)
    
    return suggestions

def _build_suggestion_prompt(
    self,
    command_id: str,
    params: List[Dict[str, str]],
    context: str,
    current_params: Optional[Dict[str, str]]
) -> str:
    """Build the prompt for parameter suggestions."""
    
    param_descriptions = []
    for param in params:
        param_descriptions.append(
            f"- {param['name']} (type: {param['type']})"
        )
    
    prompt = f"""Based on the user's command execution history, suggest default parameter values for the '{command_id}' command.

Command Parameters:
{chr(10).join(param_descriptions)}

{context}

For each parameter, suggest:
1. If type is 'market': Provide a list of 2-3 relevant market IDs with titles and reasoning
2. If type is 'text' or 'select': Provide a single suggested value

Respond in JSON format:
{{
  "paramName": {{
    "type": "market_list" or "direct",
    "value": "suggested value" (for direct type),
    "options": [
      {{"value": "market_id", "label": "Market Title", "reason": "Why suggested"}}
    ] (for market_list type),
    "reasoning": "Brief explanation"
  }}
}}

Only suggest parameters that have clear relevant history. If no good suggestions exist, return an empty object {{}}.
"""
    
    return prompt

def _parse_suggestions(
    self,
    response: dict,
    params: List[Dict[str, str]]
) -> Dict:
    """
    Parse agent response into structured suggestions.
    
    Args:
        response: Raw agent response
        params: Parameter definitions
    
    Returns:
        Structured suggestion dictionary
    """
    import json
    
    try:
        # Extract content from response
        content = response.get("content", "")
        
        # Try to extract JSON from the response
        # Agent might wrap JSON in markdown code blocks
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            content = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            content = content[start:end].strip()
        
        suggestions = json.loads(content)
        
        # Validate structure
        validated_suggestions = {}
        for param_name, suggestion in suggestions.items():
            if suggestion.get("type") in ["direct", "market_list"]:
                validated_suggestions[param_name] = suggestion
        
        return validated_suggestions
        
    except Exception as e:
        print(f"[AgentService] Failed to parse suggestions: {e}")
        return {}
```

---

### 3. WebSocket API Updates

Update the WebSocket endpoint to handle new operations.

**Location:** `backend/app/api.py`

```python
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    sub_manager = SubscriptionManager()
    await websocket.accept()
    
    # Agent state for this connection
    current_thread_id = None
    
    # Command history for this connection
    command_history = CommandHistoryManager(max_size=50)
    
    # Get agent service from app state
    agent_service = getattr(websocket.app.state, "agent", None)
    
    try:
        while True:
            data = await websocket.receive_json()
            op = data.get("op")
            
            # ===== AGENT OPERATIONS =====
            
            if op == "agent_init":
                # ... existing code ...
                pass

            elif op == "agent_message":
                # ... existing code ...
                pass
            
            # ===== NEW: COMMAND TRACKING =====
            
            elif op == "agent_track_execution":
                try:
                    command_id = data.get("command_id")
                    params = data.get("params", {})
                    timestamp = data.get("timestamp")
                    
                    if command_id:
                        command_history.track_execution(
                            command_id=command_id,
                            params=params,
                            timestamp=timestamp
                        )
                        
                        # Optional: Send acknowledgment
                        await websocket.send_json({
                            "type": "execution_tracked",
                            "command_id": command_id
                        })
                    
                except Exception as e:
                    print(f"[WebSocket] Error tracking execution: {e}")
                    # Don't send error to client - this is a background operation
            
            # ===== NEW: SUGGESTION REQUESTS =====
            
            elif op == "agent_suggest_params":
                if not agent_service:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Agent service not available",
                        "request_id": data.get("request_id")
                    })
                    continue
                
                try:
                    command_id = data.get("command_id")
                    params = data.get("params", [])
                    current_params = data.get("current_params", {})
                    request_id = data.get("request_id")
                    
                    if not command_id:
                        await websocket.send_json({
                            "type": "error",
                            "error": "command_id required",
                            "request_id": request_id
                        })
                        continue
                    
                    # Build context from command history
                    context = command_history.build_context_string(
                        command_id=command_id,
                        limit=10
                    )
                    
                    # Ensure thread exists
                    if not current_thread_id:
                        if not agent_service.assistant_id:
                            await agent_service.initialize()
                        thread = await agent_service.create_thread()
                        current_thread_id = thread.thread_id
                    
                    # Get suggestions from agent
                    suggestions = await agent_service.suggest_params(
                        thread_id=current_thread_id,
                        command_id=command_id,
                        params=params,
                        context=context,
                        current_params=current_params
                    )
                    
                    # Send suggestions to client
                    await websocket.send_json({
                        "type": "param_suggestions",
                        "command_id": command_id,
                        "request_id": request_id,
                        "suggestions": suggestions
                    })
                    
                except Exception as e:
                    print(f"[WebSocket] Error generating suggestions: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Failed to generate suggestions: {str(e)}",
                        "request_id": data.get("request_id")
                    })
            
            # ===== EXISTING MARKET OPERATIONS =====
            
            elif op == "subscribe_market":
                # ... existing code ...
                pass
            
            elif op == "unsubscribe_market":
                # ... existing code ...
                pass
                    
    except WebSocketDisconnect:
        await sub_manager.unsubscribe_from_all(websocket)
```

---

## Agent System Prompt Enhancement

Update the agent's system prompt to include parameter suggestion capabilities.

**Location:** `backend/app/ai/agent.py` (in the `initialize` method)

```python
system_prompt=(
    "You are an AI agent integrated into a financial prediction market dashboard. "
    "You have access to user history and market context. "
    "Help users analyze markets, understand trends, and make informed decisions. "
    "Be concise but informative. Remember user preferences across conversations.\n\n"
    
    "PARAMETER SUGGESTIONS:\n"
    "When asked to suggest parameter values for commands, analyze the user's recent "
    "command execution history and provide contextually relevant suggestions. "
    "For market parameters, suggest 2-3 markets the user has recently interacted with. "
    "For text parameters, suggest values based on recent patterns. "
    "Always explain your reasoning briefly. "
    "Format suggestions as structured JSON. "
    "If no good suggestions exist, return an empty object."
)
```

---

## Performance Optimizations

### 1. Caching

Implement simple in-memory caching for suggestions:

```python
from datetime import datetime, timedelta
from typing import Optional

class SuggestionCache:
    """Cache parameter suggestions to avoid redundant agent calls."""
    
    def __init__(self, ttl_seconds: int = 30):
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, tuple[dict, datetime]] = {}
    
    def get(self, command_id: str) -> Optional[dict]:
        """Get cached suggestions if still valid."""
        if command_id in self.cache:
            suggestions, timestamp = self.cache[command_id]
            if datetime.utcnow() - timestamp < timedelta(seconds=self.ttl_seconds):
                return suggestions
            else:
                del self.cache[command_id]
        return None
    
    def set(self, command_id: str, suggestions: dict) -> None:
        """Cache suggestions."""
        self.cache[command_id] = (suggestions, datetime.utcnow())
    
    def invalidate(self, command_id: str) -> None:
        """Invalidate cache for a command."""
        if command_id in self.cache:
            del self.cache[command_id]
```

Usage in WebSocket handler:

```python
# Create cache per connection
suggestion_cache = SuggestionCache(ttl_seconds=30)

# In agent_suggest_params handler:
cached = suggestion_cache.get(command_id)
if cached:
    await websocket.send_json({
        "type": "param_suggestions",
        "command_id": command_id,
        "request_id": request_id,
        "suggestions": cached,
        "cached": True  # Optional flag
    })
else:
    # Generate suggestions...
    suggestions = await agent_service.suggest_params(...)
    suggestion_cache.set(command_id, suggestions)
```

### 2. Timeout Handling

Set timeouts for agent calls:

```python
import asyncio

try:
    suggestions = await asyncio.wait_for(
        agent_service.suggest_params(...),
        timeout=2.5  # 2.5 seconds (frontend has 3s timeout)
    )
except asyncio.TimeoutError:
    await websocket.send_json({
        "type": "error",
        "error": "Suggestion request timed out",
        "request_id": request_id
    })
```

---

## Data Structures

### CommandExecution
```python
{
    "command_id": str,
    "params": Dict[str, str],
    "timestamp": str  # ISO 8601 format
}
```

### SuggestionResponse
```python
{
    "type": "param_suggestions",
    "command_id": str,
    "request_id": str,
    "suggestions": {
        "paramName": {
            "type": "direct" | "market_list",
            "value": str,  # Optional, for direct type
            "options": [  # Optional, for market_list type
                {
                    "value": str,
                    "label": str,
                    "description": str,
                    "reason": str
                }
            ],
            "reasoning": str
        }
    }
}
```

---

## Error Handling

### Graceful Degradation

1. **Agent Service Unavailable:**
   - Return error response, frontend continues normally
   - Log error for debugging

2. **No Execution History:**
   - Agent still generates suggestions (less contextual)
   - Or return empty suggestions object

3. **Agent Response Parsing Failure:**
   - Log error, return empty suggestions
   - Frontend shows no suggestions

4. **Timeout:**
   - Cancel request after 2.5 seconds
   - Return error to frontend

### Error Logging

```python
import logging

logger = logging.getLogger(__name__)

try:
    suggestions = await agent_service.suggest_params(...)
except Exception as e:
    logger.error(
        f"Failed to generate suggestions for {command_id}: {e}",
        exc_info=True
    )
    # Return error to client
```

---

## Security Considerations

### Input Validation

```python
def validate_suggestion_request(data: dict) -> bool:
    """Validate suggestion request data."""
    
    # Validate command_id
    if not data.get("command_id") or not isinstance(data["command_id"], str):
        return False
    
    if len(data["command_id"]) > 100:  # Reasonable limit
        return False
    
    # Validate params structure
    params = data.get("params", [])
    if not isinstance(params, list):
        return False
    
    for param in params:
        if not isinstance(param, dict):
            return False
        if "name" not in param or "type" not in param:
            return False
    
    return True
```

### Rate Limiting

```python
from collections import defaultdict
from datetime import datetime, timedelta

class RateLimiter:
    """Simple rate limiter for suggestion requests."""
    
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, List[datetime]] = defaultdict(list)
    
    def is_allowed(self, connection_id: str) -> bool:
        """Check if request is allowed."""
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=self.window_seconds)
        
        # Clean old requests
        self.requests[connection_id] = [
            ts for ts in self.requests[connection_id]
            if ts > cutoff
        ]
        
        # Check limit
        if len(self.requests[connection_id]) >= self.max_requests:
            return False
        
        # Record request
        self.requests[connection_id].append(now)
        return True
```

---

## Testing

### Unit Tests

```python
import pytest
from app.services.command_history import CommandHistoryManager

def test_track_execution():
    manager = CommandHistoryManager(max_size=5)
    
    manager.track_execution("test-command", {"param1": "value1"})
    
    recent = manager.get_recent_executions()
    assert len(recent) == 1
    assert recent[0].command_id == "test-command"

def test_circular_buffer():
    manager = CommandHistoryManager(max_size=3)
    
    for i in range(5):
        manager.track_execution(f"command-{i}", {})
    
    recent = manager.get_recent_executions()
    assert len(recent) == 3
    assert recent[0].command_id == "command-4"  # Most recent

def test_build_context():
    manager = CommandHistoryManager()
    
    manager.track_execution("query-market", {"marketId": "market-1"})
    manager.track_execution("query-market", {"marketId": "market-2"})
    
    context = manager.build_context_string("query-market")
    assert "market-1" in context
    assert "market-2" in context
```

### Integration Tests

```python
import pytest
from fastapi.testclient import TestClient
from fastapi import WebSocket

@pytest.mark.asyncio
async def test_suggestion_request():
    # Mock WebSocket connection
    # Send agent_suggest_params operation
    # Verify response structure
    pass

@pytest.mark.asyncio
async def test_execution_tracking():
    # Track multiple executions
    # Request suggestions
    # Verify suggestions reflect history
    pass
```

---

## Deployment Checklist

- [ ] Add `CommandHistoryManager` to `backend/app/services/command_history.py`
- [ ] Update `AgentService` with `suggest_params` method
- [ ] Update WebSocket handler with new operations
- [ ] Update agent system prompt
- [ ] Add error handling and logging
- [ ] Implement caching (optional optimization)
- [ ] Add rate limiting (optional security)
- [ ] Write unit tests
- [ ] Write integration tests
- [ ] Test with frontend
- [ ] Monitor agent API usage/costs
- [ ] Document any new environment variables

---

## Cost & Performance Monitoring

### Agent API Usage

Each suggestion request makes one Backboard API call. Monitor:
- Requests per minute
- Average response time
- Cache hit rate
- Cost per suggestion

### Optimization Strategies

1. **Increase cache TTL** for frequently used commands
2. **Batch suggestion requests** if user navigates quickly
3. **Prefetch suggestions** for common commands
4. **Fallback to rule-based suggestions** if agent is slow/unavailable

---

## Summary

This backend specification provides:

1. **Two new WebSocket operations:**
   - `agent_track_execution`: Passive command tracking
   - `agent_suggest_params`: Active suggestion generation

2. **CommandHistoryManager:** Maintains execution history per connection

3. **Enhanced AgentService:** Generates contextual parameter suggestions

4. **Response Format:** Structured suggestions for market lists and direct values

5. **Performance:** Caching, timeouts, rate limiting

6. **Security:** Input validation, request limits

The implementation integrates seamlessly with existing WebSocket infrastructure and agent integration, providing intelligent assistance without disrupting command palette functionality.
