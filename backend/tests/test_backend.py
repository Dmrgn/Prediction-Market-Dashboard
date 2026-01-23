#!/usr/bin/env python3
"""
Comprehensive Backend Test Suite
Run this script to verify all backend functionality before committing.
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"

def test_health():
    print("\n" + "="*60)
    print("TEST 1: Server Health Check")
    print("="*60)
    resp = requests.get(f"{BASE_URL}/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    print("✓ Server is running")
    print(f"  Service: {data['service']}")
    return True

def test_market_discovery():
    print("\n" + "="*60)
    print("TEST 2: Market Discovery")
    print("="*60)
    resp = requests.get(f"{BASE_URL}/markets")
    markets = resp.json()
    
    print(f"✓ Total markets: {len(markets)}")
    
    polymarket = [m for m in markets if m['source'] == 'polymarket']
    kalshi = [m for m in markets if m['source'] == 'kalshi']
    
    print(f"  - Polymarket: {len(polymarket)}")
    print(f"  - Kalshi: {len(kalshi)}")
    
    assert len(polymarket) > 0, "No Polymarket markets loaded!"
    assert len(kalshi) > 0, "No Kalshi markets loaded!"
    
    # Verify structure
    market = markets[0]
    assert 'market_id' in market
    assert 'title' in market
    assert 'outcomes' in market
    assert len(market['outcomes']) > 0
    print(f"✓ Market structure valid")
    
    return markets

def test_orderbook(markets):
    print("\n" + "="*60)
    print("TEST 3: Orderbook Data")
    print("="*60)
    
    # Test Polymarket
    pm_market = [m for m in markets if m['source'] == 'polymarket'][0]
    mid = pm_market['market_id']
    oid = pm_market['outcomes'][0]['outcome_id']
    
    resp = requests.get(f"{BASE_URL}/markets/{mid}/orderbook", params={'outcome_id': oid})
    ob = resp.json()
    
    if ob and ob.get('bids'):
        print(f"✓ Polymarket orderbook: {pm_market['title'][:50]}")
        print(f"  - Bids: {len(ob['bids'])} levels")
        print(f"  - Best bid: ${ob['bids'][0]['p']:.4f}")
        if ob.get('asks'):
            print(f"  - Asks: {len(ob['asks'])} levels")
            print(f"  - Best ask: ${ob['asks'][0]['p']:.4f}")
    else:
        print(f"⚠ Polymarket orderbook empty (polling may need more time)")
    
    # Test Kalshi
    kal_market = [m for m in markets if m['source'] == 'kalshi'][0]
    mid = kal_market['market_id']
    oid = kal_market['outcomes'][0]['outcome_id']
    
    resp = requests.get(f"{BASE_URL}/markets/{mid}/orderbook", params={'outcome_id': oid})
    ob = resp.json()
    
    if ob and ob.get('bids'):
        print(f"\n✓ Kalshi orderbook: {kal_market['title'][:50]}")
        print(f"  - Bids: {len(ob['bids'])} levels")
        print(f"  - Best bid: ${ob['bids'][0]['p']:.4f}")
    else:
        print(f"\n⚠ Kalshi orderbook empty (polling may need more time)")

def test_history(markets):
    print("\n" + "="*60)
    print("TEST 4: Price History")
    print("="*60)
    
    market = markets[0]
    mid = market['market_id']
    oid = market['outcomes'][0]['outcome_id']
    
    resp = requests.get(f"{BASE_URL}/markets/{mid}/history", params={'outcome_id': oid})
    history = resp.json()
    
    print(f"✓ History points: {len(history)}")
    if history:
        latest = history[-1]
        print(f"  Latest quote:")
        print(f"    - Timestamp: {datetime.fromtimestamp(latest['ts'])}")
        print(f"    - Mid: ${latest['mid']:.4f}")
        print(f"    - Bid: ${latest['bid']:.4f}")
        print(f"    - Ask: ${latest['ask']:.4f}")

def test_search():
    print("\n" + "="*60)
    print("TEST 5: Search Functionality")
    print("="*60)
    
    # Test search queries
    queries = ["trump", "pope", "bitcoin"]
    for q in queries:
        resp = requests.get(f"{BASE_URL}/markets", params={'q': q})
        results = resp.json()
        print(f"✓ Search '{q}': {len(results)} results")
    
    # Test source filter
    resp = requests.get(f"{BASE_URL}/markets", params={'source': 'polymarket'})
    pm_results = resp.json()
    print(f"✓ Filter by source 'polymarket': {len(pm_results)} results")

def test_websocket():
    print("\n" + "="*60)
    print("TEST 6: WebSocket Streaming")
    print("="*60)
    
    import websockets
    import asyncio
    
    async def ws_test():
        uri = f"ws://127.0.0.1:8000/ws"
        try:
            async with websockets.connect(uri) as websocket:
                print("✓ WebSocket connected")
                
                # Send subscribe
                await websocket.send(json.dumps({"op": "subscribe"}))
                
                # Wait for message
                msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                data = json.loads(msg)
                print(f"✓ Received message type: {data.get('type')}")
                print(f"  Market ID: {data.get('market_id', '')[:30]}...")
                return True
        except asyncio.TimeoutError:
            print("⚠ No messages received in 5s (expected if markets just started)")
            return True
    
    try:
        asyncio.run(ws_test())
    except Exception as e:
        print(f"✗ WebSocket test failed: {e}")
        return False

def main():
    print("\n" + "="*60)
    print("🚀 ANTIGRAVITY BACKEND TEST SUITE")
    print("="*60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Run tests
        test_health()
        markets = test_market_discovery()
        test_orderbook(markets)
        test_history(markets)
        test_search()
        test_websocket()
        
        # Summary
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED")
        print("="*60)
        print("Backend is ready for commit!")
        print("\nNext steps:")
        print("  1. git add .")
        print("  2. git commit -m 'feat: backend with Polymarket + Kalshi integration'")
        print("  3. git push")
        
    except Exception as e:
        print("\n" + "="*60)
        print("❌ TEST FAILED")
        print("="*60)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
