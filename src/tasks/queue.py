"""Cola de tareas programables en Redis (ZSET + HASH)."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.cache import get_redis
from src.config import settings

logger = logging.getLogger(__name__)

DUE_KEY = "entrenadorax:tasks:due"
TASK_HASH_PREFIX = "entrenadorax:task:"
IDEM_PREFIX = "entrenadorax:task:idem:"
PROCESSING_KEY = "entrenadorax:tasks:processing"
DISPATCHER_LOCK = "entrenadorax:dispatcher:lock"

CLAIM_LUA = """
local due_key = KEYS[1]
local proc_key = KEYS[2]
local now = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local ids = redis.call('ZRANGEBYSCORE', due_key, '-inf', now, 'LIMIT', 0, limit)
local claimed = {}
for i, task_id in ipairs(ids) do
  if redis.call('ZREM', due_key, task_id) == 1 then
    redis.call('ZADD', proc_key, now, task_id)
    table.insert(claimed, task_id)
  end
end
return claimed
"""


def _task_hash_key(task_id: str) -> str:
    return f"{TASK_HASH_PREFIX}{task_id}"


async def schedule_task(
    *,
    task_type: str,
    telegram_id: int,
    run_at: datetime,
    payload: dict[str, Any] | None = None,
    timezone_name: str = "America/Bogota",
    idempotency_key: str | None = None,
    created_by: str = "system",
    recordatorio_id: int | None = None,
) -> str | None:
    """Programa tarea. Devuelve task_id o None si idempotency_key ya existe."""
    if run_at.tzinfo is None:
        run_at_utc = run_at.replace(tzinfo=timezone.utc)
    else:
        run_at_utc = run_at.astimezone(timezone.utc)
    run_ts = run_at_utc.timestamp()

    client = await get_redis()
    if idempotency_key:
        idem_key = f"{IDEM_PREFIX}{idempotency_key}"
        existing_id = await client.get(idem_key)
        if existing_id:
            task_id = existing_id
            await client.hset(
                _task_hash_key(task_id),
                mapping={
                    "data": json.dumps(
                        {
                            "id": task_id,
                            "type": task_type,
                            "telegram_id": telegram_id,
                            "run_at": run_ts,
                            "timezone": timezone_name,
                            "payload": payload or {},
                            "idempotency_key": idempotency_key,
                            "created_by": created_by,
                            "status": "scheduled",
                            "recordatorio_id": recordatorio_id,
                        },
                        ensure_ascii=False,
                    )
                },
            )
            await client.zadd(DUE_KEY, {task_id: run_ts})
            return task_id

    task_id = uuid.uuid4().hex
    doc = {
        "id": task_id,
        "type": task_type,
        "telegram_id": telegram_id,
        "run_at": run_ts,
        "timezone": timezone_name,
        "payload": payload or {},
        "idempotency_key": idempotency_key or "",
        "created_by": created_by,
        "status": "scheduled",
        "recordatorio_id": recordatorio_id,
    }
    pipe = client.pipeline()
    pipe.hset(_task_hash_key(task_id), "data", json.dumps(doc, ensure_ascii=False))
    pipe.zadd(DUE_KEY, {task_id: run_ts})
    if idempotency_key:
        pipe.setex(f"{IDEM_PREFIX}{idempotency_key}", 60 * 60 * 24 * 90, task_id)
    await pipe.execute()
    return task_id


async def cancel_tasks(
    telegram_id: int,
    task_type: str | None = None,
    idempotency_prefix: str | None = None,
) -> int:
    """Cancela tareas pendientes del usuario. Devuelve cantidad cancelada."""
    client = await get_redis()
    cancelled = 0
    cursor = 0
    while True:
        cursor, keys = await client.scan(cursor, match=f"{TASK_HASH_PREFIX}*", count=100)
        for key in keys:
            raw = await client.hget(key, "data")
            if not raw:
                continue
            try:
                doc = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if doc.get("telegram_id") != telegram_id:
                continue
            if doc.get("status") in ("done", "cancelled"):
                continue
            if task_type and doc.get("type") != task_type:
                continue
            idem = doc.get("idempotency_key") or ""
            if idempotency_prefix and not idem.startswith(idempotency_prefix):
                continue
            task_id = doc.get("id") or key.replace(TASK_HASH_PREFIX, "")
            doc["status"] = "cancelled"
            await client.hset(key, "data", json.dumps(doc, ensure_ascii=False))
            await client.zrem(DUE_KEY, task_id)
            await client.zrem(PROCESSING_KEY, task_id)
            if idem:
                await client.delete(f"{IDEM_PREFIX}{idem}")
            cancelled += 1
        if cursor == 0:
            break
    return cancelled


async def list_tasks(
    telegram_id: int,
    include_done: bool = False,
) -> list[dict[str, Any]]:
    client = await get_redis()
    out: list[dict[str, Any]] = []
    cursor = 0
    while True:
        cursor, keys = await client.scan(cursor, match=f"{TASK_HASH_PREFIX}*", count=100)
        for key in keys:
            raw = await client.hget(key, "data")
            if not raw:
                continue
            try:
                doc = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if doc.get("telegram_id") != telegram_id:
                continue
            st = doc.get("status", "scheduled")
            if not include_done and st in ("done", "cancelled"):
                continue
            out.append(doc)
        if cursor == 0:
            break
    out.sort(key=lambda d: d.get("run_at", 0))
    return out


async def claim_due_tasks(limit: int = 20) -> list[dict[str, Any]]:
    client = await get_redis()
    now = datetime.now(timezone.utc).timestamp()
    claimed_ids = await client.eval(CLAIM_LUA, 2, DUE_KEY, PROCESSING_KEY, now, limit)
    tasks: list[dict[str, Any]] = []
    for task_id in claimed_ids or []:
        raw = await client.hget(_task_hash_key(task_id), "data")
        if not raw:
            await client.zrem(PROCESSING_KEY, task_id)
            continue
        try:
            doc = json.loads(raw)
            doc["status"] = "claimed"
            await client.hset(_task_hash_key(task_id), "data", json.dumps(doc, ensure_ascii=False))
            tasks.append(doc)
        except json.JSONDecodeError:
            await client.zrem(PROCESSING_KEY, task_id)
    return tasks


async def complete_task(task_id: str, result: dict[str, Any] | None = None) -> None:
    client = await get_redis()
    key = _task_hash_key(task_id)
    raw = await client.hget(key, "data")
    if not raw:
        await client.zrem(PROCESSING_KEY, task_id)
        return
    doc = json.loads(raw)
    doc["status"] = "done"
    if result:
        doc["result"] = result
    await client.hset(key, "data", json.dumps(doc, ensure_ascii=False))
    await client.zrem(PROCESSING_KEY, task_id)
    idem = doc.get("idempotency_key")
    if idem:
        await client.delete(f"{IDEM_PREFIX}{idem}")


async def fail_task(task_id: str, error: str, retry_at: datetime | None = None) -> None:
    client = await get_redis()
    key = _task_hash_key(task_id)
    raw = await client.hget(key, "data")
    if not raw:
        return
    doc = json.loads(raw)
    doc["status"] = "failed"
    doc["error"] = error[:500]
    await client.hset(key, "data", json.dumps(doc, ensure_ascii=False))
    await client.zrem(PROCESSING_KEY, task_id)
    if retry_at:
        doc["status"] = "scheduled"
        await client.hset(key, "data", json.dumps(doc, ensure_ascii=False))
        ts = retry_at.timestamp() if retry_at.tzinfo else retry_at.replace(tzinfo=timezone.utc).timestamp()
        await client.zadd(DUE_KEY, {task_id: ts})


async def count_overdue() -> int:
    client = await get_redis()
    now = datetime.now(timezone.utc).timestamp()
    return int(await client.zcount(DUE_KEY, "-inf", now))


async def acquire_dispatcher_lock(ttl_ms: int | None = None) -> bool:
    client = await get_redis()
    ttl = ttl_ms or (settings.task_dispatcher_interval_seconds * 1000 + 5000)
    return bool(await client.set(DISPATCHER_LOCK, "1", nx=True, px=ttl))


async def release_dispatcher_lock() -> None:
    client = await get_redis()
    await client.delete(DISPATCHER_LOCK)
