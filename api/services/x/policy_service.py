"""Publication policy engine.

The policy engine is deliberately separate from generation and X API calls. A
caller cannot publish merely because a draft exists or a review row says
"approved"; all live controls and evidence are evaluated again.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from config import x_config


POLICY_VERSION = "x-policy-v1"

_SENSITIVE_PATTERNS: Dict[str, Sequence[re.Pattern[str]]] = {
    "politics": (
        re.compile(r"\b(election|politic(?:s|al)?|president|parliament|vote)\b", re.I),
        re.compile(r"(选举|政治|总统|议会|投票)"),
    ),
    "war_or_disaster": (
        re.compile(r"\b(war|invasion|airstrike|earthquake|casualt(?:y|ies)|disaster)\b", re.I),
        re.compile(r"(战争|入侵|空袭|地震|伤亡|灾害)"),
    ),
    "medical": (
        re.compile(r"\b(diagnos(?:is|e)|prescription|dosage|treatment|suicide|self[- ]?harm)\b", re.I),
        re.compile(r"(诊断|处方|剂量|治疗|自杀|自残)"),
    ),
    "financial_or_legal": (
        re.compile(r"\b(invest(?:ment|ing)?|stock tip|legal advice|lawsuit)\b", re.I),
        re.compile(r"(投资建议|股票推荐|法律建议|诉讼)"),
    ),
    "hate_or_adult": (
        re.compile(r"\b(hate speech|racial slur|porn(?:ography)?|sexual content)\b", re.I),
        re.compile(r"(仇恨言论|种族歧视|色情|成人内容)"),
    ),
}
_OPT_OUT_PATTERNS = (
    re.compile(r"\b(stop|unsubscribe|do not reply|don't reply|leave me alone|opt[ -]?out)\b", re.I),
    re.compile(r"(停止回复|不要再回复|别再回复|取消订阅|退出互动|别联系我)"),
)
_PROMPT_INJECTION_PATTERNS = (
    re.compile(r"ignore (all |the )?(previous|above) instructions", re.I),
    re.compile(r"(system prompt|developer message|reveal.*secret|print.*api.?key)", re.I),
    re.compile(r"(忽略.*指令|系统提示词|开发者消息|泄露.*密钥)", re.I),
)


def canonical_text(value: str) -> str:
    normalized = value or ""
    for invisible in ("\u200b", "\u200c", "\u200d", "\ufeff"):
        normalized = normalized.replace(invisible, "")
    return " ".join(normalized.strip().split())


def content_hash(value: str) -> str:
    return hashlib.sha256(canonical_text(value).encode("utf-8")).hexdigest()


def detect_opt_out(text: str) -> Dict[str, Any]:
    for pattern in _OPT_OUT_PATTERNS:
        match = pattern.search(text or "")
        if match:
            return {"opted_out": True, "detected_phrase": match.group(0)}
    return {"opted_out": False, "detected_phrase": ""}


def classify_interaction_intent(text: str) -> Dict[str, Any]:
    """Return a conservative, auditable intent classification.

    Unknown text is deliberately not considered eligible for automatic reply.
    The classifier records matched evidence instead of relying on an opaque
    model-only label.
    """

    normalized = canonical_text(text).casefold()
    opt_out = detect_opt_out(normalized)
    if opt_out["opted_out"]:
        return {
            "code": "opt_out",
            "label": "退出互动",
            "confidence": 1.0,
            "matched_evidence": [opt_out["detected_phrase"]],
            "classifier_version": "rules-v1",
        }
    rules = [
        (
            "complaint",
            "问题反馈",
            ("broken", "not working", "problem", "issue", "bug", "complaint", "不能用", "无法使用", "坏了", "故障", "投诉"),
        ),
        (
            "product_information",
            "产品说明",
            ("feature", "spec", "pricing", "price", "how does", "product", "功能", "规格", "价格", "产品", "怎么用"),
        ),
        (
            "support_question",
            "售后查询",
            ("help", "support", "customer service", "assist", "帮助", "客服", "售后", "如何处理"),
        ),
        (
            "feedback",
            "一般反馈",
            ("feedback", "suggestion", "recommend", "建议", "反馈", "推荐"),
        ),
    ]
    for code, label, keywords in rules:
        matches = [keyword for keyword in keywords if keyword in normalized]
        if matches:
            return {
                "code": code,
                "label": label,
                "confidence": 0.85,
                "matched_evidence": matches[:5],
                "classifier_version": "rules-v1",
            }
    if "?" in normalized or "？" in normalized:
        return {
            "code": "support_question",
            "label": "售后查询",
            "confidence": 0.65,
            "matched_evidence": ["question_mark"],
            "classifier_version": "rules-v1",
        }
    return {
        "code": "unknown",
        "label": "未知意图",
        "confidence": 0.0,
        "matched_evidence": [],
        "classifier_version": "rules-v1",
    }


def scan_content_risk(text: str) -> Dict[str, Any]:
    categories = [
        category
        for category, patterns in _SENSITIVE_PATTERNS.items()
        if any(pattern.search(text or "") for pattern in patterns)
    ]
    injection = any(pattern.search(text or "") for pattern in _PROMPT_INJECTION_PATTERNS)
    if categories:
        level = "high"
    elif injection:
        level = "medium"
    else:
        level = "low"
    return {
        "risk_level": level,
        "sensitive_topic": bool(categories),
        "categories": categories,
        "prompt_injection_signal": injection,
    }


def character_ngram_similarity(left: str, right: str, n: int = 3) -> float:
    def grams(value: str) -> set[str]:
        normalized = canonical_text(value).casefold()
        if len(normalized) <= n:
            return {normalized} if normalized else set()
        return {normalized[index : index + n] for index in range(len(normalized) - n + 1)}

    left_grams, right_grams = grams(left), grams(right)
    if not left_grams and not right_grams:
        return 1.0
    if not left_grams or not right_grams:
        return 0.0
    return len(left_grams & right_grams) / len(left_grams | right_grams)


def max_duplicate_score(text: str, historical_texts: Iterable[str]) -> float:
    return max((character_ngram_similarity(text, item) for item in historical_texts), default=0.0)


@dataclass
class PublicationContext:
    publish_mode: str = "manual_review"
    candidate_text: str = ""
    supplied_content_hash: str = ""
    approved_content_hash: str = ""
    explicit_confirmation: bool = False
    write_enabled: bool = False
    global_kill_switch: bool = True
    require_human_review: bool = True
    account_write_enabled: bool = False
    account_status: str = "disabled"
    has_user_token: bool = False
    granted_scopes: Sequence[str] = field(default_factory=list)
    target_post_exists: bool = False
    api_reply_eligible: bool = False
    already_replied: bool = False
    user_opted_out: bool = False
    within_write_budget: bool = False
    risk_level: str = "unknown"
    factual_confidence: float = 0.0
    sensitive_topic: bool = False
    x_written_approval: bool = False
    auto_reply_enabled: bool = False
    global_auto_reply_enabled: bool = False
    automated_label_enabled: bool = False
    user_initiated: bool = False
    explicitly_addresses_account: bool = False
    automation_limits_configured: bool = False
    hourly_write_allowed: bool = False
    per_user_frequency_allowed: bool = False
    min_reply_interval_allowed: bool = False
    duplicate_score: float = 0.0
    duplicate_threshold: float = 0.92
    operational_scope_allowed: bool = True
    operational_scope_reason: str = ""
    interaction_intent: str = ""
    interaction_intent_label: str = ""
    intent_evidence_present: bool = False
    allowed_auto_reply_intents: Sequence[str] = field(default_factory=list)
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class PolicyEvaluation:
    decision: str
    allowed: bool
    blocked_reason: str
    rule_results: List[Dict[str, Any]]
    input_content_hash: str
    policy_version: str = POLICY_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _rule(results: List[Dict[str, Any]], name: str, passed: bool, detail: str) -> None:
    results.append({"rule": name, "passed": bool(passed), "detail": detail})


def evaluate_publication_policy(context: PublicationContext) -> PolicyEvaluation:
    results: List[Dict[str, Any]] = []
    actual_hash = content_hash(context.candidate_text)
    scopes = set(_parse_scopes(context.granted_scopes))

    checks = [
        ("kill_switch_off", not context.global_kill_switch, "global Kill Switch must be off"),
        ("global_write_enabled", context.write_enabled, "global write control must be enabled"),
        ("account_write_enabled", context.account_write_enabled, "account write control must be enabled"),
        ("account_active", context.account_status == "active", "account must be active"),
        ("user_token_present", context.has_user_token, "user-context access token is required"),
        ("tweet_write_scope", "tweet.write" in scopes, "OAuth scope tweet.write is required"),
        ("target_exists", context.target_post_exists, "target Post must still exist"),
        ("api_reply_eligible", context.api_reply_eligible, "target must satisfy X reply eligibility"),
        ("not_opted_out", not context.user_opted_out, "opted-out users cannot be contacted"),
        ("not_already_replied", not context.already_replied, "an interaction can be replied to only once"),
        ("within_write_budget", context.within_write_budget, "daily write budget must be available"),
        ("content_hash_matches_request", bool(actual_hash) and actual_hash == context.supplied_content_hash, "request hash must match final text"),
        (
            "duplicate_threshold",
            context.duplicate_score < context.duplicate_threshold,
            "candidate exceeds the configured duplicate-text threshold",
        ),
        (
            "operational_scope_controls",
            context.operational_scope_allowed,
            context.operational_scope_reason or "target is paused or classified as a configured high-risk topic",
        ),
    ]
    for name, passed, detail in checks:
        _rule(results, name, passed, detail)

    if context.publish_mode == "auto_reply":
        allowed_intents = {
            canonical_text(value).casefold()
            for value in context.allowed_auto_reply_intents
            if canonical_text(value)
        }
        observed_intents = {
            canonical_text(context.interaction_intent).casefold(),
            canonical_text(context.interaction_intent_label).casefold(),
        }
        intent_allowed = bool(allowed_intents & observed_intents)
        auto_checks = [
            ("x_written_approval", context.x_written_approval, "written X approval is mandatory for AI auto reply"),
            ("account_auto_reply_enabled", context.auto_reply_enabled, "account auto-reply switch must be enabled"),
            ("global_auto_reply_enabled", context.global_auto_reply_enabled, "global auto-reply switch must be enabled"),
            ("automated_label_enabled", context.automated_label_enabled, "automated account disclosure must be enabled"),
            ("user_initiated", context.user_initiated, "automatic replies require a user-initiated interaction"),
            ("explicit_address", context.explicitly_addresses_account, "the interaction must explicitly address the account"),
            ("low_risk", context.risk_level == "low", "only low-risk content may be auto-published"),
            ("factual_confidence", context.factual_confidence >= 0.85, "auto reply requires factual confidence >= 0.85"),
            ("not_sensitive", not context.sensitive_topic, "sensitive topics cannot be auto-published"),
            (
                "automation_limits_configured",
                context.automation_limits_configured,
                "hourly, per-user, and minimum-interval controls must be configured",
            ),
            ("hourly_write_limit", context.hourly_write_allowed, "hourly write limit has been reached"),
            (
                "per_user_frequency_limit",
                context.per_user_frequency_allowed,
                "per-user interaction limit has been reached",
            ),
            (
                "minimum_reply_interval",
                context.min_reply_interval_allowed,
                "minimum reply interval has not elapsed",
            ),
            (
                "intent_evidence_present",
                context.intent_evidence_present and context.interaction_intent != "unknown",
                "automatic reply requires auditable, non-unknown intent evidence",
            ),
            (
                "intent_whitelist",
                bool(allowed_intents) and intent_allowed,
                "interaction intent is not in the configured automatic-reply whitelist",
            ),
        ]
        for name, passed, detail in auto_checks:
            _rule(results, name, passed, detail)
    else:
        manual_checks = [
            ("explicit_confirmation", context.explicit_confirmation, "manual publish requires an explicit confirmation"),
            (
                "content_hash_matches_approval",
                bool(actual_hash) and actual_hash == context.approved_content_hash,
                "approval is bound to the exact final text",
            ),
            (
                "human_review_completed",
                not context.require_human_review or bool(context.approved_content_hash),
                "human review must be completed",
            ),
            ("risk_not_blocked", context.risk_level != "blocked", "blocked content cannot be published"),
        ]
        for name, passed, detail in manual_checks:
            _rule(results, name, passed, detail)

    failed = [item for item in results if not item["passed"]]
    if not failed:
        return PolicyEvaluation("allowed", True, "", results, actual_hash)
    budget_only = all(item["rule"] == "within_write_budget" for item in failed)
    decision = "deferred" if budget_only else "blocked"
    return PolicyEvaluation(
        decision,
        False,
        "; ".join(item["detail"] for item in failed),
        results,
        actual_hash,
    )


def default_controls() -> Dict[str, bool]:
    """Return security defaults from config, retaining safe fallbacks."""

    return {
        "read_enabled": bool(getattr(x_config, "X_READ_ENABLED", True)),
        "write_enabled": bool(getattr(x_config, "X_WRITE_ENABLED", False)),
        "auto_reply_enabled": bool(getattr(x_config, "X_AUTO_REPLY_ENABLED", False)),
        "global_kill_switch": bool(getattr(x_config, "X_GLOBAL_KILL_SWITCH", True)),
        "require_human_review": bool(getattr(x_config, "X_REQUIRE_HUMAN_REVIEW", True)),
    }


def _parse_scopes(scopes: Sequence[str] | str) -> List[str]:
    if isinstance(scopes, str):
        try:
            decoded = json.loads(scopes)
            if isinstance(decoded, list):
                return [str(item) for item in decoded]
        except (TypeError, ValueError):
            return scopes.replace(",", " ").split()
    return [str(item) for item in scopes]
