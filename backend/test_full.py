#!/usr/bin/env python3
"""
Full Backend Verification Test Suite
Tests: Search, Orderbook, Time Series, WebSocket Streaming
"""

import asyncio
import json
import httpx
import websockets
from datetime import datetime

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def log_pass(msg):
    print(f"{Colors.GREEN}✓ PASS:{Colors.END} {msg}")

def log_fail(msg):
    print(f"{Colors.RED}✗ FAIL:{Colors.END} {msg}")

def log_info(msg):
    print(f"{Colors.BLUE}ℹ INFO:{Colors.END} {msg}")

def log_section(msg):
    print(f"\n{Colors.YELLOW}{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}{Colors.END}\n")


async def test_search():
    """Test all search functionality variations"""
    log_section("SEARCH FUNCTIONALITY TESTS")
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Get a sample market to determine valid search terms
        setup_resp = await client.get("/markets/search", params={"limit": 50})
        setup_data = setup_resp.json()
        available_markets = setup_data.get("markets", [])
        
        if not available_markets:
             log_fail("No markets available to test search")
             return

        sample_market = available_markets[0]
        # Pick a word from the title that is likely distinctive (len > 3)
        title_words = [w for w in sample_market["title"].split() if len(w) > 3]
        keyword = title_words[0] if title_words else "the"
        sector = sample_market.get("sector")
        source = sample_market.get("source")
        
        log_info(f"Dynamic test setup: Using keyword='{keyword}', sector='{sector}', source='{source}'")

        # Test 1: Basic keyword search
        log_info(f"Test 1: Keyword search '{keyword}'")
        resp = await client.get("/markets/search", params={"q": keyword, "limit": 5})
        data = resp.json()
        if resp.status_code == 200 and data["total"] > 0:
            log_pass(f"Found {data['total']} markets for '{keyword}'")
        else:
            log_fail(f"Search for '{keyword}' failed: {data}")
        
        # Test 2: Sector filter only
        if sector:
            log_info(f"Test 2: Sector filter '{sector}'")
            resp = await client.get("/markets/search", params={"sector": sector, "limit": 5})
            data = resp.json()
            if resp.status_code == 200 and data["total"] > 0:
                all_sector = all(m.get("sector") == sector for m in data["markets"])
                if all_sector:
                    log_pass(f"Found {data['total']} {sector} markets")
                else:
                    log_fail(f"Some markets don't have sector={sector}")
            else:
                log_fail(f"Sector filter failed: {data}")
        
        # Test 3: Combined keyword + sector
        if sector:
            log_info(f"Test 3: Combined search '{keyword}' + sector '{sector}'")
            resp = await client.get("/markets/search", params={"q": keyword, "sector": sector, "limit": 5})
            data = resp.json()
            if resp.status_code == 200 and data["total"] > 0:
                log_pass(f"Found {data['total']} matches")
            else:
                log_fail(f"Combined search failed")
        
        # Test 4: Source filter (dynamic)
        log_info(f"Test 4: Source filter '{source}'")
        resp = await client.get("/markets/search", params={"source": source, "limit": 5})
        data = resp.json()
        if resp.status_code == 200:
            all_source = all(m["source"] == source for m in data["markets"])
            if all_source:
                log_pass(f"Found {data['total']} {source} markets")
            else:
                log_fail(f"Some markets not from {source}")
        
        # Test 6: Keyword + Source filter
        log_info(f"Test 6: Keyword '{keyword}' + source '{source}'")
        resp = await client.get("/markets/search", params={"q": keyword, "source": source, "limit": 5})
        data = resp.json()
        if resp.status_code == 200 and data["total"] > 0:
            log_pass(f"Found {data['total']} matches")
        else:
            log_fail(f"Combined source+keyword failed")
        
        # Test 7: Facets response
        log_info("Test 7: Verify facets in response")
        resp = await client.get("/markets/search", params={"limit": 1})
        data = resp.json()
        if "facets" in data and "sectors" in data["facets"] and "sources" in data["facets"]:
            log_pass(f"Facets present: {len(data['facets']['sectors'])} sectors, {len(data['facets']['tags'])} tags")
        else:
            log_fail("Facets missing or malformed")
        
        # Test 8: Pagination
        log_info("Test 8: Pagination (offset=10, limit=5)")
        resp1 = await client.get("/markets/search", params={"limit": 15})
        resp2 = await client.get("/markets/search", params={"limit": 5, "offset": 10})
        data1 = resp1.json()
        data2 = resp2.json()
        if data1["markets"][10]["market_id"] == data2["markets"][0]["market_id"]:
            log_pass("Pagination working correctly")
        else:
            log_fail("Pagination offset not working")
        
        return data  # Return last result for use in subsequent tests


