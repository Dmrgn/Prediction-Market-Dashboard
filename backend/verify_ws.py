import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://127.0.0.1:8000/ws"
    async with websockets.connect(uri) as websocket:
        print("Connected to WS")
        
        # Test Subscription
        # We need a valid market ID. Polymarket IDs are usually Condition IDs or Slugs (if we support lookup).
        # Let's try a known slug or ID from our initial list if we knew one.
        # Since we don't know exact ID without running, let's try a dummy subscription 
        # that might fail to spawn but will hit the manager logic.
        # Ideally, we should fetch /markets first to get an ID.
        
        print("Sending subscription...")
        await websocket.send(json.dumps({
            "op": "subscribe_market", 
            "market_id": "test_id" # This won't work unless we have a real ID, but tests flow.
        }))
        
        # Listen for a few seconds
        try:
            while True:
                msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"Received: {msg[:100]}...") 
        except asyncio.TimeoutError:
            print("No messages received (Expected if 'test_id' is invalid)")

if __name__ == "__main__":
    asyncio.run(test_ws())
