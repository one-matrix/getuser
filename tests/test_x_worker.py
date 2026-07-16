# -*- coding: utf-8 -*-
"""Durable XJob worker state-machine tests."""

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from database.models import XJob
from workers.x_worker import XJobWorker


@pytest.fixture
async def x_job_store(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'x-worker.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: XJob.__table__.create(sync_connection, checkfirst=True)
        )
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield engine, factory
    await engine.dispose()


async def _seed_job(factory, **overrides):
    values = {
        "owner_user_id": "owner-1",
        "job_id": "job-1",
        "job_type": "test",
        "payload_json": '{"value":1}',
        "status": "pending",
        "priority": 0,
        "attempt_count": 0,
        "max_attempts": 3,
        "scheduled_at": 0,
        "lease_owner": "",
        "lease_expires_at": 0,
        "created_at": 1,
        "updated_at": 1,
    }
    values.update(overrides)
    async with factory() as session:
        row = XJob(**values)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


async def _load_job(factory, row_id):
    async with factory() as session:
        result = await session.execute(select(XJob).where(XJob.id == row_id))
        return result.scalar_one()


@pytest.mark.asyncio
async def test_worker_claims_due_job_and_marks_succeeded(x_job_store):
    _, factory = x_job_store
    row_id = await _seed_job(factory)
    seen = []

    async def handler(job):
        seen.append((job.job_id, job.payload, job.attempt_count))
        return {"stored": True}

    worker = XJobWorker(
        factory,
        {"test": handler},
        worker_id="worker-a",
        clock_ms=lambda: 10_000,
    )
    assert await worker.run_once() == "job-1"

    row = await _load_job(factory, row_id)
    assert seen == [("job-1", {"value": 1}, 1)]
    assert row.status == "succeeded"
    assert row.attempt_count == 1
    assert json.loads(row.result_json) == {"stored": True}
    assert row.lease_owner == ""
    assert row.lease_expires_at == 0


@pytest.mark.asyncio
async def test_worker_retries_then_succeeds_when_due(x_job_store):
    _, factory = x_job_store
    row_id = await _seed_job(factory)
    now = [20_000]
    calls = 0

    async def handler(_job):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary failure")
        return {"attempt": calls}

    worker = XJobWorker(
        factory,
        {"test": handler},
        worker_id="worker-a",
        retry_delay_seconds=10,
        clock_ms=lambda: now[0],
    )
    await worker.run_once()
    row = await _load_job(factory, row_id)
    assert row.status == "retry_wait"
    assert row.attempt_count == 1
    assert row.scheduled_at == 30_000
    assert "temporary failure" in row.last_error

    assert await worker.run_once() is None
    now[0] = 30_000
    assert await worker.run_once() == "job-1"
    row = await _load_job(factory, row_id)
    assert row.status == "succeeded"
    assert row.attempt_count == 2


@pytest.mark.asyncio
async def test_worker_marks_failed_at_max_attempts(x_job_store):
    _, factory = x_job_store
    row_id = await _seed_job(factory, max_attempts=1)

    async def handler(_job):
        raise RuntimeError("permanent after final attempt")

    worker = XJobWorker(
        factory,
        {"test": handler},
        worker_id="worker-a",
        clock_ms=lambda: 40_000,
    )
    await worker.run_once()

    row = await _load_job(factory, row_id)
    assert row.status == "failed"
    assert row.attempt_count == 1
    assert row.finished_at == 40_000
    assert "final attempt" in row.last_error


@pytest.mark.asyncio
async def test_worker_reclaims_expired_lease(x_job_store):
    _, factory = x_job_store
    row_id = await _seed_job(
        factory,
        status="running",
        attempt_count=1,
        lease_owner="dead-worker",
        lease_expires_at=49_000,
    )

    async def handler(job):
        return {"attempt": job.attempt_count}

    worker = XJobWorker(
        factory,
        {"test": handler},
        worker_id="worker-b",
        clock_ms=lambda: 50_000,
    )
    await worker.run_once()

    row = await _load_job(factory, row_id)
    assert row.status == "succeeded"
    assert row.attempt_count == 2
    assert json.loads(row.result_json) == {"attempt": 2}


@pytest.mark.asyncio
async def test_worker_fails_expired_lease_after_max_attempts(x_job_store):
    _, factory = x_job_store
    row_id = await _seed_job(
        factory,
        status="running",
        attempt_count=3,
        max_attempts=3,
        lease_owner="dead-worker",
        lease_expires_at=54_000,
    )
    worker = XJobWorker(
        factory,
        {"test": lambda _job: {"unexpected": True}},
        worker_id="worker-b",
        clock_ms=lambda: 55_000,
    )

    assert await worker.run_once() is None
    row = await _load_job(factory, row_id)
    assert row.status == "failed"
    assert row.finished_at == 55_000
    assert "lease expired" in row.last_error


@pytest.mark.asyncio
async def test_worker_unknown_job_type_fails_without_retry(x_job_store):
    _, factory = x_job_store
    row_id = await _seed_job(factory, job_type="missing")
    worker = XJobWorker(factory, {}, worker_id="worker-a", clock_ms=lambda: 60_000)

    await worker.run_once()
    row = await _load_job(factory, row_id)
    assert row.status == "failed"
    assert row.attempt_count == 1
    assert "no handler registered" in row.last_error


@pytest.mark.asyncio
async def test_worker_does_not_claim_future_or_foreign_leased_job(x_job_store):
    _, factory = x_job_store
    future_id = await _seed_job(factory, job_id="future", scheduled_at=80_000)
    leased_id = await _seed_job(
        factory,
        job_id="leased",
        status="running",
        attempt_count=1,
        lease_owner="worker-z",
        lease_expires_at=80_000,
    )
    worker = XJobWorker(
        factory,
        {"test": lambda _job: {"unexpected": True}},
        worker_id="worker-a",
        clock_ms=lambda: 70_000,
    )

    assert await worker.run_once() is None
    assert (await _load_job(factory, future_id)).status == "pending"
    assert (await _load_job(factory, leased_id)).lease_owner == "worker-z"
