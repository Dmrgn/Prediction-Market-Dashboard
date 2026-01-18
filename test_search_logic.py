import asyncio
import json
from unittest.mock import MagicMock, AsyncMock
import sys
import os

# Mock the relative imports
sys.path.append(os.path.join(os.getcwd(), 'backend'))

# Create dummy classes for what we need
class Event:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

# Mock components that are imported
sys.modules['..schemas'] = MagicMock()
sys.modules['..schemas'].Event = Event
sys.modules['..state'] = MagicMock()
sys.modules['..taxonomy'] = MagicMock()

# Import the stuff to test
from backend.app.connectors.polymarket import PolymarketConnector, extract_keywords

async def test_search_logic():
    # Mock Gamma client
    gamma_client = AsyncMock()
    mock_data = [
        {"title": "Will Trump win?", "description": "Election 2024", "markets": [], "id": "1"},
        {"title": "Bitcoin price", "description": "Crypto market", "markets": [], "id": "2"},
        {"title": "NBA Finals", "description": "Sports", "markets": [], "id": "3"}
    ]
    
    # Mock response
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_data
    gamma_client.get.return_value = mock_resp
    
    # Instantiate connector with mocks
    connector = PolymarketConnector(MagicMock())
    connector.gamma_client = gamma_client
    
    # Test Trump search
    events_trump, _ = await connector.search_events("Trump")
    print(f"Search 'Trump' found: {[e.title for e in events_trump]}")
    
    # Test Bitcoin search
    events_btc, _ = await connector.search_events("Bitcoin")
    print(f"Search 'Bitcoin' found: {[e.title for e in events_btc]}")
    
    # Test missing match
    events_none, _ = await connector.search_events("Zorp")
    print(f"Search 'Zorp' found: {[e.title for e in events_none]}")

if __name__ == "__main__":
    asyncio.run(test_search_logic())
