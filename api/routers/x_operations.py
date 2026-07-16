"""X operations center API.

X reads use a dedicated Playwright/CDP browser profile. The official API client
is restricted to OAuth token operations and controlled single-item writes.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.x_operations import (
    XAccountUpdateRequest,
    XApprovalEvidenceRequest,
    XAutomationControlsRequest,
    XConversationAnalysisRequest,
    XInteractionEvaluateRequest,
    XMentionsRefreshRequest,
    XOAuthStartRequest,
    XOptOutRequest,
    XPublishRequest,
    XRegionCreateRequest,
    XRegionUpdateRequest,
    XReplyCandidatesRequest,
    XReviewApprovalRequest,
    XReviewRejectRequest,
    XThreadCollectionRequest,
    XTopicPostCollectionRequest,
    XTopicRefreshRequest,
)
from api.services.auth import get_current_user, require_admin
from api.services.x.account_service import (
    build_oauth_authorization_url,
    decrypt_token,
    encrypt_token,
    exchange_oauth_code,
    refresh_oauth_token,
)
from api.services.x.analysis_service import analyze_thread
from api.services.x.collection_service import XCollectionService
from api.services.x.policy_service import (
    PublicationContext,
    canonical_text,
    classify_interaction_intent,
    content_hash,
    default_controls,
    detect_opt_out,
    evaluate_publication_policy,
    scan_content_risk,
)
from api.services.x.publish_service import XPublisher, build_idempotency_key
from api.services.x.reply_service import ReplyGenerator
from api.services.x.usage_service import configured_budgets, evaluate_budget, utc_usage_date
from config import x_config
from database.db_session import get_session
from database.models import (
    XAccount,
    XApiUsageDaily,
    XAuditLog,
    XConversation,
    XInteraction,
    XPolicyDecision,
    XPost,
    XPublishJob,
    XPublishResult,
    XRateLimitState,
    XRegion,
    XReplyCandidate,
    XReviewTask,
    XSystemControl,
    XThreadAnalysis,
    XTopic,
    XTopicSnapshot,
    XUserOptOut,
)
from media_platform.x.browser_client import XBrowserClient
from media_platform.x.browser_session import open_x_browser
from media_platform.x.client import XWriteApiClient
from media_platform.x.exception import (
    XApiError,
    XAuthenticationError,
    XBrowserChallengeRequired,
    XBrowserError,
    XBrowserLoginRequired,
    XBrowserStructureChanged,
    XConfigurationError,
    XForbiddenError,
    XNotFoundError,
    XRateLimitError,
)
from media_platform.x.field import (
    build_topic_query,
    compute_reply_eligibility,
    included_users,
    map_post,
    normalize_topic_name,
    rebuild_conversation_tree,
)


router = APIRouter(prefix="/x", tags=["X Operations"])

_JSON_TEXT_FIELDS = {
    "granted_scopes",
    "payload_json",
    "result_json",
    "sentiment_json",
    "viewpoints_json",
    "risks_json",
    "output_json",
    "token_usage_json",
}
_SECRET_FIELDS = {"access_token_encrypted", "refresh_token_encrypted"}


async def require_x_operator(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") == "viewer":
        raise HTTPException(status_code=403, detail="viewer 只能查看 X 数据")
    return current_user


def _now_ms() -> int:
    return int(time.time() * 1000)


def _owner(user: Mapping[str, Any]) -> str:
    return str(user["id"])


def _json_text(value: Any, *, fallback: str = "{}") -> str:
    if isinstance(value, str):
        try:
            json.loads(value)
            return value
        except ValueError:
            return json.dumps(value, ensure_ascii=False)
    if value is None:
        return fallback
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _decode_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list, bool, int, float)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _model_kwargs(model: Any, values: Mapping[str, Any]) -> Dict[str, Any]:
    columns = {column.name for column in model.__table__.columns}
    result: Dict[str, Any] = {}
    for key, value in values.items():
        if key not in columns:
            continue
        if (key.endswith("_json") or key in _JSON_TEXT_FIELDS) and not isinstance(value, str):
            fallback = "[]" if key.endswith("s_json") or key in {"granted_scopes", "viewpoints_json", "risks_json"} else "{}"
            result[key] = _json_text(value, fallback=fallback)
        else:
            result[key] = value
    return result


def _apply_values(instance: Any, values: Mapping[str, Any], *, skip: Iterable[str] = ()) -> None:
    skip_set = set(skip)
    for key, value in _model_kwargs(type(instance), values).items():
        if key not in skip_set:
            setattr(instance, key, value)


def _serialize(instance: Any, *, include_secrets: bool = False) -> Dict[str, Any]:
    if instance is None:
        return {}
    result: Dict[str, Any] = {}
    for column in instance.__table__.columns:
        name = column.name
        if not include_secrets and name in _SECRET_FIELDS:
            continue
        value = getattr(instance, name)
        if name.endswith("_json") or name in _JSON_TEXT_FIELDS:
            default = [] if name.endswith("s_json") or name in {"granted_scopes", "viewpoints_json", "risks_json"} else {}
            value = _decode_json(value, default)
        result[name] = value
    if isinstance(instance, XPost):
        result["author_name"] = result.get("author_display_name", "")
    if isinstance(instance, XTopic):
        result["name"] = result.get("raw_name", "")
    return result


def _topic_payload(
    topic: XTopic,
    *,
    snapshot: Optional[XTopicSnapshot] = None,
    region: Optional[XRegion] = None,
) -> Dict[str, Any]:
    payload = _serialize(topic)
    payload.update(
        {
            "region": _serialize(region),
            "latest_snapshot": _serialize(snapshot),
            "region_name": region.name if region else "",
            "woeid": region.woeid if region else "",
            "rank": int(snapshot.rank or 0) if snapshot else 0,
            "rank_change": int(snapshot.rank_delta or 0) if snapshot else 0,
            "volume": int(snapshot.post_volume or 0) if snapshot else 0,
            "captured_at": int(snapshot.captured_at or 0) if snapshot else 0,
        }
    )
    return payload


def _post_url(post_id: str) -> str:
    return f"https://x.com/i/web/status/{post_id}" if post_id else ""


@asynccontextmanager
async def _browser_reader():
    async with open_x_browser() as runtime:
        yield XBrowserClient(runtime.page, cdp_url=runtime.cdp_url)


async def _owned_by_id(
    session: AsyncSession,
    model: Any,
    object_id: int,
    owner_user_id: str,
) -> Any:
    result = await session.execute(
        select(model).where(model.id == object_id, model.owner_user_id == owner_user_id)
    )
    return result.scalars().first()


async def _owned_post(
    session: AsyncSession,
    identifier: str,
    owner_user_id: str,
) -> Optional[XPost]:
    conditions = [XPost.owner_user_id == owner_user_id, XPost.x_post_id == str(identifier)]
    if str(identifier).isdigit():
        conditions.append(and_(XPost.owner_user_id == owner_user_id, XPost.id == int(identifier)))
    result = await session.execute(select(XPost).where(or_(*conditions)))
    return result.scalars().first()


async def _audit(
    session: AsyncSession,
    *,
    owner_user_id: str,
    actor_user_id: str,
    action: str,
    entity_type: str = "",
    entity_id: str = "",
    outcome: str = "success",
    account_id: Optional[int] = None,
    before: Any = None,
    after: Any = None,
    metadata: Any = None,
    request_id: str = "",
    ip_address: str = "",
) -> XAuditLog:
    item = XAuditLog(
        owner_user_id=owner_user_id,
        account_id=account_id,
        actor_user_id=actor_user_id,
        actor_type="user",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        outcome=outcome,
        before_state_json=_json_text(before or {}),
        after_state_json=_json_text(after or {}),
        metadata_json=_json_text(metadata or {}),
        request_id=request_id,
        ip_address=ip_address,
        created_at=_now_ms(),
        updated_at=_now_ms(),
    )
    session.add(item)
    return item


async def _controls(session: AsyncSession, owner_user_id: str) -> Dict[str, Any]:
    values: Dict[str, Any] = default_controls()
    extras: Dict[str, Any] = {}
    now = _now_ms()
    result = await session.execute(
        select(XSystemControl).where(
            XSystemControl.owner_user_id == owner_user_id,
            XSystemControl.scope_type == "global",
            XSystemControl.scope_key == "*",
            or_(XSystemControl.expires_at == 0, XSystemControl.expires_at > now),
        )
    )
    controls = result.scalars().all()
    for item in controls:
        if item.control_name == "policy_config":
            continue
        key = "global_kill_switch" if item.control_name == "kill_switch" else item.control_name
        if key in values:
            values[key] = bool(item.enabled)
        decoded = _decode_json(item.value_json, {})
        if isinstance(decoded, dict):
            extras.update(decoded)
    for item in controls:
        if item.control_name != "policy_config":
            continue
        decoded = _decode_json(item.value_json, {})
        if isinstance(decoded, dict):
            extras.update(decoded)
    values.update(extras)
    return values


def _control_list(controls: Mapping[str, Any], name: str) -> List[str]:
    value = controls.get(name) or []
    if isinstance(value, str):
        value = re.split(r"[\n,]", value)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _matches_control_terms(text: str, terms: Iterable[str]) -> List[str]:
    normalized = canonical_text(text).casefold()
    return [
        term
        for term in terms
        if canonical_text(term).casefold() in normalized
    ]


def _region_pause_matches(region: Optional[XRegion], paused_regions: Iterable[str]) -> List[str]:
    if region is None:
        return []
    identifiers = {
        str(region.id).casefold(),
        str(region.woeid).casefold(),
        canonical_text(region.name).casefold(),
    }
    return [
        term
        for term in paused_regions
        if canonical_text(term).casefold() in identifiers
    ]


async def _upsert_control(
    session: AsyncSession,
    *,
    owner_user_id: str,
    name: str,
    enabled: bool,
    reason: str,
    actor_user_id: str,
    value_json: Optional[Mapping[str, Any]] = None,
) -> XSystemControl:
    result = await session.execute(
        select(XSystemControl).where(
            XSystemControl.owner_user_id == owner_user_id,
            XSystemControl.scope_type == "global",
            XSystemControl.scope_key == "*",
            XSystemControl.control_name == name,
        )
    )
    item = result.scalars().first()
    now = _now_ms()
    if item is None:
        item = XSystemControl(
            owner_user_id=owner_user_id,
            scope_type="global",
            scope_key="*",
            control_name=name,
            value_json="{}",
            created_at=now,
        )
        session.add(item)
    item.enabled = bool(enabled)
    item.reason = reason
    item.changed_by_user_id = actor_user_id
    if value_json is not None:
        item.value_json = _json_text(dict(value_json))
    item.updated_at = now
    return item


async def _record_usage(
    session: AsyncSession,
    *,
    owner_user_id: str,
    endpoint: str,
    account_id: int = 0,
    success: bool = True,
    read_count: int = 0,
    write_count: int = 0,
) -> XApiUsageDaily:
    usage_date = utc_usage_date()
    result = await session.execute(
        select(XApiUsageDaily).where(
            XApiUsageDaily.owner_user_id == owner_user_id,
            XApiUsageDaily.account_id == account_id,
            XApiUsageDaily.usage_date == usage_date,
            XApiUsageDaily.endpoint == endpoint,
        )
    )
    item = result.scalars().first()
    now = _now_ms()
    if item is None:
        item = XApiUsageDaily(
            owner_user_id=owner_user_id,
            account_id=account_id,
            usage_date=usage_date,
            endpoint=endpoint,
            created_at=now,
        )
        session.add(item)
    item.request_count = int(item.request_count or 0) + 1
    item.success_count = int(item.success_count or 0) + int(success)
    item.error_count = int(item.error_count or 0) + int(not success)
    item.read_resource_count = int(item.read_resource_count or 0) + max(read_count, 0)
    item.write_count = int(item.write_count or 0) + max(write_count, 0)
    item.updated_at = now
    return item


def _normalize_endpoint(method: str, endpoint: str) -> str:
    path = endpoint.split("?", 1)[0]
    if path.startswith("http://") or path.startswith("https://"):
        path = "/" + path.split("/", 3)[-1]
    if not path.startswith("/2/") and path != "/2":
        path = f"/2/{path.lstrip('/')}"
    path = re.sub(r"/trends/by/woeid/\d+", "/trends/by/woeid/{woeid}", path)
    path = re.sub(r"/users/\d+/mentions", "/users/{id}/mentions", path)
    path = re.sub(r"/tweets/\d+", "/tweets/{id}", path)
    return f"{method.upper()} {path}"


def _response_observer(
    session: AsyncSession,
    *,
    owner_user_id: str,
    account_id: int = 0,
):
    async def observe(event: Dict[str, Any]) -> None:
        endpoint = _normalize_endpoint(event["method"], str(event["endpoint"]))
        result = await session.execute(
            select(XRateLimitState).where(
                XRateLimitState.owner_user_id == owner_user_id,
                XRateLimitState.account_id == account_id,
                XRateLimitState.endpoint == endpoint,
                XRateLimitState.resource_key == "default",
            )
        )
        item = result.scalars().first()
        now = _now_ms()
        if item is None:
            item = XRateLimitState(
                owner_user_id=owner_user_id,
                account_id=account_id,
                endpoint=endpoint,
                resource_key="default",
                created_at=now,
            )
            session.add(item)
        item.limit_total = int(event.get("rate_limit_limit") or 0)
        item.remaining = int(event.get("rate_limit_remaining") or 0)
        item.reset_at = int(event.get("rate_limit_reset") or 0) * 1000
        item.last_http_status = int(event.get("status_code") or 0)
        item.observed_at = now
        item.updated_at = now

    return observe


async def _crawl_limit_preflight(
    session: AsyncSession,
    *,
    owner_user_id: str,
    requested: int,
) -> Dict[str, Any]:
    result = await session.execute(
        select(func.coalesce(func.sum(XApiUsageDaily.read_resource_count), 0)).where(
            XApiUsageDaily.owner_user_id == owner_user_id,
            XApiUsageDaily.usage_date == utc_usage_date(),
        )
    )
    used = int(result.scalar() or 0)
    status = evaluate_budget(
        used,
        configured_budgets()["post_reads"],
        requested=max(requested, 1),
    )
    if not status.allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "message": "X 每日浏览器采集数量上限已达到",
                "budget": status.to_dict(),
            },
        )
    return status.to_dict()


def _raise_x_error(exc: XApiError) -> None:
    if isinstance(exc, XConfigurationError):
        raise HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, XRateLimitError):
        raise HTTPException(
            status_code=429,
            detail={"message": str(exc), "reset_at": exc.reset_at},
        )
    if isinstance(exc, XNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (XAuthenticationError, XForbiddenError)):
        raise HTTPException(status_code=503, detail=f"X credentials or permissions are invalid: {exc}")
    raise HTTPException(status_code=502 if exc.retryable else 400, detail=str(exc))


def _raise_x_browser_error(exc: XBrowserError) -> None:
    if isinstance(exc, XBrowserLoginRequired):
        raise HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, XBrowserChallengeRequired):
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "action": "请在专用 Chrome/CDP 会话中人工完成验证后重试",
            },
        )
    if isinstance(exc, XBrowserStructureChanged):
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "action": "检查 X 页面结构；必要时启用 browser-use 兜底",
            },
        )
    raise HTTPException(status_code=502 if exc.retryable else 400, detail=str(exc))


async def _account_access_token(
    session: AsyncSession,
    account: XAccount,
    *,
    refresh_if_needed: bool = True,
) -> str:
    token = ""
    if account.access_token_encrypted:
        token = decrypt_token(account.access_token_encrypted)
    elif x_config.X_ACCESS_TOKEN:
        token = x_config.X_ACCESS_TOKEN

    if (
        refresh_if_needed
        and account.token_expires_at
        and account.token_expires_at <= _now_ms() + 30_000
    ):
        refresh = decrypt_token(account.refresh_token_encrypted) if account.refresh_token_encrypted else ""
        if not refresh:
            account.write_enabled = False
            account.last_error = "OAuth token expired and no refresh token is available"
            account.updated_at = _now_ms()
            return ""
        try:
            payload = await refresh_oauth_token(refresh)
            token = str(payload.get("access_token") or "")
            if not token:
                raise RuntimeError("X token refresh returned no access token")
            account.access_token_encrypted = encrypt_token(token)
            if payload.get("refresh_token"):
                account.refresh_token_encrypted = encrypt_token(str(payload["refresh_token"]))
            account.token_expires_at = _now_ms() + int(payload.get("expires_in") or 0) * 1000
            account.granted_scopes = _json_text(str(payload.get("scope") or "").split())
            account.last_error = ""
            account.updated_at = _now_ms()
        except Exception as exc:
            account.write_enabled = False
            account.last_error = f"OAuth token refresh failed: {str(exc)[:300]}"
            account.updated_at = _now_ms()
            return ""
    return token


@router.get("/automation/status")
async def automation_status(current_user: dict = Depends(get_current_user)):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        controls = await _controls(session, owner_user_id)
        accounts_result = await session.execute(
            select(XAccount).where(XAccount.owner_user_id == owner_user_id).order_by(XAccount.id)
        )
        accounts = accounts_result.scalars().all()
        reasons: List[str] = []
        if controls["global_kill_switch"]:
            reasons.append("global Kill Switch is active")
        if not controls["write_enabled"]:
            reasons.append("global write is disabled")
        if not accounts:
            reasons.append("no X account is bound")
        elif not any(
            account.status == "active"
            and account.write_enabled
            and bool(account.access_token_encrypted or x_config.X_ACCESS_TOKEN)
            and "tweet.write" in _decode_json(account.granted_scopes, [])
            for account in accounts
        ):
            reasons.append("no active account has write enabled, a user token, and tweet.write scope")
        return {
            **controls,
            "credentials": {
                "browser_read_source": True,
                "browser_use_fallback": bool(
                    x_config.X_BROWSER_USE_FALLBACK_ENABLED
                    and x_config.X_BROWSER_USE_FALLBACK_COMMAND
                ),
                "x_client_id": bool(x_config.X_CLIENT_ID),
                "token_encryption_key": bool(x_config.TOKEN_ENCRYPTION_KEY),
                "llm": bool(x_config.LLM_BASE_URL and x_config.LLM_API_KEY and x_config.LLM_MODEL),
                "fallback_drafts_available": True,
            },
            "accounts": [
                {
                    **_serialize(account),
                    "token_configured": bool(account.access_token_encrypted or x_config.X_ACCESS_TOKEN),
                    "token_expired": bool(account.token_expires_at and account.token_expires_at <= _now_ms()),
                }
                for account in accounts
            ],
            "effective_write_allowed": not reasons,
            "reasons": reasons,
            "security_defaults": {
                "write_enabled": False,
                "auto_reply_enabled": False,
                "global_kill_switch": True,
                "require_human_review": True,
            },
        }


@router.patch("/automation/controls")
async def update_automation_controls(
    body: XAutomationControlsRequest,
    admin: dict = Depends(require_admin),
):
    owner_user_id = _owner(admin)
    scalar_controls = {
        "read_enabled": body.read_enabled,
        "write_enabled": body.write_enabled,
        "auto_reply_enabled": body.auto_reply_enabled,
        "kill_switch": body.global_kill_switch,
        "require_human_review": body.require_human_review,
    }
    extras = {
        key: value
        for key, value in {
            "daily_write_limit": body.daily_write_limit,
            "hourly_write_limit": body.hourly_write_limit,
            "max_interactions_per_user": body.max_interactions_per_user,
            "min_reply_interval_seconds": body.min_reply_interval_seconds,
            "duplicate_threshold": body.duplicate_threshold,
            "paused_topics": body.paused_topics,
            "paused_regions": body.paused_regions,
            "paused_keywords": body.paused_keywords,
            "high_risk_topics": body.high_risk_topics,
            "allowed_intents": body.allowed_intents,
            "auto_reply_intents": body.auto_reply_intents,
        }.items()
        if value is not None
    }
    if not any(value is not None for value in scalar_controls.values()) and not extras:
        raise HTTPException(status_code=400, detail="没有提供可更新的控制项")

    async with get_session() as session:
        if body.auto_reply_enabled:
            approved = await session.execute(
                select(func.count(XAccount.id)).where(
                    XAccount.owner_user_id == owner_user_id,
                    XAccount.status == "active",
                    XAccount.x_written_approval.is_(True),
                    XAccount.automated_label_enabled.is_(True),
                )
            )
            if int(approved.scalar() or 0) == 0:
                raise HTTPException(
                    status_code=400,
                    detail="开启自动回复前必须绑定已录入 X 书面批准且启用自动账号标签的账号",
                )
        for name, enabled in scalar_controls.items():
            if enabled is not None:
                await _upsert_control(
                    session,
                    owner_user_id=owner_user_id,
                    name=name,
                    enabled=enabled,
                    reason=body.reason,
                    actor_user_id=owner_user_id,
                )
        if extras:
            await _upsert_control(
                session,
                owner_user_id=owner_user_id,
                name="policy_config",
                enabled=True,
                reason=body.reason,
                actor_user_id=owner_user_id,
                value_json=extras,
            )
        await _audit(
            session,
            owner_user_id=owner_user_id,
            actor_user_id=owner_user_id,
            action="automation.controls.updated",
            entity_type="x_system_control",
            after=body.model_dump(exclude_none=True),
        )
    async with get_session() as session:
        return {"success": True, "controls": await _controls(session, owner_user_id)}


@router.post("/accounts/oauth/start")
async def oauth_start(
    body: Optional[XOAuthStartRequest] = None,
    current_user: dict = Depends(require_x_operator),
):
    body = body or XOAuthStartRequest()
    try:
        return build_oauth_authorization_url(
            owner_user_id=_owner(current_user),
            redirect_uri=body.redirect_uri,
            scopes=body.scopes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/accounts/oauth/callback")
async def oauth_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        raise HTTPException(status_code=400, detail=f"X OAuth authorization failed: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="OAuth callback requires code and state")
    try:
        token_payload = await exchange_oauth_code(code=code, state=state)
        access_token = str(token_payload.get("access_token") or "")
        if not access_token:
            raise RuntimeError("X OAuth response did not include an access token")
        try:
            async with _browser_reader() as client:
                identity = await client.get_current_identity()
        except XBrowserError:
            # Token exchange succeeds without a paid read operation. Browser
            # identity can be synchronized later from the account test action.
            identity = {
                "id": f"oauth:{hashlib.sha256(access_token.encode('utf-8')).hexdigest()[:24]}",
                "username": "",
                "name": "",
                "source": "oauth_token_fingerprint",
            }
        owner_user_id = str(token_payload["owner_user_id"])
        async with get_session() as session:
            result = await session.execute(
                select(XAccount).where(
                    XAccount.owner_user_id == owner_user_id,
                    XAccount.x_user_id == str(identity["id"]),
                )
            )
            account = result.scalars().first()
            now = _now_ms()
            if account is None:
                account = XAccount(
                    owner_user_id=owner_user_id,
                    x_user_id=str(identity["id"]),
                    created_at=now,
                )
                session.add(account)
            account.username = str(identity.get("username") or "")
            account.display_name = str(identity.get("name") or "")
            account.access_token_encrypted = encrypt_token(access_token)
            refresh = str(token_payload.get("refresh_token") or "")
            if refresh:
                account.refresh_token_encrypted = encrypt_token(refresh)
            account.token_expires_at = now + int(token_payload.get("expires_in") or 0) * 1000
            account.granted_scopes = _json_text(str(token_payload.get("scope") or "").split())
            account.status = "active"
            account.write_enabled = False
            account.auto_reply_enabled = False
            account.last_error = ""
            account.updated_at = now
            await session.flush()
            await _audit(
                session,
                owner_user_id=owner_user_id,
                actor_user_id=owner_user_id,
                action="account.oauth.bound",
                entity_type="x_account",
                entity_id=str(account.id),
                account_id=account.id,
                after={"x_user_id": account.x_user_id, "username": account.username, "scopes": _decode_json(account.granted_scopes, [])},
            )
            return {"success": True, "account": _serialize(account)}
    except XApiError as exc:
        _raise_x_error(exc)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/accounts")
async def list_accounts(current_user: dict = Depends(get_current_user)):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        result = await session.execute(
            select(XAccount).where(XAccount.owner_user_id == owner_user_id).order_by(XAccount.id)
        )
        items = []
        for account in result.scalars().all():
            item = _serialize(account)
            item["token_configured"] = bool(account.access_token_encrypted or x_config.X_ACCESS_TOKEN)
            item["token_expired"] = bool(account.token_expires_at and account.token_expires_at <= _now_ms())
            items.append(item)
        return {"items": items, "total": len(items)}


@router.patch("/accounts/{account_id}")
async def update_account(
    account_id: int,
    body: XAccountUpdateRequest,
    admin: dict = Depends(require_admin),
):
    owner_user_id = _owner(admin)
    async with get_session() as session:
        account = await _owned_by_id(session, XAccount, account_id, owner_user_id)
        if account is None:
            raise HTTPException(status_code=404, detail="X 账号不存在")
        before = _serialize(account)
        updates = body.model_dump(exclude_none=True)
        if updates.get("auto_reply_enabled") and (
            not account.x_written_approval or not (updates.get("automated_label_enabled", account.automated_label_enabled))
        ):
            raise HTTPException(status_code=400, detail="自动回复需要 X 书面批准和自动账号标签")
        _apply_values(account, updates)
        account.updated_at = _now_ms()
        await _audit(
            session,
            owner_user_id=owner_user_id,
            actor_user_id=owner_user_id,
            action="account.updated",
            entity_type="x_account",
            entity_id=str(account.id),
            account_id=account.id,
            before=before,
            after=_serialize(account),
        )
        return {"success": True, "account": _serialize(account)}


@router.post("/accounts/{account_id}/approval-evidence")
async def save_approval_evidence(
    account_id: int,
    body: XApprovalEvidenceRequest,
    admin: dict = Depends(require_admin),
):
    owner_user_id = _owner(admin)
    async with get_session() as session:
        account = await _owned_by_id(session, XAccount, account_id, owner_user_id)
        if account is None:
            raise HTTPException(status_code=404, detail="X 账号不存在")
        account.x_written_approval = body.x_written_approval
        account.approval_reference = body.approval_reference
        if not body.x_written_approval:
            account.auto_reply_enabled = False
        account.updated_at = _now_ms()
        await _audit(
            session,
            owner_user_id=owner_user_id,
            actor_user_id=owner_user_id,
            action="account.approval_evidence.updated",
            entity_type="x_account",
            entity_id=str(account.id),
            account_id=account.id,
            after={
                "x_written_approval": account.x_written_approval,
                "approval_reference": account.approval_reference,
            },
        )
        return {"success": True, "account": _serialize(account)}


@router.post("/accounts/{account_id}/test")
async def test_account(account_id: int, current_user: dict = Depends(require_x_operator)):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        account = await _owned_by_id(session, XAccount, account_id, owner_user_id)
        if account is None:
            raise HTTPException(status_code=404, detail="X 账号不存在")
        try:
            token = await _account_access_token(session, account)
            if not token:
                raise XConfigurationError("X user access token is missing or expired")
            async with _browser_reader() as client:
                identity = await client.get_current_identity()
            account.x_user_id = str(identity["id"])
            account.username = str(identity.get("username") or "")
            account.display_name = str(identity.get("name") or "")
            account.last_sync_at = _now_ms()
            account.last_error = ""
            account.status = "active"
            account.updated_at = _now_ms()
            await _record_usage(
                session,
                owner_user_id=owner_user_id,
                account_id=account.id,
                endpoint="BROWSER /home identity",
                read_count=1,
            )
            return {"success": True, "identity": identity, "account": _serialize(account)}
        except XBrowserError as exc:
            account.last_error = str(exc)[:500]
            account.updated_at = _now_ms()
            await session.commit()
            _raise_x_browser_error(exc)
        except (ValueError, XApiError) as exc:
            account.last_error = str(exc)[:500]
            account.write_enabled = False
            account.updated_at = _now_ms()
            await session.commit()
            raise HTTPException(status_code=503, detail=str(exc))


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: int, admin: dict = Depends(require_admin)):
    owner_user_id = _owner(admin)
    async with get_session() as session:
        account = await _owned_by_id(session, XAccount, account_id, owner_user_id)
        if account is None:
            raise HTTPException(status_code=404, detail="X 账号不存在")
        before = _serialize(account)
        jobs = await session.execute(
            select(XPublishJob).where(
                XPublishJob.owner_user_id == owner_user_id,
                XPublishJob.account_id == account_id,
                XPublishJob.status.in_(["pending", "running", "retry_wait"]),
            )
        )
        for job in jobs.scalars().all():
            job.status = "cancelled"
            job.error_message = "X account binding removed"
            job.updated_at = _now_ms()
        account.access_token_encrypted = ""
        account.refresh_token_encrypted = ""
        account.write_enabled = False
        account.auto_reply_enabled = False
        account.status = "revoked"
        account.updated_at = _now_ms()
        await _audit(
            session,
            owner_user_id=owner_user_id,
            actor_user_id=owner_user_id,
            action="account.revoked",
            entity_type="x_account",
            entity_id=str(account.id),
            account_id=account.id,
            before=before,
            after=_serialize(account),
        )
        return {"success": True}


@router.get("/regions")
async def list_regions(current_user: dict = Depends(get_current_user)):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        result = await session.execute(
            select(XRegion).where(XRegion.owner_user_id == owner_user_id).order_by(XRegion.name)
        )
        items = [_serialize(item) for item in result.scalars().all()]
        return {"items": items, "total": len(items)}


@router.post("/regions")
async def create_region(
    body: XRegionCreateRequest,
    current_user: dict = Depends(require_x_operator),
):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        existing = await session.execute(
            select(XRegion).where(
                XRegion.owner_user_id == owner_user_id,
                XRegion.woeid == body.woeid,
            )
        )
        if existing.scalars().first():
            raise HTTPException(status_code=409, detail="该 WOEID 已配置")
        now = _now_ms()
        region = XRegion(
            owner_user_id=owner_user_id,
            **body.model_dump(),
            next_poll_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(region)
        await session.flush()
        await _audit(
            session,
            owner_user_id=owner_user_id,
            actor_user_id=owner_user_id,
            action="region.created",
            entity_type="x_region",
            entity_id=str(region.id),
            after=_serialize(region),
        )
        return {"success": True, "region": _serialize(region)}


@router.patch("/regions/{region_id}")
async def update_region(
    region_id: int,
    body: XRegionUpdateRequest,
    current_user: dict = Depends(require_x_operator),
):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        region = await _owned_by_id(session, XRegion, region_id, owner_user_id)
        if region is None:
            raise HTTPException(status_code=404, detail="地域不存在")
        before = _serialize(region)
        _apply_values(region, body.model_dump(exclude_none=True))
        region.updated_at = _now_ms()
        await _audit(
            session,
            owner_user_id=owner_user_id,
            actor_user_id=owner_user_id,
            action="region.updated",
            entity_type="x_region",
            entity_id=str(region.id),
            before=before,
            after=_serialize(region),
        )
        return {"success": True, "region": _serialize(region)}


async def _ensure_default_region(session: AsyncSession, owner_user_id: str) -> XRegion:
    result = await session.execute(
        select(XRegion).where(XRegion.owner_user_id == owner_user_id).order_by(XRegion.id).limit(1)
    )
    region = result.scalars().first()
    if region is not None:
        return region
    default = x_config.X_DEFAULT_REGIONS[0]
    now = _now_ms()
    region = XRegion(
        owner_user_id=owner_user_id,
        woeid=str(default["woeid"]),
        name=str(default.get("region_name") or "Worldwide"),
        language=str(default.get("language") or ""),
        poll_interval_seconds=int(default.get("poll_interval") or 900),
        enabled=bool(default.get("enabled", True)),
        next_poll_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(region)
    await session.flush()
    return region


@router.post("/topics/refresh")
async def refresh_topics(
    body: XTopicRefreshRequest,
    request: Request,
    current_user: dict = Depends(require_x_operator),
):
    owner_user_id = _owner(current_user)

    async with get_session() as session:
        controls = await _controls(session, owner_user_id)
        if not controls["read_enabled"]:
            raise HTTPException(status_code=400, detail="X 只读采集开关已关闭")

        if body.region_ids:
            regions_result = await session.execute(
                select(XRegion).where(
                    XRegion.owner_user_id == owner_user_id,
                    XRegion.id.in_(body.region_ids),
                    XRegion.enabled.is_(True),
                )
            )
            regions = regions_result.scalars().all()
            if len(regions) != len(set(body.region_ids)):
                raise HTTPException(status_code=404, detail="部分地域不存在或已停用")
        else:
            regions_result = await session.execute(
                select(XRegion).where(
                    XRegion.owner_user_id == owner_user_id,
                    XRegion.enabled.is_(True),
                )
            )
            regions = regions_result.scalars().all()
            if not regions:
                regions = [await _ensure_default_region(session, owner_user_id)]
        paused_regions = _control_list(controls, "paused_regions")
        regions = [
            region
            for region in regions
            if not _region_pause_matches(region, paused_regions)
        ]
        if not regions:
            await _audit(
                session,
                owner_user_id=owner_user_id,
                actor_user_id=owner_user_id,
                action="topics.refresh_skipped",
                entity_type="x_region",
                outcome="blocked",
                metadata={"reason": "all requested regions are paused"},
            )
            return {
                "success": True,
                "batch_id": "",
                "captured_at": _now_ms(),
                "items": [],
                "total": 0,
                "message": "所有请求地域均处于暂停状态",
            }
        await _crawl_limit_preflight(
            session,
            owner_user_id=owner_user_id,
            requested=len(regions) * body.max_trends,
        )

        batch_id = uuid.uuid4().hex
        captured_at = _now_ms()
        collected: List[Dict[str, Any]] = []
        async with _browser_reader() as client:
            collector = XCollectionService(client)
            for region in regions:
                try:
                    result = await collector.collect_trends(
                        woeid=int(region.woeid),
                        region_id=region.id,
                        region_name=region.name,
                        max_trends=body.max_trends,
                    )
                    await _record_usage(
                        session,
                        owner_user_id=owner_user_id,
                        endpoint="BROWSER /explore/tabs/trending",
                        read_count=len(result["topics"]),
                    )
                    for raw in result["topics"]:
                        topic_result = await session.execute(
                            select(XTopic).where(
                                XTopic.owner_user_id == owner_user_id,
                                XTopic.region_id == region.id,
                                XTopic.normalized_name == raw["normalized_name"],
                            )
                        )
                        topic = topic_result.scalars().first()
                        custom_high_risk = _matches_control_terms(
                            raw["name"],
                            _control_list(controls, "high_risk_topics"),
                        )
                        risk = scan_content_risk(raw["name"])
                        is_sensitive = bool(risk["sensitive_topic"] or custom_high_risk)
                        if topic is None:
                            try:
                                search_query = build_topic_query(raw["name"], lang=region.language or None)
                            except ValueError:
                                search_query = ""
                            topic = XTopic(
                                owner_user_id=owner_user_id,
                                region_id=region.id,
                                raw_name=raw["name"],
                                normalized_name=raw["normalized_name"],
                                search_query=search_query,
                                language=region.language,
                                risk_score=1.0 if is_sensitive else 0.0,
                                is_sensitive=is_sensitive,
                                first_seen_at=captured_at,
                                created_at=captured_at,
                            )
                            session.add(topic)
                            await session.flush()
                        topic.raw_name = raw["name"]
                        topic.risk_score = 1.0 if is_sensitive else 0.0
                        topic.is_sensitive = is_sensitive
                        topic.last_seen_at = captured_at
                        topic.updated_at = captured_at

                        previous_result = await session.execute(
                            select(XTopicSnapshot)
                            .where(
                                XTopicSnapshot.owner_user_id == owner_user_id,
                                XTopicSnapshot.topic_id == topic.id,
                            )
                            .order_by(XTopicSnapshot.captured_at.desc())
                            .limit(1)
                        )
                        previous = previous_result.scalars().first()
                        rank = int(raw["rank"])
                        volume = int(raw["tweet_count"])
                        snapshot = XTopicSnapshot(
                            owner_user_id=owner_user_id,
                            topic_id=topic.id,
                            region_id=region.id,
                            capture_batch_id=batch_id,
                            rank=rank,
                            rank_delta=(int(previous.rank or 0) - rank) if previous else 0,
                            post_volume=volume,
                            volume_delta=volume - int(previous.post_volume or 0) if previous else 0,
                            raw_payload_json=_json_text(raw["raw_payload_json"]),
                            captured_at=captured_at,
                            created_at=captured_at,
                            updated_at=captured_at,
                        )
                        session.add(snapshot)
                        await session.flush()
                        collected.append(_topic_payload(topic, snapshot=snapshot, region=region))
                    region.last_polled_at = captured_at
                    region.next_poll_at = captured_at + int(region.poll_interval_seconds or 900) * 1000
                    region.last_error = ""
                    region.updated_at = captured_at
                except XBrowserError as exc:
                    region.last_error = str(exc)[:500]
                    region.updated_at = captured_at
                    await _record_usage(
                        session,
                        owner_user_id=owner_user_id,
                        endpoint="BROWSER /explore/tabs/trending",
                        success=False,
                    )
                    await session.commit()
                    _raise_x_browser_error(exc)

        await _audit(
            session,
            owner_user_id=owner_user_id,
            actor_user_id=owner_user_id,
            action="topics.refreshed",
            entity_type="x_topic_snapshot_batch",
            entity_id=batch_id,
            after={"regions": len(regions), "topics": len(collected)},
            request_id=request.headers.get("x-request-id", ""),
            ip_address=request.client.host if request.client else "",
        )
        return {
            "success": True,
            "batch_id": batch_id,
            "captured_at": captured_at,
            "items": collected,
            "total": len(collected),
        }


@router.get("/topics")
async def list_topics(
    region_id: Optional[int] = None,
    status: Optional[str] = None,
    sensitive_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        conditions = [XTopic.owner_user_id == owner_user_id]
        if region_id is not None:
            conditions.append(XTopic.region_id == region_id)
        if status:
            conditions.append(XTopic.status == status)
        if sensitive_only:
            conditions.append(XTopic.is_sensitive.is_(True))
        total_result = await session.execute(
            select(func.count(XTopic.id)).where(*conditions)
        )
        result = await session.execute(
            select(XTopic)
            .where(*conditions)
            .order_by(XTopic.last_seen_at.desc(), XTopic.id.desc())
            .limit(limit)
            .offset(offset)
        )
        items: List[Dict[str, Any]] = []
        for topic in result.scalars().all():
            snapshot_result = await session.execute(
                select(XTopicSnapshot)
                .where(
                    XTopicSnapshot.owner_user_id == owner_user_id,
                    XTopicSnapshot.topic_id == topic.id,
                )
                .order_by(XTopicSnapshot.captured_at.desc())
                .limit(1)
            )
            region = await _owned_by_id(session, XRegion, topic.region_id, owner_user_id)
            items.append(
                _topic_payload(
                    topic,
                    snapshot=snapshot_result.scalars().first(),
                    region=region,
                )
            )
        return {"items": items, "total": int(total_result.scalar() or 0), "limit": limit, "offset": offset}


@router.get("/topics/{topic_id}")
async def get_topic(topic_id: int, current_user: dict = Depends(get_current_user)):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        topic = await _owned_by_id(session, XTopic, topic_id, owner_user_id)
        if topic is None:
            raise HTTPException(status_code=404, detail="热点不存在")
        snapshots_result = await session.execute(
            select(XTopicSnapshot)
            .where(
                XTopicSnapshot.owner_user_id == owner_user_id,
                XTopicSnapshot.topic_id == topic.id,
            )
            .order_by(XTopicSnapshot.captured_at.desc())
            .limit(100)
        )
        post_count_result = await session.execute(
            select(func.count(XPost.id)).where(
                XPost.owner_user_id == owner_user_id,
                XPost.source_topic_id == topic.id,
            )
        )
        snapshots = snapshots_result.scalars().all()
        region = await _owned_by_id(session, XRegion, topic.region_id, owner_user_id)
        return {
            "topic": _topic_payload(
                topic,
                snapshot=snapshots[0] if snapshots else None,
                region=region,
            ),
            "snapshots": [_serialize(item) for item in snapshots],
            "post_count": int(post_count_result.scalar() or 0),
        }


async def _upsert_post(
    session: AsyncSession,
    *,
    owner_user_id: str,
    values: Mapping[str, Any],
) -> XPost:
    x_post_id = str(values.get("x_post_id") or "")
    result = await session.execute(
        select(XPost).where(
            XPost.owner_user_id == owner_user_id,
            XPost.x_post_id == x_post_id,
        )
    )
    post = result.scalars().first()
    now = _now_ms()
    if post is None:
        kwargs = _model_kwargs(XPost, {**values, "owner_user_id": owner_user_id})
        post = XPost(**kwargs)
        if not post.created_at:
            post.created_at = now
        session.add(post)
    else:
        _apply_values(post, values, skip={"id", "owner_user_id", "created_at"})
    post.updated_at = now
    return post


@router.post("/topics/{topic_id}/collect-posts")
async def collect_topic_posts(
    topic_id: int,
    body: XTopicPostCollectionRequest,
    current_user: dict = Depends(require_x_operator),
):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        controls = await _controls(session, owner_user_id)
        if not controls["read_enabled"]:
            raise HTTPException(status_code=400, detail="X 只读采集开关已关闭")
        topic = await _owned_by_id(session, XTopic, topic_id, owner_user_id)
        if topic is None:
            raise HTTPException(status_code=404, detail="热点不存在")
        if topic.is_sensitive:
            generation_note = "该主题为高风险监控主题，只采集、不生成发布候选"
        else:
            generation_note = ""
        region = await _owned_by_id(session, XRegion, topic.region_id, owner_user_id)
        paused_region_matches = _region_pause_matches(
            region,
            _control_list(controls, "paused_regions"),
        )
        paused_keyword_matches = _matches_control_terms(
            f"{topic.raw_name} {topic.search_query}",
            _control_list(controls, "paused_keywords"),
        )
        if paused_region_matches or paused_keyword_matches:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "该热点命中暂停采集策略",
                    "paused_regions": paused_region_matches,
                    "paused_keywords": paused_keyword_matches,
                },
            )
        await _crawl_limit_preflight(
            session,
            owner_user_id=owner_user_id,
            requested=body.max_posts,
        )
        try:
            async with _browser_reader() as client:
                collector = XCollectionService(client)
                result = await collector.collect_topic_posts(
                    topic=topic.raw_name,
                    topic_id=topic.id,
                    lang=body.language or topic.language or (region.language if region else None),
                    max_posts=body.max_posts,
                )
            stored = []
            for values in result["posts"]:
                stored.append(await _upsert_post(session, owner_user_id=owner_user_id, values=values))
            topic.search_query = result["query"]
            topic.updated_at = _now_ms()
            await session.flush()
            await _record_usage(
                session,
                owner_user_id=owner_user_id,
                endpoint="BROWSER /search?f=live",
                read_count=len(stored),
            )
            await _audit(
                session,
                owner_user_id=owner_user_id,
                actor_user_id=owner_user_id,
                action="topic.posts.collected",
                entity_type="x_topic",
                entity_id=str(topic.id),
                after={"post_count": len(stored), "query": result["query"]},
            )
            return {
                "success": True,
                "query": result["query"],
                "items": [{**_serialize(post), "post_url": _post_url(post.x_post_id)} for post in stored],
                "total": len(stored),
                "note": generation_note,
            }
        except XBrowserError as exc:
            await _record_usage(
                session,
                owner_user_id=owner_user_id,
                endpoint="BROWSER /search?f=live",
                success=False,
            )
            await session.commit()
            _raise_x_browser_error(exc)


@router.get("/posts")
async def list_posts(
    topic_id: Optional[int] = None,
    conversation_id: Optional[str] = None,
    lang: Optional[str] = None,
    risk_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        conditions = [XPost.owner_user_id == owner_user_id]
        if topic_id is not None:
            conditions.append(XPost.source_topic_id == topic_id)
        if conversation_id:
            conditions.append(XPost.conversation_id == conversation_id)
        if lang:
            conditions.append(XPost.lang == lang)
        if risk_only:
            conditions.append(XPost.possibly_sensitive.is_(True))
        total_result = await session.execute(select(func.count(XPost.id)).where(*conditions))
        result = await session.execute(
            select(XPost)
            .where(*conditions)
            .order_by(XPost.created_at_x.desc(), XPost.id.desc())
            .limit(limit)
            .offset(offset)
        )
        items = [
            {**_serialize(post), "post_url": _post_url(post.x_post_id)}
            for post in result.scalars().all()
        ]
        return {"items": items, "total": int(total_result.scalar() or 0), "limit": limit, "offset": offset}


@router.get("/posts/{post_id}")
async def get_post(post_id: str, current_user: dict = Depends(get_current_user)):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        post = await _owned_post(session, post_id, owner_user_id)
        if post is None:
            raise HTTPException(status_code=404, detail="帖子不存在")
        conversation_result = await session.execute(
            select(XConversation).where(
                XConversation.owner_user_id == owner_user_id,
                or_(
                    XConversation.root_post_id == post.x_post_id,
                    XConversation.x_conversation_id == post.conversation_id,
                ),
            )
        )
        return {
            "post": {**_serialize(post), "post_url": _post_url(post.x_post_id)},
            "conversation": _serialize(conversation_result.scalars().first()),
        }


def _tree_depth(nodes: Iterable[Mapping[str, Any]], depth: int = 1) -> int:
    maximum = 0
    for node in nodes:
        children = node.get("children") or []
        maximum = max(maximum, depth, _tree_depth(children, depth + 1) if children else depth)
    return maximum


@router.post("/posts/{post_id}/collect-thread")
async def collect_thread(
    post_id: str,
    body: XThreadCollectionRequest,
    current_user: dict = Depends(require_x_operator),
):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        controls = await _controls(session, owner_user_id)
        if not controls["read_enabled"]:
            raise HTTPException(status_code=400, detail="X 只读采集开关已关闭")
        local_post = await _owned_post(session, post_id, owner_user_id)
        root_post_id = local_post.x_post_id if local_post else str(post_id)
        if not root_post_id.isdigit():
            raise HTTPException(status_code=400, detail="需要有效的 X Post ID")
        await _crawl_limit_preflight(
            session,
            owner_user_id=owner_user_id,
            requested=body.max_posts + 1,
        )
        try:
            async with _browser_reader() as client:
                result = await XCollectionService(client).collect_thread(
                    root_post_id=root_post_id,
                    max_posts=body.max_posts,
                )
            stored: List[XPost] = []
            for values in result["posts"]:
                stored.append(await _upsert_post(session, owner_user_id=owner_user_id, values=values))
            await session.flush()
            root = next((item for item in stored if item.x_post_id == root_post_id), stored[0] if stored else None)
            x_conversation_id = root.conversation_id if root else root_post_id
            conv_result = await session.execute(
                select(XConversation).where(
                    XConversation.owner_user_id == owner_user_id,
                    XConversation.root_post_id == root_post_id,
                )
            )
            conversation = conv_result.scalars().first()
            now = _now_ms()
            if conversation is None:
                conversation = XConversation(
                    owner_user_id=owner_user_id,
                    root_post_id=root_post_id,
                    created_at=now,
                )
                session.add(conversation)
            post_payloads = [_serialize(item) for item in stored]
            tree = rebuild_conversation_tree(post_payloads)
            conversation.x_conversation_id = x_conversation_id
            conversation.language = root.lang if root else ""
            conversation.status = "ready"
            conversation.sample_limit = body.max_posts
            conversation.total_post_count = len(stored)
            conversation.sampled_post_count = len(stored)
            conversation.max_depth = _tree_depth(tree)
            conversation.newest_post_at = max((item.created_at_x or 0 for item in stored), default=0)
            conversation.pagination_token = str((result.get("meta") or {}).get("next_token") or "")
            conversation.last_collected_at = now
            conversation.next_refresh_at = now + int(x_config.X_MENTIONS_INTERVAL_SECONDS) * 1000
            conversation.last_error = ""
            conversation.updated_at = now
            await session.flush()
            await _record_usage(
                session,
                owner_user_id=owner_user_id,
                endpoint="BROWSER /i/web/status/{id}",
                read_count=len(stored),
            )
            await _audit(
                session,
                owner_user_id=owner_user_id,
                actor_user_id=owner_user_id,
                action="conversation.collected",
                entity_type="x_conversation",
                entity_id=str(conversation.id),
                after={"root_post_id": root_post_id, "post_count": len(stored)},
            )
            return {
                "success": True,
                "conversation": _serialize(conversation),
                "posts": [
                    {**_serialize(item), "post_url": _post_url(item.x_post_id)}
                    for item in stored
                ],
                "tree": tree,
            }
        except XBrowserError as exc:
            if local_post:
                conv_result = await session.execute(
                    select(XConversation).where(
                        XConversation.owner_user_id == owner_user_id,
                        XConversation.root_post_id == root_post_id,
                    )
                )
                conversation = conv_result.scalars().first()
                if conversation:
                    conversation.status = "failed"
                    conversation.last_error = str(exc)[:500]
                    conversation.updated_at = _now_ms()
            await _record_usage(
                session,
                owner_user_id=owner_user_id,
                endpoint=getattr(exc, "usage_endpoint", "BROWSER /i/web/status/{id}"),
                success=False,
            )
            await session.commit()
            _raise_x_browser_error(exc)


@router.get("/conversations/{root_post_id}")
async def get_conversation(root_post_id: str, current_user: dict = Depends(get_current_user)):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        result = await session.execute(
            select(XConversation).where(
                XConversation.owner_user_id == owner_user_id,
                XConversation.root_post_id == root_post_id,
            )
        )
        conversation = result.scalars().first()
        if conversation is None:
            raise HTTPException(status_code=404, detail="线程尚未采集")
        posts_result = await session.execute(
            select(XPost)
            .where(
                XPost.owner_user_id == owner_user_id,
                or_(
                    XPost.conversation_id == conversation.x_conversation_id,
                    XPost.x_post_id == conversation.root_post_id,
                ),
            )
            .order_by(XPost.created_at_x, XPost.id)
        )
        posts = posts_result.scalars().all()
        analysis_result = await session.execute(
            select(XThreadAnalysis)
            .where(
                XThreadAnalysis.owner_user_id == owner_user_id,
                XThreadAnalysis.conversation_id == conversation.id,
            )
            .order_by(XThreadAnalysis.analysed_at.desc(), XThreadAnalysis.id.desc())
            .limit(1)
        )
        payloads = [_serialize(item) for item in posts]
        return {
            "conversation": _serialize(conversation),
            "posts": [
                {**payload, "post_url": _post_url(payload["x_post_id"])}
                for payload in payloads
            ],
            "tree": rebuild_conversation_tree(payloads),
            "analysis": _serialize(analysis_result.scalars().first()),
        }


@router.post("/conversations/{root_post_id}/analyze")
async def analyze_conversation(
    root_post_id: str,
    body: XConversationAnalysisRequest,
    current_user: dict = Depends(require_x_operator),
):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        conv_result = await session.execute(
            select(XConversation).where(
                XConversation.owner_user_id == owner_user_id,
                XConversation.root_post_id == root_post_id,
            )
        )
        conversation = conv_result.scalars().first()
        if conversation is None:
            raise HTTPException(status_code=404, detail="请先采集评论线程")
        posts_result = await session.execute(
            select(XPost)
            .where(
                XPost.owner_user_id == owner_user_id,
                or_(
                    XPost.conversation_id == conversation.x_conversation_id,
                    XPost.x_post_id == conversation.root_post_id,
                ),
            )
            .order_by(XPost.created_at_x, XPost.id)
        )
        posts = posts_result.scalars().all()
        if not posts:
            raise HTTPException(status_code=400, detail="线程中没有可分析帖子")
        post_payloads = [_serialize(item) for item in posts]
        analysis_payload = analyze_thread(
            post_payloads,
            topic=body.topic,
            max_samples=body.max_samples,
        )
        existing_result = await session.execute(
            select(XThreadAnalysis).where(
                XThreadAnalysis.owner_user_id == owner_user_id,
                XThreadAnalysis.conversation_id == conversation.id,
                XThreadAnalysis.input_content_hash == analysis_payload["input_content_hash"],
                XThreadAnalysis.model_version == analysis_payload["model_version"],
                XThreadAnalysis.prompt_version == analysis_payload["prompt_version"],
            )
        )
        analysis = existing_result.scalars().first()
        if analysis is None:
            root = next((item for item in posts if item.x_post_id == root_post_id), posts[0])
            now = _now_ms()
            analysis = XThreadAnalysis(
                owner_user_id=owner_user_id,
                conversation_id=conversation.id,
                source_post_id=root.id,
                status="succeeded",
                input_content_hash=analysis_payload["input_content_hash"],
                model_version=analysis_payload["model_version"],
                prompt_version=analysis_payload["prompt_version"],
                schema_version=analysis_payload["schema_version"],
                summary=analysis_payload["summary"],
                sentiment_json=_json_text(
                    {
                        "dominant_sentiment": analysis_payload["dominant_sentiment"],
                        "distribution": analysis_payload["sentiment_distribution"],
                    }
                ),
                viewpoints_json=_json_text(analysis_payload["main_viewpoints"], fallback="[]"),
                risks_json=_json_text(analysis_payload["misinformation_risks"], fallback="[]"),
                reply_recommendation=analysis_payload["reply_recommendation"],
                output_json=_json_text(analysis_payload),
                token_usage_json="{}",
                analysed_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(analysis)
            conversation.status = "analysed"
            conversation.updated_at = now
            await session.flush()
            await _audit(
                session,
                owner_user_id=owner_user_id,
                actor_user_id=owner_user_id,
                action="conversation.analysed",
                entity_type="x_thread_analysis",
                entity_id=str(analysis.id),
                after={"conversation_id": conversation.id, "input_content_hash": analysis.input_content_hash},
            )
        return {
            "success": True,
            "analysis": _serialize(analysis),
            "structured_output": _decode_json(analysis.output_json, {}),
            "fallback_used": analysis.model_version.startswith("deterministic-"),
        }


async def _select_account(
    session: AsyncSession,
    *,
    owner_user_id: str,
    account_id: Optional[int],
) -> XAccount:
    statement = select(XAccount).where(
        XAccount.owner_user_id == owner_user_id,
        XAccount.status == "active",
    )
    if account_id is not None:
        statement = statement.where(XAccount.id == account_id)
    statement = statement.order_by(XAccount.id).limit(1)
    result = await session.execute(statement)
    account = result.scalars().first()
    if account is None:
        detail = "指定 X 账号不存在或不可用" if account_id else "请先绑定一个有效的 X 账号"
        raise HTTPException(status_code=400, detail=detail)
    return account


async def _latest_analysis_for_post(
    session: AsyncSession,
    *,
    owner_user_id: str,
    post: XPost,
) -> Optional[XThreadAnalysis]:
    conv_result = await session.execute(
        select(XConversation).where(
            XConversation.owner_user_id == owner_user_id,
            or_(
                XConversation.x_conversation_id == post.conversation_id,
                XConversation.root_post_id == post.x_post_id,
            ),
        )
    )
    conversation = conv_result.scalars().first()
    if conversation is None:
        return None
    result = await session.execute(
        select(XThreadAnalysis)
        .where(
            XThreadAnalysis.owner_user_id == owner_user_id,
            XThreadAnalysis.conversation_id == conversation.id,
            XThreadAnalysis.status == "succeeded",
        )
        .order_by(XThreadAnalysis.analysed_at.desc(), XThreadAnalysis.id.desc())
        .limit(1)
    )
    return result.scalars().first()


async def _generate_candidates_for_post(
    session: AsyncSession,
    *,
    owner_user_id: str,
    actor_user_id: str,
    post: XPost,
    body: XReplyCandidatesRequest,
) -> Dict[str, Any]:
    account = await _select_account(
        session,
        owner_user_id=owner_user_id,
        account_id=body.account_id,
    )
    controls = await _controls(session, owner_user_id)
    topic = None
    region = None
    if post.source_topic_id:
        topic = await _owned_by_id(session, XTopic, post.source_topic_id, owner_user_id)
        if topic and topic.is_sensitive:
            raise HTTPException(status_code=400, detail="高风险热点仅允许监控，不能生成待发布回复")
        if topic:
            region = await _owned_by_id(session, XRegion, topic.region_id, owner_user_id)
    paused_region_matches = _region_pause_matches(
        region,
        _control_list(controls, "paused_regions"),
    )
    target_context = f"{topic.raw_name if topic else ''} {post.text}"
    paused_keyword_matches = _matches_control_terms(
        target_context,
        _control_list(controls, "paused_keywords"),
    )
    high_risk_matches = _matches_control_terms(
        target_context,
        _control_list(controls, "high_risk_topics"),
    )
    if paused_region_matches or paused_keyword_matches or high_risk_matches:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "目标命中暂停或高风险运营策略，不能生成待发布候选",
                "paused_regions": paused_region_matches,
                "paused_keywords": paused_keyword_matches,
                "high_risk_topics": high_risk_matches,
            },
        )

    analysis = await _latest_analysis_for_post(
        session,
        owner_user_id=owner_user_id,
        post=post,
    )
    history_result = await session.execute(
        select(XReplyCandidate.generated_text, XReplyCandidate.edited_text)
        .where(
            XReplyCandidate.owner_user_id == owner_user_id,
            XReplyCandidate.account_id == account.id,
            XReplyCandidate.review_status == "published",
        )
        .order_by(XReplyCandidate.created_at.desc())
        .limit(1000)
    )
    historical: List[str] = []
    for generated, edited in history_result.all():
        historical.append(str(edited or generated or ""))
    interaction_result = await session.execute(
        select(XInteraction).where(
            XInteraction.owner_user_id == owner_user_id,
            XInteraction.account_id == account.id,
            XInteraction.interaction_post_id == post.x_post_id,
        )
    )
    interaction = interaction_result.scalars().first()
    analysis_payload = _decode_json(analysis.output_json, {}) if analysis else {}
    voice = body.brand_voice
    if body.tone:
        voice = f"{voice}; requested tone: {body.tone}"
    generated = await ReplyGenerator().generate(
        target_post=_serialize(post),
        thread_analysis=analysis_payload,
        brand_voice=voice,
        mode=body.mode,
        historical_replies=historical,
    )
    if generated["blocked"] or not generated["candidates"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": generated["reason"],
                "input_risk": generated["input_risk"],
            },
        )

    now = _now_ms()
    persisted: List[Dict[str, Any]] = []
    for index, draft in enumerate(generated["candidates"][: body.candidate_count]):
        candidate = XReplyCandidate(
            owner_user_id=owner_user_id,
            account_id=account.id,
            thread_analysis_id=analysis.id if analysis else None,
            source_post_id=post.id,
            interaction_id=interaction.id if interaction else None,
            candidate_index=index,
            generated_text=draft["text"],
            style=draft["style"],
            risk_level=draft["risk_level"],
            confidence=draft["confidence"],
            requires_fact_check=draft["requires_fact_check"],
            model_version=draft["model_version"],
            prompt_version=draft["prompt_version"],
            content_hash=draft["content_hash"],
            duplicate_score=draft["duplicate_score"],
            generation_metadata_json=_json_text(
                {
                    "fallback_used": generated["fallback_used"],
                    "reason": generated["reason"],
                    "mode": body.mode,
                    "target_post_id": post.x_post_id,
                    "input_risk": generated["input_risk"],
                    "token_usage": generated.get("token_usage") or {},
                }
            ),
            review_status="pending" if draft["risk_level"] != "blocked" else "invalidated",
            created_at=now,
            updated_at=now,
        )
        session.add(candidate)
        await session.flush()
        review = None
        if candidate.review_status == "pending":
            review = XReviewTask(
                owner_user_id=owner_user_id,
                account_id=account.id,
                reply_candidate_id=candidate.id,
                interaction_id=interaction.id if interaction else None,
                review_status="pending",
                created_at=now,
                updated_at=now,
            )
            session.add(review)
            await session.flush()
        persisted.append(
            {
                "candidate": _serialize(candidate),
                "review": _serialize(review),
            }
        )
    await _audit(
        session,
        owner_user_id=owner_user_id,
        actor_user_id=actor_user_id,
        action="reply_candidates.generated",
        entity_type="x_post",
        entity_id=str(post.id),
        account_id=account.id,
        after={
            "candidate_ids": [item["candidate"]["id"] for item in persisted],
            "fallback_used": generated["fallback_used"],
        },
    )
    return {
        "success": True,
        "account": _serialize(account),
        "post": {**_serialize(post), "post_url": _post_url(post.x_post_id)},
        "items": persisted,
        "total": len(persisted),
        "recommended_index": generated["recommended_index"],
        "reason": generated["reason"],
        "fallback_used": generated["fallback_used"],
    }


@router.post("/posts/{post_id}/reply-candidates")
async def generate_reply_candidates(
    post_id: str,
    body: XReplyCandidatesRequest,
    current_user: dict = Depends(require_x_operator),
):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        post = await _owned_post(session, post_id, owner_user_id)
        if post is None:
            raise HTTPException(status_code=404, detail="帖子不存在")
        return await _generate_candidates_for_post(
            session,
            owner_user_id=owner_user_id,
            actor_user_id=owner_user_id,
            post=post,
            body=body,
        )


async def _review_payload(
    session: AsyncSession,
    *,
    review: XReviewTask,
    owner_user_id: str,
) -> Dict[str, Any]:
    candidate = await _owned_by_id(
        session,
        XReplyCandidate,
        review.reply_candidate_id,
        owner_user_id,
    )
    post = (
        await _owned_by_id(session, XPost, candidate.source_post_id, owner_user_id)
        if candidate
        else None
    )
    account = (
        await _owned_by_id(session, XAccount, review.account_id, owner_user_id)
        if review.account_id
        else None
    )
    interaction = (
        await _owned_by_id(session, XInteraction, review.interaction_id, owner_user_id)
        if review.interaction_id
        else None
    )
    eligibility = _decode_json(interaction.eligibility_json, {}) if interaction else {}
    if not eligibility and post and account:
        own_posts_result = await session.execute(
            select(XPost.x_post_id).where(
                XPost.owner_user_id == owner_user_id,
                XPost.author_x_user_id == account.x_user_id,
            )
        )
        eligibility = compute_reply_eligibility(
            _serialize(post),
            account_username=account.username,
            account_post_ids=own_posts_result.scalars().all(),
        )
    policy_checks = [
        {"name": "candidate_not_blocked", "passed": bool(candidate and candidate.risk_level != "blocked")},
        {"name": "account_active", "passed": bool(account and account.status == "active")},
        {"name": "account_write_enabled", "passed": bool(account and account.write_enabled)},
        {"name": "api_reply_eligible", "passed": bool(eligibility.get("eligible"))},
        {
            "name": "content_hash_current",
            "passed": bool(
                candidate
                and candidate.content_hash
                == content_hash(candidate.edited_text or candidate.generated_text)
            ),
        },
    ]
    return {
        **_serialize(review),
        "candidate": _serialize(candidate),
        "post": (
            {**_serialize(post), "post_url": _post_url(post.x_post_id)}
            if post
            else {}
        ),
        "account": _serialize(account),
        "interaction": _serialize(interaction),
        "api_reply_eligible": bool(eligibility.get("eligible")),
        "eligibility": eligibility,
        "policy_checks": policy_checks,
        "manual_fallback": {
            "copy_text": review.final_text or (candidate.edited_text or candidate.generated_text if candidate else ""),
            "post_url": _post_url(post.x_post_id) if post else "",
        },
    }


@router.get("/reviews")
async def list_reviews(
    status: Optional[str] = None,
    account_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        conditions = [XReviewTask.owner_user_id == owner_user_id]
        if status:
            conditions.append(XReviewTask.review_status == status)
        if account_id is not None:
            conditions.append(XReviewTask.account_id == account_id)
        total_result = await session.execute(select(func.count(XReviewTask.id)).where(*conditions))
        result = await session.execute(
            select(XReviewTask)
            .where(*conditions)
            .order_by(XReviewTask.priority.desc(), XReviewTask.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items = [
            await _review_payload(session, review=review, owner_user_id=owner_user_id)
            for review in result.scalars().all()
        ]
        return {"items": items, "total": int(total_result.scalar() or 0), "limit": limit, "offset": offset}


@router.get("/reviews/{review_id}")
async def get_review(review_id: int, current_user: dict = Depends(get_current_user)):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        review = await _owned_by_id(session, XReviewTask, review_id, owner_user_id)
        if review is None:
            raise HTTPException(status_code=404, detail="审核任务不存在")
        return await _review_payload(session, review=review, owner_user_id=owner_user_id)


@router.post("/reviews/{review_id}/regenerate")
async def regenerate_review(
    review_id: int,
    body: Optional[XReplyCandidatesRequest] = None,
    current_user: dict = Depends(require_x_operator),
):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        review = await _owned_by_id(session, XReviewTask, review_id, owner_user_id)
        if review is None:
            raise HTTPException(status_code=404, detail="审核任务不存在")
        candidate = await _owned_by_id(
            session,
            XReplyCandidate,
            review.reply_candidate_id,
            owner_user_id,
        )
        post = (
            await _owned_by_id(session, XPost, candidate.source_post_id, owner_user_id)
            if candidate
            else None
        )
        if candidate is None or post is None:
            raise HTTPException(status_code=409, detail="原候选或目标帖子已不存在")
        review.review_status = "cancelled"
        candidate.review_status = "invalidated"
        review.updated_at = _now_ms()
        candidate.updated_at = _now_ms()
        request_body = body or XReplyCandidatesRequest(account_id=candidate.account_id)
        if request_body.account_id is None:
            request_body.account_id = candidate.account_id
        return await _generate_candidates_for_post(
            session,
            owner_user_id=owner_user_id,
            actor_user_id=owner_user_id,
            post=post,
            body=request_body,
        )


@router.post("/reviews/{review_id}/approve")
async def approve_review(
    review_id: int,
    body: XReviewApprovalRequest,
    current_user: dict = Depends(require_x_operator),
):
    if not body.explicit_confirmation:
        raise HTTPException(status_code=400, detail="必须明确确认目标帖子和最终文本")
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        review = await _owned_by_id(session, XReviewTask, review_id, owner_user_id)
        if review is None:
            raise HTTPException(status_code=404, detail="审核任务不存在")
        if review.reply_candidate_id != body.candidate_id:
            raise HTTPException(status_code=400, detail="candidate_id 与审核任务不匹配")
        if review.review_status not in {"pending", "in_review", "approved"}:
            raise HTTPException(status_code=409, detail=f"当前审核状态不可批准: {review.review_status}")
        candidate = await _owned_by_id(
            session,
            XReplyCandidate,
            body.candidate_id,
            owner_user_id,
        )
        if candidate is None:
            raise HTTPException(status_code=404, detail="候选不存在")
        actual_hash = content_hash(body.final_text)
        if actual_hash != body.content_hash:
            raise HTTPException(status_code=400, detail="content_hash 与最终文本不匹配，审批已拒绝")
        risk = scan_content_risk(body.final_text)
        if risk["risk_level"] == "high":
            raise HTTPException(status_code=400, detail={"message": "最终文本触发高风险策略", "risk": risk})
        before = _serialize(review)
        candidate.edited_text = body.final_text if body.final_text != candidate.generated_text else ""
        candidate.content_hash = actual_hash
        candidate.risk_level = risk["risk_level"]
        candidate.review_status = "approved"
        candidate.updated_at = _now_ms()
        review.review_status = "approved"
        review.final_text = body.final_text
        review.final_content_hash = actual_hash
        review.review_reason = body.reason
        review.reviewed_by_user_id = owner_user_id
        review.reviewed_at = _now_ms()
        review.updated_at = _now_ms()
        await _audit(
            session,
            owner_user_id=owner_user_id,
            actor_user_id=owner_user_id,
            action="review.approved",
            entity_type="x_review_task",
            entity_id=str(review.id),
            account_id=review.account_id,
            before=before,
            after=_serialize(review),
            metadata={"candidate_id": candidate.id, "content_hash": actual_hash},
        )
        return {
            "success": True,
            "message": "已批准；发布时仍会重新检查 Kill Switch、资格、预算和文本哈希",
            "review": await _review_payload(session, review=review, owner_user_id=owner_user_id),
        }


@router.post("/reviews/{review_id}/reject")
async def reject_review(
    review_id: int,
    body: XReviewRejectRequest,
    current_user: dict = Depends(require_x_operator),
):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        review = await _owned_by_id(session, XReviewTask, review_id, owner_user_id)
        if review is None:
            raise HTTPException(status_code=404, detail="审核任务不存在")
        candidate = await _owned_by_id(
            session,
            XReplyCandidate,
            review.reply_candidate_id,
            owner_user_id,
        )
        if review.review_status == "published":
            raise HTTPException(status_code=409, detail="已发布任务不能拒绝")
        review.review_status = "rejected"
        review.review_reason = body.reason
        review.reviewed_by_user_id = owner_user_id
        review.reviewed_at = _now_ms()
        review.updated_at = _now_ms()
        if candidate:
            candidate.review_status = "rejected"
            candidate.updated_at = _now_ms()
        await _audit(
            session,
            owner_user_id=owner_user_id,
            actor_user_id=owner_user_id,
            action="review.rejected",
            entity_type="x_review_task",
            entity_id=str(review.id),
            account_id=review.account_id,
            after={"reason": body.reason},
        )
        return {"success": True, "review": _serialize(review)}


async def _write_count_today(
    session: AsyncSession,
    *,
    owner_user_id: str,
    account_id: int,
) -> int:
    result = await session.execute(
        select(func.coalesce(func.sum(XApiUsageDaily.write_count), 0)).where(
            XApiUsageDaily.owner_user_id == owner_user_id,
            XApiUsageDaily.account_id == account_id,
            XApiUsageDaily.usage_date == utc_usage_date(),
        )
    )
    return int(result.scalar() or 0)


async def _user_opted_out(
    session: AsyncSession,
    *,
    owner_user_id: str,
    account_id: int,
    x_user_id: str,
) -> bool:
    if not x_user_id:
        return False
    result = await session.execute(
        select(func.count(XUserOptOut.id)).where(
            XUserOptOut.owner_user_id == owner_user_id,
            XUserOptOut.x_user_id == x_user_id,
            XUserOptOut.account_id.in_([0, account_id]),
            XUserOptOut.status == "active",
        )
    )
    return int(result.scalar() or 0) > 0


@router.post("/reviews/{review_id}/publish")
async def publish_review(
    review_id: int,
    body: XPublishRequest,
    request: Request,
    current_user: dict = Depends(require_x_operator),
):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        review = await _owned_by_id(session, XReviewTask, review_id, owner_user_id)
        if review is None:
            raise HTTPException(status_code=404, detail="审核任务不存在")
        if review.reply_candidate_id != body.candidate_id:
            raise HTTPException(status_code=400, detail="candidate_id 与审核任务不匹配")
        if body.publish_mode == "manual_review" and review.review_status != "approved":
            raise HTTPException(status_code=409, detail="人工发布前必须完成逐条审核")
        candidate = await _owned_by_id(
            session,
            XReplyCandidate,
            body.candidate_id,
            owner_user_id,
        )
        account = await _owned_by_id(session, XAccount, review.account_id, owner_user_id)
        post = (
            await _owned_by_id(session, XPost, candidate.source_post_id, owner_user_id)
            if candidate
            else None
        )
        if candidate is None or account is None or post is None:
            raise HTTPException(status_code=409, detail="候选、账号或目标帖子已不存在")
        final_text = review.final_text or candidate.edited_text or candidate.generated_text
        if content_hash(final_text) != body.content_hash:
            raise HTTPException(status_code=400, detail="文本已变化，原审批失效，请重新审核")

        existing_result = await session.execute(
            select(XPublishJob).where(
                XPublishJob.owner_user_id == owner_user_id,
                XPublishJob.account_id == account.id,
                XPublishJob.target_post_id == post.x_post_id,
                XPublishJob.publish_mode == body.publish_mode,
            ).with_for_update()
        )
        existing = existing_result.scalars().first()
        retrying_existing_job = False
        if existing is not None:
            same_approval = (
                existing.reply_candidate_id == candidate.id
                and existing.review_task_id == review.id
                and existing.approval_content_hash == body.content_hash
                and content_hash(existing.reply_text) == body.content_hash
            )
            if not same_approval:
                raise HTTPException(
                    status_code=409,
                    detail="该目标已有绑定其他候选、审核或文本版本的发布任务",
                )
            if existing.status == "succeeded":
                return {
                    "success": True,
                    "idempotent_replay": True,
                    "publish_job": _serialize(existing),
                    "x_post_id": existing.x_post_id,
                }
            if existing.status in {"pending", "running"}:
                raise HTTPException(
                    status_code=409,
                    detail={"message": "该发布任务正在处理中", "publish_job": _serialize(existing)},
                )
            if existing.status not in {"failed", "retry_wait"}:
                raise HTTPException(
                    status_code=409,
                    detail={"message": "该发布任务当前不可重试", "publish_job": _serialize(existing)},
                )
            if int(existing.retry_count or 0) >= int(existing.max_retries or 3):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "该发布任务已达到最大重试次数",
                        "publish_job": _serialize(existing),
                    },
                )
            if not body.explicit_confirmation:
                raise HTTPException(status_code=400, detail="重试发布必须再次明确确认目标帖子和最终文本")
            retrying_existing_job = True

        try:
            access_token = await _account_access_token(session, account)
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        if not access_token:
            await session.commit()
            raise HTTPException(status_code=503, detail="X user access token 未配置或已过期，账号写入已关闭")

        try:
            async with _browser_reader() as client:
                target_payload = await client.lookup_post(post.x_post_id)
            users = included_users(target_payload)
            live_post = map_post(target_payload.get("data") or {}, users_by_id=users)
            await _record_usage(
                session,
                owner_user_id=owner_user_id,
                endpoint="BROWSER /i/web/status/{id} prepublish",
                read_count=1,
            )
        except XBrowserError as exc:
            await _record_usage(
                session,
                owner_user_id=owner_user_id,
                endpoint="BROWSER /i/web/status/{id} prepublish",
                success=False,
            )
            await session.commit()
            _raise_x_browser_error(exc)

        own_posts_result = await session.execute(
            select(XPost.x_post_id).where(
                XPost.owner_user_id == owner_user_id,
                XPost.author_x_user_id == account.x_user_id,
            )
        )
        eligibility = compute_reply_eligibility(
            live_post,
            account_username=account.username,
            account_post_ids=own_posts_result.scalars().all(),
        )
        interaction = (
            await _owned_by_id(session, XInteraction, candidate.interaction_id, owner_user_id)
            if candidate.interaction_id
            else None
        )
        opted_out = await _user_opted_out(
            session,
            owner_user_id=owner_user_id,
            account_id=account.id,
            x_user_id=str(live_post.get("author_x_user_id") or ""),
        )
        replied_statement = select(func.count(XPublishJob.id)).where(
                XPublishJob.owner_user_id == owner_user_id,
                XPublishJob.account_id == account.id,
                XPublishJob.target_post_id == post.x_post_id,
                XPublishJob.status.in_(["pending", "running", "succeeded", "retry_wait"]),
            )
        if existing is not None:
            replied_statement = replied_statement.where(XPublishJob.id != existing.id)
        replied_result = await session.execute(replied_statement)
        already_replied = int(replied_result.scalar() or 0) > 0 or bool(
            interaction
            and interaction.replied_publish_job_id
            and (existing is None or interaction.replied_publish_job_id != existing.id)
        )
        controls = await _controls(session, owner_user_id)
        topic = (
            await _owned_by_id(session, XTopic, post.source_topic_id, owner_user_id)
            if post.source_topic_id
            else None
        )
        region = (
            await _owned_by_id(session, XRegion, topic.region_id, owner_user_id)
            if topic
            else None
        )
        target_context = f"{topic.raw_name if topic else ''} {live_post.get('text') or ''}"
        paused_region_matches = _region_pause_matches(
            region,
            _control_list(controls, "paused_regions"),
        )
        paused_keyword_matches = _matches_control_terms(
            target_context,
            _control_list(controls, "paused_keywords"),
        )
        high_risk_matches = _matches_control_terms(
            target_context,
            _control_list(controls, "high_risk_topics"),
        )
        operational_scope_allowed = not (
            paused_region_matches or paused_keyword_matches or high_risk_matches
        )
        duplicate_threshold = float(controls.get("duplicate_threshold", 0.92))
        write_used = await _write_count_today(
            session,
            owner_user_id=owner_user_id,
            account_id=account.id,
        )
        write_limit = int(controls.get("daily_write_limit") or x_config.X_DAILY_WRITE_BUDGET)
        budget = evaluate_budget(write_used, write_limit, 1)
        scopes = _decode_json(account.granted_scopes, [])
        target_risk = scan_content_risk(str(live_post.get("text") or ""))
        opt_in_evidence = _decode_json(interaction.opt_in_evidence_json, {}) if interaction else {}
        policy_now = _now_ms()
        hourly_limit = controls.get("hourly_write_limit")
        max_per_user = controls.get("max_interactions_per_user")
        minimum_interval = controls.get("min_reply_interval_seconds")
        automation_limits_configured = all(
            value is not None
            for value in (hourly_limit, max_per_user, minimum_interval)
        )
        hourly_result = await session.execute(
            select(func.count(XPublishJob.id)).where(
                XPublishJob.owner_user_id == owner_user_id,
                XPublishJob.account_id == account.id,
                XPublishJob.status == "succeeded",
                XPublishJob.executed_at >= policy_now - 3_600_000,
            )
        )
        hourly_count = int(hourly_result.scalar() or 0)
        hourly_write_allowed = bool(
            hourly_limit is not None
            and (int(hourly_limit) == 0 or hourly_count < int(hourly_limit))
        )
        target_user_id = str(live_post.get("author_x_user_id") or "")
        per_user_result = await session.execute(
            select(func.count(XPublishJob.id)).where(
                XPublishJob.owner_user_id == owner_user_id,
                XPublishJob.account_id == account.id,
                XPublishJob.target_user_id == target_user_id,
                XPublishJob.status == "succeeded",
                XPublishJob.executed_at >= policy_now - 86_400_000,
            )
        )
        per_user_count = int(per_user_result.scalar() or 0)
        per_user_frequency_allowed = bool(
            max_per_user is not None and per_user_count < int(max_per_user)
        )
        last_publish_result = await session.execute(
            select(func.max(XPublishJob.executed_at)).where(
                XPublishJob.owner_user_id == owner_user_id,
                XPublishJob.account_id == account.id,
                XPublishJob.status == "succeeded",
            )
        )
        last_publish_at = int(last_publish_result.scalar() or 0)
        min_reply_interval_allowed = bool(
            minimum_interval is not None
            and (
                last_publish_at == 0
                or policy_now - last_publish_at >= int(minimum_interval) * 1000
            )
        )
        intent_evidence = opt_in_evidence.get("intent") if isinstance(opt_in_evidence, dict) else {}
        if not isinstance(intent_evidence, dict):
            intent_evidence = {}
        allowed_auto_reply_intents = (
            controls.get("auto_reply_intents")
            or controls.get("allowed_intents")
            or []
        )
        policy = evaluate_publication_policy(
            PublicationContext(
                publish_mode=body.publish_mode,
                candidate_text=final_text,
                supplied_content_hash=body.content_hash,
                approved_content_hash=review.final_content_hash,
                explicit_confirmation=body.explicit_confirmation,
                write_enabled=bool(controls["write_enabled"]),
                global_kill_switch=bool(controls["global_kill_switch"]),
                require_human_review=bool(controls["require_human_review"]),
                account_write_enabled=bool(account.write_enabled),
                account_status=account.status,
                has_user_token=bool(access_token),
                granted_scopes=scopes,
                target_post_exists=True,
                api_reply_eligible=bool(eligibility["eligible"]),
                already_replied=already_replied,
                user_opted_out=opted_out,
                within_write_budget=budget.allowed,
                risk_level=candidate.risk_level,
                factual_confidence=float(candidate.confidence or 0),
                sensitive_topic=bool(target_risk["sensitive_topic"]),
                x_written_approval=bool(account.x_written_approval),
                auto_reply_enabled=bool(account.auto_reply_enabled),
                global_auto_reply_enabled=bool(controls["auto_reply_enabled"]),
                automated_label_enabled=bool(account.automated_label_enabled),
                user_initiated=bool(
                    interaction
                    and interaction.interaction_type in {"mention", "reply", "quote", "campaign_reply"}
                ),
                explicitly_addresses_account=bool(eligibility["eligible"]),
                automation_limits_configured=automation_limits_configured,
                hourly_write_allowed=hourly_write_allowed,
                per_user_frequency_allowed=per_user_frequency_allowed,
                min_reply_interval_allowed=min_reply_interval_allowed,
                duplicate_score=float(candidate.duplicate_score or 0),
                duplicate_threshold=duplicate_threshold,
                operational_scope_allowed=operational_scope_allowed,
                operational_scope_reason=(
                    "target matched paused regions, paused keywords, or high-risk topics"
                    if not operational_scope_allowed
                    else ""
                ),
                interaction_intent=str(intent_evidence.get("code") or ""),
                interaction_intent_label=str(intent_evidence.get("label") or ""),
                intent_evidence_present=bool(
                    intent_evidence.get("classifier_version")
                    and intent_evidence.get("code")
                ),
                allowed_auto_reply_intents=allowed_auto_reply_intents,
                evidence={
                    "eligibility": eligibility,
                    "opt_in": opt_in_evidence,
                    "target_post_id": post.x_post_id,
                    "intent": intent_evidence,
                    "operational_scope": {
                        "paused_regions": paused_region_matches,
                        "paused_keywords": paused_keyword_matches,
                        "high_risk_topics": high_risk_matches,
                    },
                },
            )
        )
        now = _now_ms()
        policy_row = XPolicyDecision(
            owner_user_id=owner_user_id,
            account_id=account.id,
            reply_candidate_id=candidate.id,
            interaction_id=interaction.id if interaction else None,
            target_post_id=post.x_post_id,
            policy_version=policy.policy_version,
            decision=policy.decision,
            rule_results_json=_json_text(policy.rule_results, fallback="[]"),
            evidence_json=_json_text(
                {
                    "eligibility": eligibility,
                    "opt_in": opt_in_evidence,
                    "write_budget": budget.to_dict(),
                    "automation_frequency": {
                        "hourly_limit": hourly_limit,
                        "hourly_count": hourly_count,
                        "max_interactions_per_user": max_per_user,
                        "per_user_count_24h": per_user_count,
                        "min_reply_interval_seconds": minimum_interval,
                        "last_publish_at": last_publish_at,
                    },
                    "intent": intent_evidence,
                    "allowed_auto_reply_intents": allowed_auto_reply_intents,
                    "duplicate_policy": {
                        "score": float(candidate.duplicate_score or 0),
                        "threshold": duplicate_threshold,
                    },
                    "operational_scope": {
                        "paused_regions": paused_region_matches,
                        "paused_keywords": paused_keyword_matches,
                        "high_risk_topics": high_risk_matches,
                    },
                }
            ),
            blocked_reason=policy.blocked_reason,
            input_content_hash=policy.input_content_hash,
            evaluated_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(policy_row)
        await session.flush()
        if not policy.allowed:
            await _audit(
                session,
                owner_user_id=owner_user_id,
                actor_user_id=owner_user_id,
                action="publish.blocked",
                entity_type="x_policy_decision",
                entity_id=str(policy_row.id),
                account_id=account.id,
                outcome="blocked",
                after=policy.to_dict(),
                request_id=request.headers.get("x-request-id", ""),
                ip_address=request.client.host if request.client else "",
            )
            await session.commit()
            raise HTTPException(
                status_code=400,
                detail={
                    "message": policy.blocked_reason,
                    "decision": policy.to_dict(),
                    "manual_fallback": {
                        "copy_text": final_text,
                        "post_url": _post_url(post.x_post_id),
                    },
                },
            )

        idempotency_key = build_idempotency_key(
            owner_user_id=owner_user_id,
            account_id=account.id,
            target_post_id=post.x_post_id,
            publish_mode=body.publish_mode,
            approved_content_hash=body.content_hash,
        )
        if retrying_existing_job:
            publish_job = existing
            publish_job.policy_decision_id = policy_row.id
            publish_job.target_user_id = str(live_post.get("author_x_user_id") or "")
            publish_job.opt_in_evidence_json = _json_text(opt_in_evidence)
            publish_job.status = "running"
            publish_job.executed_at = now
            publish_job.error_code = ""
            publish_job.error_message = ""
            publish_job.updated_at = now
        else:
            publish_job = XPublishJob(
                owner_user_id=owner_user_id,
                account_id=account.id,
                reply_candidate_id=candidate.id,
                review_task_id=review.id,
                interaction_id=interaction.id if interaction else None,
                policy_decision_id=policy_row.id,
                target_post_id=post.x_post_id,
                target_user_id=str(live_post.get("author_x_user_id") or ""),
                publish_mode=body.publish_mode,
                reply_text=final_text,
                approval_content_hash=body.content_hash,
                opt_in_evidence_json=_json_text(opt_in_evidence),
                idempotency_key=idempotency_key,
                status="running",
                scheduled_at=now,
                executed_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(publish_job)
        await session.flush()
        attempt_result = await session.execute(
            select(func.coalesce(func.max(XPublishResult.attempt_no), 0)).where(
                XPublishResult.owner_user_id == owner_user_id,
                XPublishResult.publish_job_id == publish_job.id,
            )
        )
        attempt_no = int(attempt_result.scalar() or 0) + 1
        if retrying_existing_job:
            await _audit(
                session,
                owner_user_id=owner_user_id,
                actor_user_id=owner_user_id,
                action="reply.retry_started",
                entity_type="x_publish_job",
                entity_id=str(publish_job.id),
                account_id=account.id,
                after={"attempt_no": attempt_no, "policy_decision_id": policy_row.id},
            )
        try:
            async with XWriteApiClient(
                user_access_token=access_token,
                base_url=x_config.X_WRITE_API_BASE_URL,
                response_observer=_response_observer(
                    session,
                    owner_user_id=owner_user_id,
                    account_id=account.id,
                ),
            ) as client:
                response = await XPublisher(client).publish_reply(
                    text=final_text,
                    target_post_id=post.x_post_id,
                    idempotency_key=idempotency_key,
                    policy=policy,
                )
            created = response.get("data") or {}
            x_post_id = str(created.get("id") or "")
            publish_job.status = "succeeded"
            publish_job.x_post_id = x_post_id
            publish_job.error_code = ""
            publish_job.error_message = ""
            publish_job.updated_at = _now_ms()
            result_row = XPublishResult(
                owner_user_id=owner_user_id,
                publish_job_id=publish_job.id,
                account_id=account.id,
                attempt_no=attempt_no,
                success=True,
                x_post_id=x_post_id,
                http_status=201,
                response_metadata_json=_json_text({"id": x_post_id}),
                request_id=request.headers.get("x-request-id", ""),
                attempted_at=_now_ms(),
                created_at=_now_ms(),
                updated_at=_now_ms(),
            )
            session.add(result_row)
            candidate.review_status = "published"
            candidate.updated_at = _now_ms()
            review.review_status = "published"
            review.updated_at = _now_ms()
            if interaction:
                interaction.status = "published"
                interaction.replied_publish_job_id = publish_job.id
                interaction.processed_at = _now_ms()
                interaction.updated_at = _now_ms()
            await _record_usage(
                session,
                owner_user_id=owner_user_id,
                account_id=account.id,
                endpoint="POST /2/tweets",
                write_count=1,
            )
            await _audit(
                session,
                owner_user_id=owner_user_id,
                actor_user_id=owner_user_id,
                action="reply.published",
                entity_type="x_publish_job",
                entity_id=str(publish_job.id),
                account_id=account.id,
                after={"x_post_id": x_post_id, "target_post_id": post.x_post_id},
                request_id=request.headers.get("x-request-id", ""),
                ip_address=request.client.host if request.client else "",
            )
            return {
                "success": True,
                "publish_job": _serialize(publish_job),
                "publish_result": _serialize(result_row),
                "x_post_id": x_post_id,
                "x_post_url": _post_url(x_post_id),
            }
        except XApiError as exc:
            publish_job.retry_count = int(publish_job.retry_count or 0) + 1
            publish_job.status = (
                "retry_wait"
                if exc.retryable and publish_job.retry_count < int(publish_job.max_retries or 3)
                else "failed"
            )
            publish_job.error_code = exc.error_code
            publish_job.error_message = str(exc)[:1000]
            publish_job.updated_at = _now_ms()
            reset_at = int(exc.reset_at or 0) * 1000 if isinstance(exc, XRateLimitError) else 0
            if publish_job.status == "retry_wait" and reset_at:
                publish_job.scheduled_at = reset_at
            result_row = XPublishResult(
                owner_user_id=owner_user_id,
                publish_job_id=publish_job.id,
                account_id=account.id,
                attempt_no=attempt_no,
                success=False,
                http_status=exc.status_code,
                x_error_code=exc.error_code,
                error_message=str(exc)[:1000],
                retryable=exc.retryable,
                rate_limit_reset_at=reset_at,
                response_metadata_json="{}",
                request_id=request.headers.get("x-request-id", ""),
                attempted_at=_now_ms(),
                created_at=_now_ms(),
                updated_at=_now_ms(),
            )
            session.add(result_row)
            await _record_usage(
                session,
                owner_user_id=owner_user_id,
                account_id=account.id,
                endpoint="POST /2/tweets",
                success=False,
            )
            await _audit(
                session,
                owner_user_id=owner_user_id,
                actor_user_id=owner_user_id,
                action="reply.publish_failed",
                entity_type="x_publish_job",
                entity_id=str(publish_job.id),
                account_id=account.id,
                outcome="failed",
                after={
                    "attempt_no": attempt_no,
                    "error_code": exc.error_code,
                    "retryable": exc.retryable,
                },
            )
            await session.commit()
            _raise_x_error(exc)


@router.post("/interactions/refresh")
async def refresh_mentions(
    body: Optional[XMentionsRefreshRequest] = None,
    current_user: dict = Depends(require_x_operator),
):
    """Incrementally collect mentions for one bound account.

    This endpoint only persists Posts and interactions. It never generates,
    approves, queues, or publishes a reply.
    """

    body = body or XMentionsRefreshRequest()
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        controls = await _controls(session, owner_user_id)
        if not controls["read_enabled"]:
            raise HTTPException(status_code=400, detail="X 只读采集开关已关闭")
        account = await _select_account(
            session,
            owner_user_id=owner_user_id,
            account_id=body.account_id,
        )
        await _crawl_limit_preflight(
            session,
            owner_user_id=owner_user_id,
            requested=body.max_posts,
        )

        since_id = body.since_id
        if not since_id:
            existing_ids_result = await session.execute(
                select(XInteraction.interaction_post_id).where(
                    XInteraction.owner_user_id == owner_user_id,
                    XInteraction.account_id == account.id,
                )
            )
            numeric_ids = [
                int(value)
                for value in existing_ids_result.scalars().all()
                if str(value).isdigit()
            ]
            since_id = str(max(numeric_ids)) if numeric_ids else ""
        try:
            async with _browser_reader() as client:
                if not account.username:
                    identity = await client.get_current_identity()
                    account.x_user_id = str(identity["id"])
                    account.username = str(identity.get("username") or "")
                    account.display_name = str(identity.get("name") or "")
                payload = await client.get_mentions(
                    account.username,
                    since_id=since_id,
                    max_total=body.max_posts,
                )
        except XBrowserError as exc:
            await _record_usage(
                session,
                owner_user_id=owner_user_id,
                account_id=account.id,
                endpoint="BROWSER /notifications/mentions",
                success=False,
            )
            await session.commit()
            _raise_x_browser_error(exc)

        users = included_users(payload)
        own_posts_result = await session.execute(
            select(XPost.x_post_id).where(
                XPost.owner_user_id == owner_user_id,
                XPost.author_x_user_id == account.x_user_id,
            )
        )
        own_post_ids = list(own_posts_result.scalars().all())
        now = _now_ms()
        stored: List[Dict[str, Any]] = []
        newest_id = int(since_id) if since_id else 0
        for raw_post in payload.get("data") or []:
            values = map_post(raw_post, users_by_id=users)
            values["post_type"] = "mention"
            post = await _upsert_post(
                session,
                owner_user_id=owner_user_id,
                values=values,
            )
            await session.flush()
            x_post_id = str(values["x_post_id"])
            if x_post_id.isdigit():
                newest_id = max(newest_id, int(x_post_id))
            eligibility = compute_reply_eligibility(
                values,
                account_username=account.username,
                account_post_ids=own_post_ids,
            )
            intent = classify_interaction_intent(str(values.get("text") or ""))
            references = values.get("referenced_tweets_json") or []
            if any(item.get("type") == "quoted" for item in references):
                interaction_type = "quote"
            elif any(item.get("type") == "replied_to" for item in references):
                interaction_type = "reply"
            else:
                interaction_type = "mention"
            opt_out = detect_opt_out(str(values.get("text") or ""))
            interaction_result = await session.execute(
                select(XInteraction).where(
                    XInteraction.owner_user_id == owner_user_id,
                    XInteraction.account_id == account.id,
                    XInteraction.interaction_post_id == x_post_id,
                )
            )
            interaction = interaction_result.scalars().first()
            if interaction is None:
                interaction = XInteraction(
                    owner_user_id=owner_user_id,
                    account_id=account.id,
                    interaction_post_id=x_post_id,
                    actor_x_user_id=str(values.get("author_x_user_id") or ""),
                    interaction_type=interaction_type,
                    received_at=int(values.get("created_at_x") or now),
                    created_at=now,
                )
                session.add(interaction)
            interaction.opt_in_evidence_json = _json_text(
                {
                    "source": "BROWSER /notifications/mentions",
                    "user_initiated": True,
                    "interaction_type": interaction_type,
                    "eligibility": eligibility,
                    "intent": intent,
                }
            )
            interaction.eligibility_json = _json_text(eligibility)
            interaction.is_opted_out = bool(opt_out["opted_out"]) or await _user_opted_out(
                session,
                owner_user_id=owner_user_id,
                account_id=account.id,
                x_user_id=interaction.actor_x_user_id,
            )
            interaction.status = (
                "blocked"
                if interaction.is_opted_out
                else ("eligible" if eligibility["eligible"] else "pending")
            )
            interaction.updated_at = now
            await session.flush()

            if opt_out["opted_out"]:
                opt_result = await session.execute(
                    select(XUserOptOut).where(
                        XUserOptOut.owner_user_id == owner_user_id,
                        XUserOptOut.account_id == account.id,
                        XUserOptOut.x_user_id == interaction.actor_x_user_id,
                    )
                )
                opt_record = opt_result.scalars().first()
                if opt_record is None:
                    opt_record = XUserOptOut(
                        owner_user_id=owner_user_id,
                        account_id=account.id,
                        x_user_id=interaction.actor_x_user_id,
                        created_at=now,
                    )
                    session.add(opt_record)
                opt_record.status = "active"
                opt_record.source_interaction_id = interaction.id
                opt_record.source_post_id = x_post_id
                opt_record.detected_phrase = opt_out["detected_phrase"]
                opt_record.evidence_json = _json_text({"text_hash": content_hash(post.text)})
                opt_record.detected_at = now
                opt_record.updated_at = now

            stored.append(
                {
                    "interaction": _serialize(interaction),
                    "post": {**_serialize(post), "post_url": _post_url(post.x_post_id)},
                    "eligibility": eligibility,
                }
            )

        account.last_sync_at = now
        account.last_error = ""
        account.updated_at = now
        await _record_usage(
            session,
            owner_user_id=owner_user_id,
            account_id=account.id,
            endpoint="BROWSER /notifications/mentions",
            read_count=len(stored),
        )
        await _audit(
            session,
            owner_user_id=owner_user_id,
            actor_user_id=owner_user_id,
            action="interactions.mentions_refreshed",
            entity_type="x_account",
            entity_id=str(account.id),
            account_id=account.id,
            after={
                "since_id": since_id,
                "next_since_id": str(newest_id) if newest_id else "",
                "interaction_count": len(stored),
                "auto_publish_created": False,
            },
        )
        return {
            "success": True,
            "account_id": account.id,
            "since_id": since_id,
            "next_since_id": str(newest_id) if newest_id else "",
            "items": stored,
            "total": len(stored),
            "auto_publish_created": False,
        }


@router.get("/interactions")
async def list_interactions(
    status: Optional[str] = None,
    account_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        conditions = [XInteraction.owner_user_id == owner_user_id]
        if status:
            conditions.append(XInteraction.status == status)
        if account_id:
            conditions.append(XInteraction.account_id == account_id)
        total_result = await session.execute(select(func.count(XInteraction.id)).where(*conditions))
        result = await session.execute(
            select(XInteraction)
            .where(*conditions)
            .order_by(XInteraction.received_at.desc(), XInteraction.id.desc())
            .limit(limit)
            .offset(offset)
        )
        items = []
        for interaction in result.scalars().all():
            post_result = await session.execute(
                select(XPost).where(
                    XPost.owner_user_id == owner_user_id,
                    XPost.x_post_id == interaction.interaction_post_id,
                )
            )
            post = post_result.scalars().first()
            items.append(
                {
                    **_serialize(interaction),
                    "post": (
                        {**_serialize(post), "post_url": _post_url(post.x_post_id)}
                        if post
                        else {}
                    ),
                }
            )
        return {"items": items, "total": int(total_result.scalar() or 0), "limit": limit, "offset": offset}


@router.post("/interactions/{interaction_id}/evaluate")
async def evaluate_interaction(
    interaction_id: int,
    body: XInteractionEvaluateRequest,
    current_user: dict = Depends(require_x_operator),
):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        interaction = await _owned_by_id(
            session,
            XInteraction,
            interaction_id,
            owner_user_id,
        )
        if interaction is None:
            raise HTTPException(status_code=404, detail="互动不存在")
        account = await _owned_by_id(
            session,
            XAccount,
            interaction.account_id,
            owner_user_id,
        )
        post_result = await session.execute(
            select(XPost).where(
                XPost.owner_user_id == owner_user_id,
                XPost.x_post_id == interaction.interaction_post_id,
            )
        )
        post = post_result.scalars().first()
        if account is None or post is None:
            raise HTTPException(status_code=409, detail="互动关联账号或帖子不存在")
        own_post_ids = body.account_post_ids
        if not own_post_ids:
            own_result = await session.execute(
                select(XPost.x_post_id).where(
                    XPost.owner_user_id == owner_user_id,
                    XPost.author_x_user_id == account.x_user_id,
                )
            )
            own_post_ids = list(own_result.scalars().all())
        eligibility = compute_reply_eligibility(
            _serialize(post),
            account_username=account.username,
            account_post_ids=own_post_ids,
        )
        opt_out = detect_opt_out(post.text)
        intent = classify_interaction_intent(post.text)
        if opt_out["opted_out"]:
            existing = await session.execute(
                select(XUserOptOut).where(
                    XUserOptOut.owner_user_id == owner_user_id,
                    XUserOptOut.account_id == account.id,
                    XUserOptOut.x_user_id == interaction.actor_x_user_id,
                )
            )
            record = existing.scalars().first()
            now = _now_ms()
            if record is None:
                record = XUserOptOut(
                    owner_user_id=owner_user_id,
                    account_id=account.id,
                    x_user_id=interaction.actor_x_user_id,
                    created_at=now,
                )
                session.add(record)
            record.status = "active"
            record.source_interaction_id = interaction.id
            record.source_post_id = interaction.interaction_post_id
            record.detected_phrase = opt_out["detected_phrase"]
            record.evidence_json = _json_text({"text_hash": content_hash(post.text)})
            record.detected_at = now
            record.updated_at = now
        interaction.eligibility_json = _json_text(eligibility)
        interaction.opt_in_evidence_json = _json_text(
            {
                "interaction_type": interaction.interaction_type,
                "user_initiated": interaction.interaction_type in {"mention", "reply", "quote", "campaign_reply"},
                "eligibility": eligibility,
                "intent": intent,
            }
        )
        interaction.is_opted_out = opt_out["opted_out"] or await _user_opted_out(
            session,
            owner_user_id=owner_user_id,
            account_id=account.id,
            x_user_id=interaction.actor_x_user_id,
        )
        interaction.status = (
            "blocked"
            if interaction.is_opted_out
            else ("eligible" if eligibility["eligible"] else "blocked")
        )
        interaction.processed_at = _now_ms()
        interaction.updated_at = _now_ms()
        await _audit(
            session,
            owner_user_id=owner_user_id,
            actor_user_id=owner_user_id,
            action="interaction.evaluated",
            entity_type="x_interaction",
            entity_id=str(interaction.id),
            account_id=account.id,
            after={
                "status": interaction.status,
                "eligibility": eligibility,
                "opted_out": interaction.is_opted_out,
                "intent": intent,
            },
        )
        return {
            "success": True,
            "interaction": _serialize(interaction),
            "eligibility": eligibility,
            "opt_out": opt_out,
            "intent": intent,
        }


@router.post("/users/{x_user_id}/opt-out")
async def opt_out_user(
    x_user_id: str,
    body: XOptOutRequest,
    current_user: dict = Depends(require_x_operator),
):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        result = await session.execute(
            select(XUserOptOut).where(
                XUserOptOut.owner_user_id == owner_user_id,
                XUserOptOut.account_id == body.account_id,
                XUserOptOut.x_user_id == x_user_id,
            )
        )
        record = result.scalars().first()
        now = _now_ms()
        if record is None:
            record = XUserOptOut(
                owner_user_id=owner_user_id,
                account_id=body.account_id,
                x_user_id=x_user_id,
                created_at=now,
            )
            session.add(record)
        record.username_snapshot = body.username_snapshot
        record.status = "active"
        record.source_interaction_id = body.source_interaction_id
        record.source_post_id = body.source_post_id
        record.detected_phrase = body.detected_phrase
        record.evidence_json = _json_text(body.evidence)
        record.detected_at = now
        record.revoked_at = 0
        record.updated_at = now
        interactions_result = await session.execute(
            select(XInteraction).where(
                XInteraction.owner_user_id == owner_user_id,
                XInteraction.actor_x_user_id == x_user_id,
                or_(
                    XInteraction.account_id == body.account_id,
                    body.account_id == 0,
                ),
            )
        )
        for interaction in interactions_result.scalars().all():
            interaction.is_opted_out = True
            interaction.status = "blocked"
            interaction.updated_at = now
        await _audit(
            session,
            owner_user_id=owner_user_id,
            actor_user_id=owner_user_id,
            action="user.opted_out",
            entity_type="x_user",
            entity_id=x_user_id,
            account_id=body.account_id or None,
            after={"account_id": body.account_id, "detected_phrase": body.detected_phrase},
        )
        await session.flush()
        return {"success": True, "opt_out": _serialize(record)}


@router.get("/usage")
async def get_usage(
    usage_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = _owner(current_user)
    usage_date = usage_date or utc_usage_date()
    async with get_session() as session:
        result = await session.execute(
            select(XApiUsageDaily)
            .where(
                XApiUsageDaily.owner_user_id == owner_user_id,
                XApiUsageDaily.usage_date == usage_date,
            )
            .order_by(XApiUsageDaily.account_id, XApiUsageDaily.endpoint)
        )
        items = result.scalars().all()
        total_reads = sum(int(item.read_resource_count or 0) for item in items)
        total_writes = sum(int(item.write_count or 0) for item in items)
        budgets = configured_budgets()
        rate_result = await session.execute(
            select(XRateLimitState)
            .where(XRateLimitState.owner_user_id == owner_user_id)
            .order_by(XRateLimitState.observed_at.desc())
        )
        return {
            "usage_date": usage_date,
            "items": [_serialize(item) for item in items],
            "summary": {
                "request_count": sum(int(item.request_count or 0) for item in items),
                "success_count": sum(int(item.success_count or 0) for item in items),
                "error_count": sum(int(item.error_count or 0) for item in items),
                "read_resource_count": total_reads,
                "write_count": total_writes,
            },
            "budgets": {
                **budgets,
                "post_reads_status": evaluate_budget(total_reads, budgets["post_reads"], 0).to_dict(),
                "writes_status": evaluate_budget(total_writes, budgets["writes"], 0).to_dict(),
            },
            "rate_limits": [_serialize(item) for item in rate_result.scalars().all()],
        }


@router.get("/audit-logs")
async def list_audit_logs(
    action: Optional[str] = None,
    outcome: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = _owner(current_user)
    async with get_session() as session:
        conditions = [XAuditLog.owner_user_id == owner_user_id]
        if action:
            conditions.append(XAuditLog.action == action)
        if outcome:
            conditions.append(XAuditLog.outcome == outcome)
        total_result = await session.execute(select(func.count(XAuditLog.id)).where(*conditions))
        result = await session.execute(
            select(XAuditLog)
            .where(*conditions)
            .order_by(XAuditLog.created_at.desc(), XAuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return {
            "items": [_serialize(item) for item in result.scalars().all()],
            "total": int(total_result.scalar() or 0),
            "limit": limit,
            "offset": offset,
        }
