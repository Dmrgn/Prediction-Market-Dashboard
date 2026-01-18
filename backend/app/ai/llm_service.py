"""LLM Service for parameter suggestions using OpenRouter API."""

import os
import json
import requests
import asyncio
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..state import StateManager

DEBUG_LLM = True


class CommandExecution:
    """Represents a single command execution."""
    
    def __init__(
        self,
        command_id: str,
        params: Dict[str, str],
        timestamp: str,
        market_details: Optional[Dict[str, Dict[str, str]]] = None
    ):
        self.command_id = command_id
        self.params = params
        self.timestamp = timestamp
        self.market_details: Dict[str, Dict[str, str]] = market_details or {}
    
    def to_dict(self) -> dict:
        return {
            "command_id": self.command_id,
            "params": self.params,
            "timestamp": self.timestamp,
            "market_details": self.market_details
        }


class LLMService:
    """
    LLM service for AI-powered parameter suggestions using OpenRouter.
    Maintains global command history (last 15 executions) and uses it
    to provide contextual parameter suggestions.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the LLM service.
        
        Args:
            api_key: OpenRouter API key (defaults to OPENROUTER_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable is required")
        
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "openai/gpt-oss-120b"
        
        # Global command history (last 15 commands across all users)
        self.command_history: deque[CommandExecution] = deque(maxlen=15)
        self._history_lock = asyncio.Lock()
        
        if DEBUG_LLM:
            print(f"[LLMService] Initialized with model: {self.model}")
    
    async def track_execution(
        self,
        command_id: str,
        params: Dict[str, str],
        timestamp: Optional[str] = None,
        state_manager: Optional["StateManager"] = None
    ) -> None:
        """
        Track a command execution in global history.
        
        Args:
            command_id: The command identifier
            params: The parameters used
            timestamp: ISO timestamp (auto-generated if not provided)
            state_manager: Optional StateManager to enrich market IDs
        """
        if not timestamp:
            timestamp = datetime.utcnow().isoformat() + "Z"
        
        # Enrich market IDs with human-readable details
        market_details = {}
        if state_manager:
            for param_name, param_value in params.items():
                if isinstance(param_value, str) and (
                    param_value.startswith("0x") or param_value.startswith("KX")
                ):
                    market = state_manager.get_market(param_value)
                    if market:
                        market_details[param_name] = {
                            "title": market.title,
                            "source": market.source
                        }
        
        execution = CommandExecution(command_id, params, timestamp, market_details)
        
        async with self._history_lock:
            self.command_history.append(execution)
            
            if DEBUG_LLM:
                print(f"[LLMService] Tracked: {command_id} (total: {len(self.command_history)})")
    
    def _build_context_string(self, command_id: str) -> str:
        """
        Build context string from recent command history.
        
        Args:
            command_id: The command to generate suggestions for
            
        Returns:
            Formatted context string
        """
        if not self.command_history:
            return "No command execution history available."
        
        lines = ["Recent command executions (last 15):"]
        
        # Reverse to show most recent first
        recent_commands = list(reversed(self.command_history))
        
        for i, execution in enumerate(recent_commands, 1):
            # Build parameter string with market details if available
            param_parts = []
            for param_name, param_value in execution.params.items():
                if param_name in execution.market_details:
                    detail = execution.market_details[param_name]
                    param_parts.append(
                        f'{param_name}="{detail["title"]}" ({detail["source"]})'
                    )
                else:
                    param_parts.append(f'{param_name}="{param_value}"')
            
            params_str = ", ".join(param_parts) if param_parts else "{}"
            lines.append(f"{i}. {execution.command_id}({params_str}) at {execution.timestamp}")
        
        # Add specific context for the requested command
        same_command = [e for e in recent_commands if e.command_id == command_id]
        if same_command:
            lines.append(f"\nPrevious executions of '{command_id}':")
            for i, execution in enumerate(same_command[:5], 1):
                param_parts = []
                for param_name, param_value in execution.params.items():
                    if param_name in execution.market_details:
                        detail = execution.market_details[param_name]
                        param_parts.append(
                            f'{param_name}="{detail["title"]}" ({detail["source"]})'
                        )
                    else:
                        param_parts.append(f'{param_name}="{param_value}"')
                
                params_str = ", ".join(param_parts) if param_parts else "{}"
                lines.append(f"  {i}. {params_str} at {execution.timestamp}")
        
        return "\n".join(lines)
    
    async def _search_markets(
        self,
        keywords: List[str],
        state_manager: "StateManager"
    ) -> str:
        """
        Search markets and build compact summary.
        
        Args:
            keywords: List of search keywords
            state_manager: StateManager instance for search
            
        Returns:
            Formatted market search results
        """
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
        market_summary: str,
        current_params: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Build the prompt for parameter suggestions.
        
        Args:
            command_id: Command to suggest parameters for
            params: Parameter definitions
            context: Command execution history
            market_summary: Available markets from search
            current_params: Current parameter values
            
        Returns:
            Formatted prompt string
        """
        param_descriptions = [
            f"- {param['name']} (type: {param['type']})" for param in params
        ]
        
        current_params_block = ""
        if current_params:
            current_params_block = f"\nCurrent params: {json.dumps(current_params)}\n"
        
        market_context = ""
        if market_summary:
            market_context = f"\n{market_summary}\n"
        
        prompt = (
            f"Based on the user's command execution history, suggest default "
            f"parameter values for the '{command_id}' command.\n\n"
            f"Command Parameters:\n"
            f"{chr(10).join(param_descriptions)}\n\n"
            f"{context}\n"
            f"{market_context}"
            f"{current_params_block}"
            f"For each parameter, suggest:\n"
            f"1. If type is 'market': Provide a list of 2-3 relevant market IDs with "
            f"titles and reasoning\n"
            f"2. If type is 'text' or 'select': Provide a single suggested value\n\n"
            f"Respond in JSON format:\n"
            f"{{\n"
            f'  "paramName": {{\n'
            f'    "type": "market_list" or "direct",\n'
            f'    "value": "suggested value" (for direct type),\n'
            f'    "options": [\n'
            f'      {{"value": "market_id", "label": "Market Title", '
            f'"reason": "Why suggested"}}\n'
            f'    ] (for market_list type),\n'
            f'    "reasoning": "Brief explanation"\n'
            f"  }}\n"
            f"}}\n\n"
            f"Only suggest parameters that have clear relevant history. If no good "
            f"suggestions exist, return an empty object {{}}."
        )
        
        return prompt
    
    async def _call_openrouter(self, prompt: str) -> str:
        """
        Call OpenRouter API synchronously (runs in thread pool).
        
        Args:
            prompt: The prompt to send
            
        Returns:
            Response content from the model
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://jarvis-dashboard.local",
            "X-Title": "Jarvis Prediction Market Dashboard"
        }
        
        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.post(
                self.api_url,
                headers=headers,
                json=data,
                timeout=10
            )
        )
        
        if response.status_code != 200:
            raise Exception(
                f"OpenRouter API error: {response.status_code} - {response.text}"
            )
        
        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        return content
    
    async def suggest_params(
        self,
        command_id: str,
        params: List[Dict[str, str]],
        current_params: Optional[Dict[str, str]] = None,
        state_manager: Optional["StateManager"] = None
    ) -> Dict:
        """
        Generate parameter suggestions for a command.
        
        Args:
            command_id: The command to suggest parameters for
            params: List of parameter definitions [{"name": "marketId", "type": "market"}]
            current_params: Current parameter values (optional)
            state_manager: StateManager for market search (optional)
            
        Returns:
            Dictionary of parameter suggestions
        """
        try:
            # Build context from command history
            async with self._history_lock:
                context = self._build_context_string(command_id)
            
            # Optional: Search markets if state_manager available
            market_summary = ""
            if state_manager:
                # Extract keywords from recent commands for the same command_id
                keywords = self._extract_keywords_from_history(command_id)
                if keywords:
                    market_summary = await self._search_markets(keywords, state_manager)
            
            # Build prompt
            prompt = self._build_suggestion_prompt(
                command_id,
                params,
                context,
                market_summary,
                current_params
            )
            
            if DEBUG_LLM:
                print(f"[LLMService] Generating suggestions for {command_id}")
                print(f"[LLMService] Prompt:\n{prompt}")
            
            # Call OpenRouter API
            response_content = await self._call_openrouter(prompt)
            
            if DEBUG_LLM:
                print(f"[LLMService] Raw response:\n{response_content}")
            
            # Parse response
            suggestions = self._parse_suggestions(response_content, params)
            
            if DEBUG_LLM:
                print(f"[LLMService] Parsed suggestions: {suggestions}")
            
            return suggestions
            
        except Exception as e:
            if DEBUG_LLM:
                print(f"[LLMService] Error generating suggestions: {e}")
            return {}
    
    def _extract_keywords_from_history(self, command_id: str) -> List[str]:
        """
        Extract search keywords from command history.
        Simple implementation: look for market titles in recent executions.
        
        Args:
            command_id: Command to extract keywords for
            
        Returns:
            List of keywords
        """
        keywords = []
        
        # Look at recent executions of the same command
        for execution in reversed(self.command_history):
            if execution.command_id == command_id:
                for param_name, details in execution.market_details.items():
                    if "title" in details:
                        # Extract first few words from title as keywords
                        title = details["title"]
                        words = title.split()[:3]  # First 3 words
                        keywords.extend(words)
                        break  # Only use most recent
                
                if keywords:
                    break
        
        # Deduplicate and limit
        unique_keywords = []
        seen = set()
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower not in seen and len(kw) > 2:  # Skip short words
                seen.add(kw_lower)
                unique_keywords.append(kw)
        
        return unique_keywords[:3]  # Max 3 keywords
    
    def _parse_suggestions(
        self,
        response_content: str,
        params: List[Dict[str, str]]
    ) -> Dict:
        """
        Parse LLM response into structured suggestions.
        
        Args:
            response_content: Raw response from LLM
            params: Parameter definitions
            
        Returns:
            Structured suggestion dictionary
        """
        try:
            # Extract JSON from response (might be in code blocks)
            content = response_content.strip()
            
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                content = content[start:end].strip()
            
            # Parse JSON
            suggestions = json.loads(content)
            
            # Validate structure
            validated_suggestions = {}
            if isinstance(suggestions, dict):
                for param_name, suggestion in suggestions.items():
                    if isinstance(suggestion, dict) and suggestion.get("type") in ["direct", "market_list"]:
                        validated_suggestions[param_name] = suggestion
            
            return validated_suggestions
            
        except Exception as e:
            if DEBUG_LLM:
                print(f"[LLMService] Failed to parse suggestions: {e}")
            return {}
    
    def get_history_stats(self) -> Dict:
        """Get statistics about command history."""
        command_counts = {}
        
        for execution in self.command_history:
            command_counts[execution.command_id] = (
                command_counts.get(execution.command_id, 0) + 1
            )
        
        return {
            "total_executions": len(self.command_history),
            "command_counts": command_counts,
            "max_size": self.command_history.maxlen
        }
