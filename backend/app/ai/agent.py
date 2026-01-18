"""Agent service for managing Backboard AI integration."""

import os
import json
from backboard import BackboardClient
from typing import AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..state import StateManager

DEBUG_AGENT = True

class AgentService:
    """
    Manages the Backboard AI Agent lifecycle.
    Handles assistant creation, thread management, and streaming chat.
    """
    
    def __init__(self):
        """Initialize the Backboard client."""
        api_key = os.getenv("BACKBOARD")
        if not api_key:
            raise ValueError("BACKBOARD environment variable is required")
        
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
                description=""
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
        
        if DEBUG_AGENT:
            print(f"[AgentService] Streaming message to {thread_id}: {content}")

        stream = await self.client.add_message(
            thread_id=thread_id,
            content=content,
            memory="Auto",  # Enable automatic memory management
            stream=True
        )
        async for chunk in stream:
            if DEBUG_AGENT:
                print(f"[AgentService] Stream chunk: {chunk}")
            yield chunk

    async def track_execution(
        self,
        thread_id: str,
        command_id: str,
        params: Dict[str, str],
        timestamp: Optional[str] = None,
        state_manager: Optional["StateManager"] = None,
    ) -> None:
        """
        Track a command execution by sending it to the agent's memory.
        Enriches market IDs with human-readable details.
        
        Args:
            thread_id: The conversation thread ID
            command_id: The command that was executed
            params: The parameters used
            timestamp: ISO timestamp of execution
            state_manager: Optional StateManager to lookup market details
        """
        if not self.assistant_id:
            raise RuntimeError("Assistant not initialized. Call initialize() first.")
        
        # Build base prompt
        prompt_parts = [
            f"SYSTEM: Remember this command execution for future reference:\n",
            f"Command: {command_id}",
            f"Parameters: {json.dumps(params)}",
        ]
        
        # Enrich market IDs with human-readable details
        if state_manager:
            market_details = []
            for param_name, param_value in params.items():
                # Check if this looks like a market ID
                if isinstance(param_value, str) and (
                    param_value.startswith("0x") or param_value.startswith("KX")
                ):
                    market = state_manager.get_market(param_value)
                    if market:
                        market_details.append(
                            f"  {param_name}: \"{market.title}\" ({market.source})"
                        )
            
            if market_details:
                prompt_parts.append(f"Market Details:")
                prompt_parts.extend(market_details)
        
        prompt_parts.append(f"Time: {timestamp or 'now'}")
        prompt_parts.append("\nStore this in your memory to help with future parameter suggestions.")
        
        prompt = "\n".join(prompt_parts)
        
        if DEBUG_AGENT:
            print(f"[AgentService] Tracking execution: {command_id} with params {params}")
        
        # Send to agent with memory enabled, but don't wait for/use response
        try:
            await self.client.add_message(
                thread_id=thread_id,
                content=prompt,
                memory="Auto",
                stream=False,
            )
        except Exception as e:
            print(f"[AgentService] Error tracking execution: {e}")

    async def suggest_params(
        self,
        thread_id: str,
        command_id: str,
        params: List[Dict[str, str]],
        current_params: Optional[Dict[str, str]] = None,
        state_manager: Optional["StateManager"] = None,
    ) -> Dict:
        """
        Generate parameter suggestions for a command using memory and market search.
        """
        if not self.assistant_id:
            raise RuntimeError("Assistant not initialized. Call initialize() first.")

        # Step 1: Ask agent to extract keywords from memory + current params
        keywords = await self._extract_keywords(thread_id, command_id, params, current_params)
        
        # Step 2: Use keywords to search markets
        market_summary = ""
        if state_manager and keywords:
            market_summary = await self._search_markets(keywords, state_manager)
        
        # Step 3: Generate suggestions with market context
        prompt = self._build_suggestion_prompt(
            command_id,
            params,
            market_summary,
            current_params,
        )

        if DEBUG_AGENT:
            print(
                "[AgentService] Suggestion prompt for "
                f"{command_id} (thread {thread_id}):\n{prompt}"
            )

        response = await self.client.add_message(
            thread_id=thread_id,
            content=prompt,
            memory="Auto",
            stream=False,
        )
        
        # Extract content from response
        response_content = ""
        if hasattr(response, 'content'):
            response_content = str(response.content)
        else:
            response_content = str(response)
            
        response_content = response_content.replace("```json", "").replace("```", "")

        if DEBUG_AGENT:
            print(f"[AgentService] Raw suggestion response: {response_content}")

        try:
            parsed_response = json.loads(response_content)
        except Exception as e:
            if DEBUG_AGENT:
                print(f"[AgentService] Invalid JSON returned by the model: {e}")
            return {}
        
        # Validate the parsed JSON directly (it's already parsed, don't parse again)
        validated_suggestions = {}
        if isinstance(parsed_response, dict):
            for param_name, suggestion in parsed_response.items():
                if isinstance(suggestion, dict) and suggestion.get("type") in ["direct", "market_list"]:
                    validated_suggestions[param_name] = suggestion

        if DEBUG_AGENT:
            print(f"[AgentService] Parsed suggestions: {validated_suggestions}")

        return validated_suggestions
    
    async def _extract_keywords(
        self,
        thread_id: str,
        command_id: str,
        params: List[Dict[str, str]],
        current_params: Optional[Dict[str, str]],
    ) -> List[str]:
        """Extract search keywords from command history memory."""
        prompt = (
            f"Based on your memory of past user actions and the command they're about to execute, "
            f"generate 2-4 search keywords for finding relevant prediction markets.\n\n"
            f"Command: {command_id}\n"
            f"Parameters: {[p['name'] for p in params]}\n"
        )
        if current_params:
            prompt += f"Current values: {json.dumps(current_params)}\n"
        
        prompt += (
            "\nRespond with ONLY a JSON array of keyword strings, nothing else. "
            "Example: [\"trump\", \"election\", \"2024\"]\n"
            "If no good keywords, return: []"
        )
        
        try:
            response = await self.client.add_message(
                thread_id=thread_id,
                content=prompt,
                memory="Auto",
                stream=False,
            )
            
            # Extract content
            content = ""
            if hasattr(response, 'content'):
                content = str(response.content)
            else:
                content = str(response)
                
            content = content.strip().replace("```json", "").replace("```", "").strip()
            
            keywords = json.loads(content)
            if isinstance(keywords, list):
                return [str(k) for k in keywords[:4]]  # Max 4 keywords
            return []
        except Exception as e:
            if DEBUG_AGENT:
                print(f"[AgentService] Failed to extract keywords: {e}")
            return []
    
    async def _search_markets(
        self,
        keywords: List[str],
        state_manager: "StateManager",
    ) -> str:
        """Search markets and build compact summary."""
        from ..search_helper import search_markets
        
        all_markets = []
        for keyword in keywords[:3]:  # Max 3 keywords
            markets, total, facets = search_markets(
                state=state_manager,
                q=keyword,
                limit=3,  # Max 3 per keyword
            )
            all_markets.extend(markets)
        
        # Deduplicate by market_id
        seen = set()
        unique_markets = []
        for m in all_markets:
            if m.market_id not in seen:
                seen.add(m.market_id)
                unique_markets.append(m)
        
        # Cap at 10 total markets
        unique_markets = unique_markets[:10]
        
        if not unique_markets:
            return ""
        
        # Build compact summary
        lines = ["Available markets from search:"]
        for m in unique_markets:
            # Truncate title if too long
            title = m.title[:60] + "..." if len(m.title) > 60 else m.title
            lines.append(f"- ID: {m.market_id} | {title} | {m.source}")
        
        return "\n".join(lines)

    def _build_suggestion_prompt(
        self,
        command_id: str,
        params: List[Dict[str, str]],
        context: str,
        current_params: Optional[Dict[str, str]],
    ) -> str:
        param_descriptions = [
            f"- {param['name']} (type: {param['type']})" for param in params
        ]

        current_params_block = ""
        if current_params:
            current_params_block = f"\nCurrent params: {current_params}\n"

        prompt = (
            "Based on the user's command execution history, suggest default "
            f"parameter values for the '{command_id}' command.\n\n"
            "Command Parameters:\n"
            f"{chr(10).join(param_descriptions)}\n\n"
            f"{context}\n"
            f"{current_params_block}"
            "For each parameter, suggest:\n"
            "1. If type is 'market': Provide a list of 2-3 relevant market IDs with "
            "titles and reasoning\n"
            "2. If type is 'text' or 'select': Provide a single suggested value\n\n"
            "Respond in JSON format:\n"
            "{\n"
            "  \"paramName\": {\n"
            "    \"type\": \"market_list\" or \"direct\",\n"
            "    \"value\": \"suggested value\" (for direct type),\n"
            "    \"options\": [\n"
            "      {\"value\": \"market_id\", \"label\": \"Market Title\", "
            "\"reason\": \"Why suggested\"}\n"
            "    ] (for market_list type),\n"
            "    \"reasoning\": \"Brief explanation\"\n"
            "  }\n"
            "}\n\n"
            "Only suggest parameters that have clear relevant history. If no good "
            "suggestions exist, return an empty object {}."
        )

        return prompt

    def _parse_suggestions(
        self,
        response: Dict,
        params: List[Dict[str, str]],
    ) -> Dict:
        import json

        try:
            content = response.get("content", "")

            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                content = content[start:end].strip()

            suggestions = json.loads(content)

            validated_suggestions = {}
            for param_name, suggestion in suggestions.items():
                if suggestion.get("type") in ["direct", "market_list"]:
                    validated_suggestions[param_name] = suggestion

            return validated_suggestions
        except Exception as error:
            print(f"[AgentService] Failed to parse suggestions: {error}")
            return {}

    # ==================== AGENT LOOP ====================

    # Model configuration for different phases
    PLANNER_MODEL = "google/gemini-2.0-flash-001"
    SUMMARY_MODEL = "openai/gpt-4o"

    def _build_agent_system_prompt(self, commands: List[Dict]) -> str:
        """Build system prompt with available commands for the agent."""
        commands_desc = []
        for cmd in commands:
            params_desc = ""
            if cmd.get("params"):
                params_desc = ", ".join(
                    f'{p["name"]}: {p.get("type", "text")}' 
                    for p in cmd["params"]
                )
            commands_desc.append(
                f"- {cmd['id']}: {cmd.get('description', cmd['label'])} "
                f"(params: {params_desc or 'none'})"
            )
        
        return f"""You are an AI agent that helps users build prediction market dashboards.

AVAILABLE COMMANDS:
{chr(10).join(commands_desc)}

INSTRUCTIONS:
1. Analyze the user's request
2. Select which commands to execute to fulfill the request
3. Return a JSON response with your plan

CRITICAL RULES:
- If the user asks for a specific market (e.g., "Bitcoin", "Trump"), you MUST use "search-markets" FIRST to find the correct Market ID.
- STOP after searching. Do NOT try to open the panel in the same step. Wait for the search results to get the correct ID.
- NEVER guess a market ID or use a placeholder like "Bitcoin Market ID".
- After opening new panels, ALWAYS run "layout-optimize" to organize the dashboard.
- Do NOT try to open a "RESEARCH" panel. Use "open-news-feed" instead.

RESPONSE FORMAT:
{{
  "reasoning": "Brief explanation of your plan",
  "actions": [
    {{"command": "command-id", "params": {{"paramName": "value"}}}}
  ],
  "done": false
}}

When all actions are complete and you've received confirmation, respond with:
{{
  "reasoning": "Summary of what was accomplished", 
  "actions": [],
  "done": true
}}

Be concise. Prefer the query-market command when user wants a complete view of a market.
Use optimize-layout after opening multiple panels."""

    async def run_agent_step(
        self,
        thread_id: str,
        prompt: str,
        commands: List[Dict],
        observations: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Run a single step of the agent loop.
        
        Args:
            thread_id: Backboard thread ID
            prompt: User's original request
            commands: Available commands from frontend
            observations: Results from previous command executions
            
        Returns:
            Dict with reasoning, actions, and done flag
        """
        if not self.assistant_id:
            raise RuntimeError("Assistant not initialized. Call initialize() first.")

        # Build the message content
        if observations is None:
            # First step - include system prompt and user request
            system_prompt = self._build_agent_system_prompt(commands)
            content = f"{system_prompt}\n\nUSER REQUEST: {prompt}"
        else:
            # Continuation - provide observation results
            obs_text = json.dumps(observations, indent=2)
            content = f"COMMAND RESULTS:\n{obs_text}\n\nContinue with the next actions, or respond with done=true if complete."

        if DEBUG_AGENT:
            print(f"[AgentService] Agent step with model: {self.PLANNER_MODEL}")
            print(f"[AgentService] Content: {content[:500]}...")

        # Call Backboard with the planner model
        try:
            response = await self.client.add_message(
                thread_id=thread_id,
                content=content,
                memory="Auto",
                stream=False,
            )
            
            # Extract content from response
            response_content = ""
            if hasattr(response, 'content'):
                response_content = str(response.content)
            else:
                response_content = str(response)
            
            if DEBUG_AGENT:
                print(f"[AgentService] Raw response: {response_content}")

            # Parse JSON from response
            return self._parse_agent_response(response_content)

        except Exception as e:
            print(f"[AgentService] Agent step error: {e}")
            return {
                "reasoning": f"Error: {str(e)}",
                "actions": [],
                "done": True,
                "error": str(e)
            }

    async def generate_summary(
        self,
        thread_id: str,
        prompt: str,
        all_observations: List[Dict],
    ) -> str:
        """
        Generate a user-friendly summary using GPT.
        
        Args:
            thread_id: Backboard thread ID
            prompt: Original user request
            all_observations: All command execution results
            
        Returns:
            Formatted summary string
        """
        if not self.assistant_id:
            raise RuntimeError("Assistant not initialized. Call initialize() first.")

        summary_prompt = f"""The user requested: "{prompt}"

Here's what was accomplished:
{json.dumps(all_observations, indent=2)}

Write a brief, friendly 1-2 sentence summary of what was done. 
Be conversational and mention specific actions taken."""

        if DEBUG_AGENT:
            print(f"[AgentService] Generating summary with model: {self.SUMMARY_MODEL}")

        try:
            response = await self.client.add_message(
                thread_id=thread_id,
                content=summary_prompt,
                memory="Auto",
                stream=False,
            )
            
            if hasattr(response, 'content'):
                return str(response.content)
            return str(response)

        except Exception as e:
            print(f"[AgentService] Summary generation error: {e}")
            return "Completed your request."

    def _parse_agent_response(self, response_content: str) -> Dict:
        """Parse the agent's JSON response."""
        try:
            content = response_content.strip()
            
            # Extract JSON from markdown code blocks if present
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                content = content[start:end].strip()

            parsed = json.loads(content)
            
            return {
                "reasoning": parsed.get("reasoning", ""),
                "actions": parsed.get("actions", []),
                "done": parsed.get("done", False),
            }

        except Exception as e:
            print(f"[AgentService] Failed to parse agent response: {e}")
            print(f"[AgentService] Raw content: {response_content}")
            return {
                "reasoning": "Failed to parse response",
                "actions": [],
                "done": True,
                "error": str(e)
            }
