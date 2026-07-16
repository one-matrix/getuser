from cryptography.fernet import Fernet

from api.services.x.account_service import (
    OAuthStateStore,
    _oauth_token_endpoint,
    decrypt_token,
    encrypt_token,
)
from api.services.x.policy_service import (
    PublicationContext,
    canonical_text,
    classify_interaction_intent,
    content_hash,
    evaluate_publication_policy,
)
from api.services.x.reply_service import OpenAICompatibleLLMClient, ReplyGenerator
from media_platform.x.field import (
    build_topic_query,
    compute_reply_eligibility,
    map_post,
)


def _publishable_context(**overrides):
    text = "Thanks for the feedback."
    digest = content_hash(text)
    values = {
        "publish_mode": "manual_review",
        "candidate_text": text,
        "supplied_content_hash": digest,
        "approved_content_hash": digest,
        "explicit_confirmation": True,
        "write_enabled": True,
        "global_kill_switch": False,
        "require_human_review": True,
        "account_write_enabled": True,
        "account_status": "active",
        "has_user_token": True,
        "granted_scopes": ["tweet.read", "tweet.write"],
        "target_post_exists": True,
        "api_reply_eligible": True,
        "already_replied": False,
        "user_opted_out": False,
        "within_write_budget": True,
        "risk_level": "low",
        "factual_confidence": 0.92,
        "sensitive_topic": False,
        "automation_limits_configured": True,
        "hourly_write_allowed": True,
        "per_user_frequency_allowed": True,
        "min_reply_interval_allowed": True,
        "interaction_intent": "support_question",
        "interaction_intent_label": "售后查询",
        "intent_evidence_present": True,
        "allowed_auto_reply_intents": ["support_question"],
    }
    values.update(overrides)
    return PublicationContext(**values)


def test_manual_publish_requires_explicit_confirmation_and_exact_hash():
    denied = evaluate_publication_policy(
        _publishable_context(explicit_confirmation=False, supplied_content_hash="0" * 64)
    )
    assert denied.allowed is False
    failed = {item["rule"] for item in denied.rule_results if not item["passed"]}
    assert "explicit_confirmation" in failed
    assert "content_hash_matches_request" in failed

    allowed = evaluate_publication_policy(_publishable_context())
    assert allowed.allowed is True
    assert allowed.decision == "allowed"


def test_kill_switch_and_write_disabled_block_publication():
    result = evaluate_publication_policy(
        _publishable_context(global_kill_switch=True, write_enabled=False)
    )
    assert result.allowed is False
    failed = {item["rule"] for item in result.rule_results if not item["passed"]}
    assert {"kill_switch_off", "global_write_enabled"} <= failed


def test_duplicate_and_operational_scope_controls_block_publication():
    result = evaluate_publication_policy(
        _publishable_context(
            duplicate_score=0.85,
            duplicate_threshold=0.8,
            operational_scope_allowed=False,
            operational_scope_reason="paused keyword matched",
        )
    )
    failed = {item["rule"] for item in result.rule_results if not item["passed"]}
    assert "duplicate_threshold" in failed
    assert "operational_scope_controls" in failed
    assert "paused keyword matched" in result.blocked_reason


def test_auto_reply_requires_written_approval_and_user_initiated_evidence():
    denied = evaluate_publication_policy(
        _publishable_context(
            publish_mode="auto_reply",
            approved_content_hash="",
            explicit_confirmation=False,
            x_written_approval=False,
            auto_reply_enabled=True,
            global_auto_reply_enabled=True,
            automated_label_enabled=True,
            user_initiated=False,
            explicitly_addresses_account=True,
        )
    )
    failed = {item["rule"] for item in denied.rule_results if not item["passed"]}
    assert "x_written_approval" in failed
    assert "user_initiated" in failed

    allowed = evaluate_publication_policy(
        _publishable_context(
            publish_mode="auto_reply",
            approved_content_hash="",
            explicit_confirmation=False,
            x_written_approval=True,
            auto_reply_enabled=True,
            global_auto_reply_enabled=True,
            automated_label_enabled=True,
            user_initiated=True,
            explicitly_addresses_account=True,
        )
    )
    assert allowed.allowed is True


