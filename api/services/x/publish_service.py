"""Low-level publisher called only after a successful policy evaluation."""

from __future__ import annotations

import hashlib
from typing import Any, Dict

from media_platform.x.client import XWriteApiClient

from .policy_service import PolicyEvaluation


def build_idempotency_key(
    *,
    owner_user_id: str,
    account_id: int,
    target_post_id: str,
    publish_mode: str,
    approved_content_hash: str,
) -> str:
    raw = "|".join(
        [owner_user_id, str(account_id), target_post_id, publish_mode, approved_content_hash]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class XPublisher:
    def __init__(self, client: XWriteApiClient) -> None:
        self.client = client

    async def publish_reply(
        self,
        *,
        text: str,
        target_post_id: str,
        idempotency_key: str,
        policy: PolicyEvaluation,
    ) -> Dict[str, Any]:
        if not policy.allowed:
            raise PermissionError(policy.blocked_reason or "publication policy blocked the request")
        return await self.client.create_reply(
            text=text,
            target_post_id=target_post_id,
            idempotency_key=idempotency_key,
        )
