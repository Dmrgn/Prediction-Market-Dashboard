import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://127.0.0.1:8000/ws"
    async with websockets.connect(uri) as websocket:
        print("Connected to WS")
        
        # Send subscribe (optional, backend currently broadcasts everything)
        await websocket.send(json.dumps({"op": "subscribe"}))
        
        # Listen for a few seconds
        try:
            while True:
                msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"Received: {msg[:100]}...") # Print first 100 chars
                # If we receive anything, it works.
                break
        except asyncio.TimeoutError:
            print("No messages received in 5s (expected if no market updates)")

if __name__ == "__main__":
    asyncio.run(test_ws())
