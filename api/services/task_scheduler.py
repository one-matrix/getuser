# -*- coding: utf-8 -*-
"""
任务调度器 - 支持 interval/daily/weekly 自动执行任务

设计要点:
1. 轻量级实现,不引入 APScheduler/Celery 等重型依赖,使用 asyncio 后台任务 + 时间比对
2. 每分钟检查一次 crawler_task 表中已到期的 interval/daily/weekly 任务
3. 调用 start_task 同一逻辑触发执行(绕过 HTTP 层,直接调用服务函数)
4. 通过 next_scheduled_ts 字段防止重复触发
5. 单实例运行(通过 _scheduler_started 全局标志保护),适合单机部署
"""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import CrawlerTaskModel
from database.db_session import get_session


_scheduler_started = False
_scheduler_task: Optional[asyncio.Task] = None


def _calc_next_scheduled_ts(
    schedule_type: str,
    schedule_time: str,
    schedule_weekday: int,
    now_ts: int,
    interval_seconds: int = 900,
) -> int:
    """计算下次调度时间戳"""
    now = datetime.fromtimestamp(now_ts)
    hour, minute = 9, 0
    try:
        parts = schedule_time.split(":")
        parsed_hour = int(parts[0])
        parsed_minute = int(parts[1]) if len(parts) > 1 else 0
        if not 0 <= parsed_hour <= 23 or not 0 <= parsed_minute <= 59:
            raise ValueError("schedule time is outside 00:00-23:59")
        hour, minute = parsed_hour, parsed_minute
    except (AttributeError, TypeError, ValueError):
        hour, minute = 9, 0

    if schedule_type == "interval":
        return now_ts + max(60, interval_seconds or 900)
    if schedule_type == "daily":
        # 今天指定时间,若已过则明天
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return int(target.timestamp())
    elif schedule_type == "weekly":
        # 本周指定星期几的指定时间,若已过则下周
        target_weekday = max(1, min(7, schedule_weekday or 1))
        days_ahead = (target_weekday - 1) - now.weekday()
        if days_ahead < 0:
            days_ahead += 7
        target = (now + timedelta(days=days_ahead)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=7)
        return int(target.timestamp())
    return 0


async def _trigger_scheduled_task(
    task_id: str,
    owner_user_id: str,
    *,
    user_loader: Optional[Callable[[int], Awaitable[Optional[dict]]]] = None,
    task_starter: Optional[Callable[..., Awaitable[dict]]] = None,
) -> bool:
    """在调度进程内以任务所属用户身份复用 ``start_task``。

    不能通过无认证的 localhost HTTP 请求触发：任务接口要求 Bearer Token，
    且 API 监听端口不是调度器可以安全假定的固定值。
    """
    try:
        owner_id = int(str(owner_user_id or "").strip())
        if user_loader is None:
            from api.services.auth import get_user_by_id

            user_loader = get_user_by_id
        current_user = await user_loader(owner_id)
        if not current_user or current_user.get("status") != "active":
            print(f"[Scheduler] 跳过任务 {task_id}: 归属用户不存在或已禁用")
            return False

        if task_starter is None:
            from api.routers.tasks import start_task

            task_starter = start_task
        result = await task_starter(task_id, current_user=current_user)
        success = bool(result.get("success")) if isinstance(result, dict) else False
        print(f"[Scheduler] 触发任务 {task_id} 完成,success={success}")
        return success
    except (TypeError, ValueError):
        print(f"[Scheduler] 跳过任务 {task_id}: 缺少有效的 owner_user_id")
        return False
    except Exception as e:
        print(f"[Scheduler] 触发任务 {task_id} 失败: {e}")
        return False


async def _scheduler_loop():
    """调度器主循环,每分钟检查一次"""
    print("[Scheduler] 调度器主循环已启动")
    while True:
        try:
            now_ts = int(time.time())
            async with get_session() as session:
                # 查找到期且未执行的任务
                result = await session.execute(
                    select(CrawlerTaskModel).where(
                        CrawlerTaskModel.schedule_type.in_(["interval", "daily", "weekly"]),
                        CrawlerTaskModel.status.in_(["pending", "completed", "failed"]),
                        CrawlerTaskModel.next_scheduled_ts <= now_ts,
                        CrawlerTaskModel.next_scheduled_ts > 0,
                    )
                )
                tasks_to_run = result.scalars().all()

                for task in tasks_to_run:
                    print(f"[Scheduler] 调度触发任务: {task.id} ({task.name}) schedule_type={task.schedule_type}")
                    # 更新 next_scheduled_ts 为下次时间,防止重复触发
                    next_ts = _calc_next_scheduled_ts(
                        task.schedule_type, task.schedule_time or "09:00",
                        task.schedule_weekday or 1, now_ts,
                        getattr(task, "schedule_interval_seconds", 900) or 900,
                    )
                    await session.execute(
                        update(CrawlerTaskModel)
                        .where(CrawlerTaskModel.id == task.id)
                        .values(last_scheduled_ts=now_ts, next_scheduled_ts=next_ts)
                    )
                    await session.commit()

                    # 异步触发任务执行,不阻塞调度循环
                    asyncio.create_task(_trigger_scheduled_task(task.id, task.owner_user_id or ""))

                # 为启用调度但 next_scheduled_ts=0 的任务初始化下次时间
                result2 = await session.execute(
                    select(CrawlerTaskModel).where(
                        CrawlerTaskModel.schedule_type.in_(["interval", "daily", "weekly"]),
                        CrawlerTaskModel.next_scheduled_ts == 0,
                    )
                )
                init_tasks = result2.scalars().all()
                for task in init_tasks:
                    next_ts = _calc_next_scheduled_ts(
                        task.schedule_type, task.schedule_time or "09:00",
                        task.schedule_weekday or 1, now_ts,
                        getattr(task, "schedule_interval_seconds", 900) or 900,
                    )
                    await session.execute(
                        update(CrawlerTaskModel)
                        .where(CrawlerTaskModel.id == task.id)
                        .values(next_scheduled_ts=next_ts)
                    )
                if init_tasks:
                    await session.commit()

        except Exception as e:
            print(f"[Scheduler] 调度循环异常: {e}")

        await asyncio.sleep(60)


async def start_scheduler():
    """启动调度器(全局只启动一次)"""
    global _scheduler_started, _scheduler_task
    if _scheduler_started:
        return
    _scheduler_started = True
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    print("[Scheduler] 任务调度器已启动(interval/daily/weekly 支持)")


async def stop_scheduler():
    """停止调度器"""
    global _scheduler_started, _scheduler_task
    if _scheduler_task:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
    _scheduler_started = False
    _scheduler_task = None
    print("[Scheduler] 任务调度器已停止")


def schedule_task_now(
    task_id: str,
    schedule_type: str,
    schedule_time: str = "09:00",
    schedule_weekday: int = 1,
    interval_seconds: int = 900,
) -> int:
    """同步辅助:计算并返回下次调度时间(供 API 调用更新 next_scheduled_ts)"""
    now_ts = int(time.time())
    return _calc_next_scheduled_ts(
        schedule_type,
        schedule_time,
        schedule_weekday,
        now_ts,
        interval_seconds,
    )
