import asyncio
import json
from collections import defaultdict


class ProjectEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, project_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._subscribers[project_id].add(queue)
        return queue

    async def unsubscribe(self, project_id: int, queue: asyncio.Queue) -> None:
        async with self._lock:
            subscribers = self._subscribers.get(project_id)
            if not subscribers:
                return
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(project_id, None)

    async def publish(self, project_id: int, event: dict) -> None:
        async with self._lock:
            subscribers = list(self._subscribers.get(project_id, ()))
        for queue in subscribers:
            await queue.put(event)


project_event_bus = ProjectEventBus()


def format_sse_message(event_name: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_name}\ndata: {payload}\n\n"
