import asyncio
from typing import Dict, Set, Optional, Callable
from fastapi import WebSocket

class SubscriptionManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SubscriptionManager, cls).__new__(cls)
            # Map: market_id -> Set[WebSocket]
            cls._instance.subscriptions: Dict[str, Set[WebSocket]] = {}
            # Map: market_id -> asyncio.Task
            cls._instance.polling_tasks: Dict[str, asyncio.Task] = {}
            # Method to spawn a poller (injected from main/connectors)
            cls._instance.spawner: Optional[Callable[[str], asyncio.Task]] = None
        return cls._instance

    def set_spawner(self, spawner_func: Callable[[str], asyncio.Task]):
        self.spawner = spawner_func

    async def subscribe(self, market_id: str, websocket: WebSocket):
        if market_id not in self.subscriptions:
            self.subscriptions[market_id] = set()

        self.subscriptions[market_id].add(websocket)
        print(f"[Manager] WS subscribed to {market_id}. Total: {len(self.subscriptions[market_id])}")

        # If this is the first subscriber, start polling
        if len(self.subscriptions[market_id]) == 1:
            await self._start_polling(market_id)

    async def unsubscribe(self, market_id: str, websocket: WebSocket):
        if market_id in self.subscriptions:
            if websocket in self.subscriptions[market_id]:
                self.subscriptions[market_id].remove(websocket)
                print(f"[Manager] WS unsubscribed from {market_id}. Remaining: {len(self.subscriptions[market_id])}")
            
            # If no subscribers left, stop polling
            if len(self.subscriptions[market_id]) == 0:
                await self._stop_polling(market_id)
                del self.subscriptions[market_id]

    async def unsubscribe_from_all(self, websocket: WebSocket):
        """Called when a socket disconnects entirely"""
        market_ids = list(self.subscriptions.keys())
        for market_id in market_ids:
            if websocket in self.subscriptions[market_id]:
                await self.unsubscribe(market_id, websocket)

    async def _start_polling(self, market_id: str):
        if market_id in self.polling_tasks:
            return # Already running
        
        if self.spawner:
            print(f"[Manager] Spawning poller for {market_id}")
            task = await self.spawner(market_id)  # Await the coroutine
            if task:
                self.polling_tasks[market_id] = task

    async def _stop_polling(self, market_id: str):
        if market_id in self.polling_tasks:
            print(f"[Manager] Stopping poller for {market_id}")
            task = self.polling_tasks[market_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self.polling_tasks[market_id]

    async def broadcast(self, market_id: str, message: dict):
        if market_id in self.subscriptions:
            dead_sockets = []
            for websocket in self.subscriptions[market_id]:
                try:
                    await websocket.send_json(message)
                except Exception:
                    dead_sockets.append(websocket)
            
            for ws in dead_sockets:
                await self.unsubscribe(market_id, ws)
