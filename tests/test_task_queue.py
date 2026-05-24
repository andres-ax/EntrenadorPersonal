"""Tests cola Redis de tareas."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from src.tasks import queue as tq


@pytest.mark.asyncio
async def test_schedule_idempotency(monkeypatch):
    store: dict = {}
    zset: dict = {}

    class Pipe:
        def __init__(self, r):
            self.r = r
            self.ops = []

        def hset(self, key, field=None, value=None, mapping=None):
            self.ops.append(("hset", key, field, value, mapping))
            return self

        def zadd(self, key, mapping):
            self.ops.append(("zadd", key, mapping))
            return self

        def setex(self, key, ttl, val):
            self.ops.append(("setex", key, ttl, val))
            return self

        async def execute(self):
            for op in self.ops:
                if op[0] == "hset":
                    _, key, field, value, mapping = op
                    if mapping:
                        store[key] = mapping.get("data")
                    else:
                        store[key] = value
                elif op[0] == "zadd":
                    zset.update(op[2])
                elif op[0] == "setex":
                    store[op[1]] = op[3]
            self.ops = []
            return True

    class FakeRedis:
        async def get(self, key):
            return store.get(key)

        async def setex(self, key, ttl, val):
            store[key] = val

        async def delete(self, key):
            store.pop(key, None)

        async def hset(self, key, mapping=None, field=None, value=None):
            if mapping:
                store[key] = mapping.get("data")
            else:
                store[key] = value

        async def hget(self, key, field):
            return store.get(key)

        async def zadd(self, key, mapping):
            zset.update(mapping)

        def pipeline(self):
            return Pipe(self)

        async def scan(self, cursor, match=None, count=100):
            return 0, []

        async def eval(self, *a, **k):
            return []

    async def fake_get_redis():
        return FakeRedis()

    monkeypatch.setattr(tq, "get_redis", fake_get_redis)

    run_at = datetime.now(timezone.utc) + timedelta(hours=1)
    tid1 = await tq.schedule_task(
        task_type="recordatorio",
        telegram_id=123,
        run_at=run_at,
        payload={"mensaje": "test"},
        idempotency_key="test:1",
    )
    tid2 = await tq.schedule_task(
        task_type="recordatorio",
        telegram_id=123,
        run_at=run_at,
        payload={"mensaje": "test"},
        idempotency_key="test:1",
    )
    assert tid1 is not None
    assert tid2 == tid1


@pytest.mark.asyncio
async def test_cancel_tasks(monkeypatch):
    store: dict = {}
    zset: dict = {"abc": 1.0}

    class FakeRedis:
        async def hget(self, key, field):
            return store.get(key)

        async def hset(self, key, field=None, value=None, mapping=None):
            if mapping:
                store[key] = mapping.get("data")
            elif field is not None:
                store[key] = value

        async def zrem(self, key, member):
            zset.pop(member, None)

        async def delete(self, key):
            pass

        async def scan(self, cursor, match=None, count=100):
            return 0, list(store.keys())

    import json

    store["entrenadorax:task:abc"] = json.dumps(
        {
            "id": "abc",
            "type": "escalacion",
            "telegram_id": 999,
            "status": "scheduled",
            "idempotency_key": "x",
        }
    )

    async def fake_get_redis():
        return FakeRedis()

    monkeypatch.setattr(tq, "get_redis", fake_get_redis)
    n = await tq.cancel_tasks(999, task_type="escalacion")
    assert n == 1
    assert "abc" not in zset