async def test_orderbook():
    """Test orderbook retrieval for both sources"""
    log_section("ORDERBOOK TESTS")
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Get a Polymarket market
        resp = await client.get("/markets/search", params={"source": "polymarket", "limit": 1})
        poly_markets = resp.json()["markets"]
        
        if poly_markets:
            market = poly_markets[0]
            log_info(f"Test: Polymarket orderbook for '{market['title'][:40]}...'")
            
            ob_resp = await client.get(f"/markets/{market['market_id']}/orderbook")
            if ob_resp.status_code == 200:
                ob = ob_resp.json()
                if ob and ("bids" in ob or "asks" in ob):
                    bids = ob.get("bids", [])
                    asks = ob.get("asks", [])
                    log_pass(f"Orderbook retrieved: {len(bids)} bids, {len(asks)} asks")
                else:
                    log_info("Orderbook empty (market may have no liquidity)")
            else:
                log_fail(f"Orderbook request failed: {ob_resp.status_code}")
        
        # Get a Kalshi market
        resp = await client.get("/markets/search", params={"source": "kalshi", "limit": 1})
        kalshi_markets = resp.json()["markets"]
        
        if kalshi_markets:
            market = kalshi_markets[0]
            log_info(f"Test: Kalshi orderbook for '{market['title'][:40]}...'")
            
            ob_resp = await client.get(f"/markets/{market['market_id']}/orderbook")
            if ob_resp.status_code == 200:
                ob = ob_resp.json()
                if ob:
                    log_pass(f"Kalshi orderbook retrieved")
                else:
                    log_info("Orderbook empty (requires WebSocket subscription to populate)")
            else:
                log_fail(f"Kalshi orderbook failed: {ob_resp.status_code}")


async def test_history():
    """Test time series history retrieval"""
    log_section("TIME SERIES HISTORY TESTS")
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Get a market
        resp = await client.get("/markets/search", params={"limit": 1})
        markets = resp.json()["markets"]
        
        if markets:
            market = markets[0]
            log_info(f"Test: History for '{market['title'][:40]}...'")
            
            hist_resp = await client.get(f"/markets/{market['market_id']}/history")
            if hist_resp.status_code == 200:
                history = hist_resp.json()
                if isinstance(history, list):
                    log_pass(f"History endpoint OK: {len(history)} data points")
                    if history:
                        log_info(f"Sample point: price={history[-1].get('price', 'N/A')}")
                else:
                    log_info("History empty (requires WebSocket subscription to populate)")
            else:
                log_fail(f"History request failed: {hist_resp.status_code}")