def test_auto_reply_blocks_when_limits_or_intent_whitelist_are_missing():
    denied = evaluate_publication_policy(
        _publishable_context(
            publish_mode="auto_reply",
            approved_content_hash="",
            explicit_confirmation=False,
            x_written_approval=True,
            auto_reply_enabled=True,
            global_auto_reply_enabled=True,
            automated_label_enabled=True,
            user_initiated=True,
            explicitly_addresses_account=True,
            automation_limits_configured=False,
            interaction_intent="unknown",
            interaction_intent_label="未知意图",
            intent_evidence_present=False,
            allowed_auto_reply_intents=[],
        )
    )
    failed = {item["rule"] for item in denied.rule_results if not item["passed"]}
    assert "automation_limits_configured" in failed
    assert "intent_evidence_present" in failed
    assert "intent_whitelist" in failed


def test_interaction_intent_classifier_returns_auditable_evidence():
    classified = classify_interaction_intent("@brandbot How does the pricing work?")
    assert classified["code"] == "product_information"
    assert classified["confidence"] > 0
    assert classified["matched_evidence"]
    assert classified["classifier_version"] == "rules-v1"

    unknown = classify_interaction_intent("hello there")
    assert unknown["code"] == "unknown"


def test_invisible_obfuscation_cannot_bypass_content_hash():
    clean = "hello world"
    obfuscated = "hel\u200blo\u200c \u200dworld\ufeff"
    assert canonical_text(clean) == canonical_text(obfuscated)
    assert content_hash(clean) == content_hash(obfuscated)


def test_topic_query_treats_operator_text_as_literal_data():
    query = build_topic_query('AI") OR from:someone (')
    assert query.startswith('"')
    assert '\\"' in query
    assert query.endswith('-is:retweet')
    assert len(query) <= 512


def test_reply_eligibility_is_computed_from_mention_or_quote_evidence():
    mention = compute_reply_eligibility(
        {"entities": {"mentions": [{"username": "BrandBot"}]}},
        account_username="@brandbot",
    )
    assert mention["eligible"] is True
    assert mention["explicit_mention"] is True

    quote = compute_reply_eligibility(
        {"referenced_tweets": [{"type": "quoted", "id": "123"}]},
        account_username="brandbot",
        account_post_ids=["123"],
    )
    assert quote["eligible"] is True
    assert quote["quoted_account_post_ids"] == ["123"]

    unrelated = compute_reply_eligibility(
        {"entities": {"mentions": [{"username": "other"}]}},
        account_username="brandbot",
    )
    assert unrelated["eligible"] is False


def test_map_post_converts_rfc3339_to_epoch_milliseconds():
    mapped = map_post(
        {
            "id": "100",
            "author_id": "200",
            "text": "hello",
            "created_at": "2026-07-16T00:00:00.000Z",
            "conversation_id": "100",
        }
    )
    assert mapped["created_at_x"] == 1784160000000
    assert mapped["author_display_name"] == ""


async def test_reply_generator_has_deterministic_local_fallback():
    llm = OpenAICompatibleLLMClient(base_url="", api_key="", model="")
    result = await ReplyGenerator(llm).generate(
        target_post={"x_post_id": "1", "text": "Can you clarify this?", "lang": "en"},
    )
    assert result["fallback_used"] is True
    assert len(result["candidates"]) == 3
    assert all(candidate["content_hash"] for candidate in result["candidates"])
    assert all(len(candidate["text"]) <= 280 for candidate in result["candidates"])


def test_oauth_state_is_one_time_and_tokens_are_encrypted():
    store = OAuthStateStore(ttl_seconds=60)
    state, verifier = store.issue(owner_user_id="7", redirect_uri="https://example.test/callback")
    pending = store.consume(state)
    assert pending.owner_user_id == "7"
    assert pending.code_verifier == verifier
    try:
        store.consume(state)
        assert False, "state must be one-time"
    except ValueError:
        pass

    key = Fernet.generate_key().decode("ascii")
    encrypted = encrypt_token("secret-token", key)
    assert encrypted != "secret-token"
    assert decrypt_token(encrypted, key) == "secret-token"


def test_oauth_token_endpoint_accepts_base_url_with_or_without_v2(monkeypatch):
    from config import x_config

    monkeypatch.setattr(x_config, "X_API_BASE_URL", "https://api.x.com")
    assert _oauth_token_endpoint() == "https://api.x.com/2/oauth2/token"
    monkeypatch.setattr(x_config, "X_API_BASE_URL", "https://api.x.com/2/")
    assert _oauth_token_endpoint() == "https://api.x.com/2/oauth2/token"
