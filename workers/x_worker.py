"""Durable database worker for :class:`database.models.XJob`.

The worker owns queue mechanics only: claiming, leases, attempts, retries and
terminal state transitions. Collection, analysis and publishing logic is
provided through an injectable handler registry.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import socket
import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import XJob


logger = logging.getLogger(__name__)

JobHandler = Callable[["XJobContext"], Any | Awaitable[Any]]
SessionFactory = Callable[[], AsyncSession]


class NonRetryableJobError(RuntimeError):
    """A malformed or unsupported job that should immediately fail."""


class RetryableJobError(RuntimeError):
    """A handler error with an optional explicit retry delay."""

    def __init__(self, message: str, *, retry_after_seconds: Optional[int] = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class XJobContext:
    id: int
    job_id: str
    owner_user_id: str
    job_type: str
    payload: Dict[str, Any]
    attempt_count: int
    max_attempts: int
    account_id: Optional[int] = None
    region_id: Optional[int] = None
    topic_id: Optional[int] = None
    conversation_id: Optional[int] = None
    parent_job_id: str = ""
    dedup_key: str = ""


class XJobWorker:
    """Claim and execute one X job at a time with renewable leases."""

    def __init__(
        self,
        session_factory: SessionFactory,
        handlers: Optional[Mapping[str, JobHandler]] = None,
        *,
        worker_id: Optional[str] = None,
        lease_seconds: int = 300,
        retry_delay_seconds: int = 60,
        max_retry_delay_seconds: int = 3600,
        poll_interval_seconds: float = 2.0,
        clock_ms: Optional[Callable[[], int]] = None,
    ) -> None:
        self.session_factory = session_factory
        self.handlers: Dict[str, JobHandler] = dict(handlers or {})
        self.worker_id = worker_id or _default_worker_id()
        self.lease_seconds = max(int(lease_seconds), 3)
        self.retry_delay_seconds = max(int(retry_delay_seconds), 1)
        self.max_retry_delay_seconds = max(
            int(max_retry_delay_seconds),
            self.retry_delay_seconds,
        )
        self.poll_interval_seconds = max(float(poll_interval_seconds), 0.05)
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._stop_event = asyncio.Event()

    def register_handler(self, job_type: str, handler: JobHandler) -> None:
        if not job_type or not callable(handler):
            raise ValueError("job_type and callable handler are required")
        self.handlers[job_type] = handler

    async def run_once(self) -> Optional[str]:
        """Claim and process one due job, returning its business job ID."""

        job = await self.claim_next()
        if job is None:
            return None
        await self._execute(job)
        return job.job_id

    async def run_forever(self) -> None:
        """Poll until :meth:`stop` is called or the task is cancelled."""

        self._stop_event.clear()
        while not self._stop_event.is_set():
            try:
                processed = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("X job worker polling iteration failed")
                processed = None
            if processed is None:
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.poll_interval_seconds,
                    )
                except asyncio.TimeoutError:
                    pass

    def stop(self) -> None:
        self._stop_event.set()

    async def claim_next(self) -> Optional[XJobContext]:
        """Atomically claim one due or lease-expired job.

        ``FOR UPDATE SKIP LOCKED`` is used where supported. The conditional
        UPDATE remains the final ownership check and also protects SQLite,
        whose dialect ignores row-lock clauses.
        """

        now_ms = self.clock_ms()
        eligible = _eligible_clause(now_ms)
        async with self.session_factory() as session:
            await self._fail_exhausted_expired_jobs(session, now_ms)

            result = await session.execute(
                select(XJob)
                .where(eligible, XJob.attempt_count < XJob.max_attempts)
                .order_by(
                    XJob.priority.desc(),
                    XJob.scheduled_at.asc(),
                    XJob.id.asc(),
                )
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            row = result.scalars().first()
            if row is None:
                await session.commit()
                return None
            context = self._context_from_row(
                row,
                attempt_count=(row.attempt_count or 0) + 1,
            )

            claimed = await session.execute(
                update(XJob)
                .where(
                    XJob.id == row.id,
                    _eligible_clause(now_ms),
                    XJob.attempt_count < XJob.max_attempts,
                )
                .values(
                    status="running",
                    attempt_count=XJob.attempt_count + 1,
                    started_at=now_ms,
                    finished_at=0,
                    lease_owner=self.worker_id,
                    lease_expires_at=now_ms + self.lease_seconds * 1000,
                    updated_at=now_ms,
                )
            )
            if claimed.rowcount != 1:
                await session.rollback()
                return None

            await session.commit()
            return context

    async def _execute(self, job: XJobContext) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(job.id))
        try:
            invalid_payload = job.payload.get("_invalid_payload_error")
            if invalid_payload:
                raise NonRetryableJobError(str(invalid_payload))
            handler = self.handlers.get(job.job_type)
            if handler is None:
                raise NonRetryableJobError(f"no handler registered for job type {job.job_type!r}")
            result = handler(job)
            if inspect.isawaitable(result):
                result = await result
            result_json = json.dumps(
                {} if result is None else result,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )
            await self._mark_succeeded(job, result_json)
        except asyncio.CancelledError:
            await asyncio.shield(
                self._mark_retry_or_failed(
                    job,
                    "worker execution cancelled",
                    retry_after_seconds=1,
                )
            )
            raise
        except NonRetryableJobError as exc:
            await self._mark_failed(job, str(exc))
        except RetryableJobError as exc:
            await self._mark_retry_or_failed(
                job,
                str(exc),
                retry_after_seconds=exc.retry_after_seconds,
            )
        except Exception as exc:
            logger.exception("X job %s failed", job.job_id)
            await self._mark_retry_or_failed(job, str(exc))
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass

    async def _heartbeat(self, row_id: int) -> None:
        interval = max(self.lease_seconds / 3, 1.0)
        while True:
            await asyncio.sleep(interval)
            now_ms = self.clock_ms()
            async with self.session_factory() as session:
                renewed = await session.execute(
                    update(XJob)
                    .where(
                        XJob.id == row_id,
                        XJob.status == "running",
                        XJob.lease_owner == self.worker_id,
                    )
                    .values(
                        lease_expires_at=now_ms + self.lease_seconds * 1000,
                        updated_at=now_ms,
                    )
                )
                await session.commit()
                if renewed.rowcount != 1:
                    return

    async def _mark_succeeded(self, job: XJobContext, result_json: str) -> None:
        now_ms = self.clock_ms()
        await self._update_owned_job(
            job.id,
            status="succeeded",
            result_json=result_json,
            last_error="",
            finished_at=now_ms,
            lease_owner="",
            lease_expires_at=0,
            updated_at=now_ms,
        )

    async def _mark_failed(self, job: XJobContext, error: str) -> None:
        now_ms = self.clock_ms()
        await self._update_owned_job(
            job.id,
            status="failed",
            last_error=_error_text(error),
            finished_at=now_ms,
            lease_owner="",
            lease_expires_at=0,
            updated_at=now_ms,
        )

    async def _mark_retry_or_failed(
        self,
        job: XJobContext,
        error: str,
        *,
        retry_after_seconds: Optional[int] = None,
    ) -> None:
        if job.attempt_count >= job.max_attempts:
            await self._mark_failed(job, error)
            return

        delay_seconds = (
            min(max(int(retry_after_seconds), 1), self.max_retry_delay_seconds)
            if retry_after_seconds is not None
            else self._retry_delay(job.attempt_count)
        )
        now_ms = self.clock_ms()
        await self._update_owned_job(
            job.id,
            status="retry_wait",
            scheduled_at=now_ms + delay_seconds * 1000,
            last_error=_error_text(error),
            finished_at=0,
            lease_owner="",
            lease_expires_at=0,
            updated_at=now_ms,
        )

    async def _update_owned_job(self, row_id: int, **values: Any) -> bool:
        async with self.session_factory() as session:
            result = await session.execute(
                update(XJob)
                .where(
                    XJob.id == row_id,
                    XJob.status == "running",
                    XJob.lease_owner == self.worker_id,
                )
                .values(**values)
            )
            await session.commit()
            if result.rowcount != 1:
                logger.warning("X job row %s lease was lost before state update", row_id)
                return False
            return True

    async def _fail_exhausted_expired_jobs(self, session: AsyncSession, now_ms: int) -> None:
        await session.execute(
            update(XJob)
            .where(
                XJob.status == "running",
                XJob.lease_expires_at > 0,
                XJob.lease_expires_at <= now_ms,
                XJob.attempt_count >= XJob.max_attempts,
            )
            .values(
                status="failed",
                last_error="worker lease expired after maximum attempts",
                finished_at=now_ms,
                lease_owner="",
                lease_expires_at=0,
                updated_at=now_ms,
            )
        )

    def _context_from_row(self, row: XJob, *, attempt_count: int) -> XJobContext:
        try:
            payload = json.loads(row.payload_json or "{}")
        except (TypeError, ValueError) as exc:
            payload = {"_invalid_payload_error": str(exc)}
        if not isinstance(payload, dict):
            payload = {"_invalid_payload_error": "payload_json must decode to an object"}
        return XJobContext(
            id=row.id,
            job_id=row.job_id,
            owner_user_id=row.owner_user_id,
            job_type=row.job_type,
            payload=payload,
            attempt_count=attempt_count,
            max_attempts=max(int(row.max_attempts or 1), 1),
            account_id=row.account_id,
            region_id=row.region_id,
            topic_id=row.topic_id,
            conversation_id=row.conversation_id,
            parent_job_id=row.parent_job_id or "",
            dedup_key=row.dedup_key or "",
        )

    def _retry_delay(self, attempt_count: int) -> int:
        delay = self.retry_delay_seconds * (2 ** max(attempt_count - 1, 0))
        return min(delay, self.max_retry_delay_seconds)


def _eligible_clause(now_ms: int):
    return or_(
        and_(
            XJob.status.in_(("pending", "retry_wait")),
            XJob.scheduled_at <= now_ms,
        ),
        and_(
            XJob.status == "running",
            XJob.lease_expires_at > 0,
            XJob.lease_expires_at <= now_ms,
        ),
    )


def _error_text(error: str) -> str:
    normalized = " ".join(str(error or "job failed").split())
    return normalized[:4000]


def _default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