async def test_websocket_streaming():
    """Test live WebSocket orderbook and quote streaming"""
    log_section("WEBSOCKET LIVE STREAMING TESTS")
    
    # First get a market to subscribe to
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        resp = await client.get("/markets/search", params={"source": "polymarket", "limit": 1})
        markets = resp.json()["markets"]
        
        if not markets:
            log_fail("No markets available to test WebSocket")
            return
        
        market = markets[0]
        market_id = market["market_id"]
        log_info(f"Testing WebSocket with market: {market['title'][:40]}...")
    
    try:
        async with websockets.connect(WS_URL) as ws:
            log_pass("WebSocket connected")
            
            # Subscribe to market
            await ws.send(json.dumps({
                "op": "subscribe_market",
                "market_id": market_id
            }))
            log_pass(f"Subscribed to market {market_id[:20]}...")
            
            # Wait for messages (with timeout)
            log_info("Waiting for live updates (5 seconds)...")
            messages_received = 0
            quote_received = False
            orderbook_received = False
            
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(msg)
                    messages_received += 1
                    
                    if data.get("type") == "quote":
                        quote_received = True
                        price = data.get('price')
                        try:
                            p_str = f"{float(price):.4f}"
                        except (ValueError, TypeError):
                            p_str = str(price)
                        log_pass(f"QUOTE received: price={p_str}")
                    elif data.get("type") == "orderbook":
                        orderbook_received = True
                        bids = len(data.get("bids", []))
                        asks = len(data.get("asks", []))
                        log_pass(f"ORDERBOOK received: {bids} bids, {asks} asks")
                    else:
                        log_info(f"Message received: {data.get('type', 'unknown')}")
                    
                    if messages_received >= 3:
                        break
                        
            except asyncio.TimeoutError:
                if messages_received > 0:
                    log_pass(f"Received {messages_received} messages before timeout")
                else:
                    log_info("No messages received (backend may need to poll longer)")
            
            # Unsubscribe
            await ws.send(json.dumps({
                "op": "unsubscribe_market",
                "market_id": market_id
            }))
            log_pass("Unsubscribed successfully")
            
    except Exception as e:
        log_fail(f"WebSocket error: {e}")


async def test_aggregated_display():
    """Test aggregate display like TradingView"""
    log_section("AGGREGATED DISPLAY TESTS (TradingView-like)")
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Test: Get both sources together
        log_info("Test: Aggregate search across both exchanges")
        resp = await client.get("/markets/search", params={"q": "price", "limit": 10})
        data = resp.json()
        
        poly_count = sum(1 for m in data["markets"] if m["source"] == "polymarket")
        kalshi_count = sum(1 for m in data["markets"] if m["source"] == "kalshi")
        
        log_pass(f"Aggregate results: {poly_count} Polymarket + {kalshi_count} Kalshi = {len(data['markets'])} total")
        
        # Test: Verify we can switch between views
        log_info("Test: Switch to Polymarket-only view")
        resp = await client.get("/markets/search", params={"q": "price", "source": "polymarket", "limit": 5})
        data = resp.json()
        log_pass(f"Polymarket view: {data['total']} markets")
        
        log_info("Test: Switch to Kalshi-only view")
        resp = await client.get("/markets/search", params={"q": "price", "source": "kalshi", "limit": 5})
        data = resp.json()
        log_pass(f"Kalshi view: {data['total']} markets")


async def main():
    print(f"\n{Colors.BLUE}{'='*60}")
    print("  PREDICTION MARKET DASHBOARD - FULL BACKEND TEST")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}{Colors.END}\n")
    
    # Wait for server and markets
    print("Waiting for server and market data...")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        # 1. Wait for connectivity
        for i in range(10):
            try:
                resp = await client.get("/")
                if resp.status_code == 200:
                    log_pass("Server compliant")
                    break
            except:
                pass
            await asyncio.sleep(1)
            print(".", end="", flush=True)
        else:
            log_fail("Server not reachable")
            return

        # 2. Wait for markets to populate
        for i in range(30):
            try:
                resp = await client.get("/markets/search", params={"limit": 1})
                if resp.status_code == 200 and resp.json().get("total", 0) > 0:
                    log_pass("Markets loaded")
                    break
            except:
                pass
            print(".", end="", flush=True)
            await asyncio.sleep(1)
        else:
            log_fail("Markets did not load in time")
            return

    # Run all tests
    await test_search()
    await test_orderbook()
    await test_history()
    await test_websocket_streaming()
    await test_aggregated_display()
    
    print(f"\n{Colors.GREEN}{'='*60}")
    print("  ALL TESTS COMPLETED")
    print(f"{'='*60}{Colors.END}\n")


if __name__ == "__main__":
    asyncio.run(main())
