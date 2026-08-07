"""In-session conversation memory for intent follow-ups.

Uses an in-process store keyed by session_id (cleared on process restart;
no page-reload persistence required). LangGraph MemorySaver checkpoints
graph runs per thread_id=session_id.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger
from app.engines.intent.entity_grounding import (
    is_measure_column,
    match_column,
    normalize_column_name,
)

logger = get_logger(__name__)

_MAX_TURNS = 8
_MAX_SESSIONS = 200
_SESSION_TTL_SEC = 60 * 60 * 6  # 6 hours

_VIZ_HINTS = (
    "chart",
    "graph",
    "plot",
    "visualize",
    "visualise",
    "histogram",
    "bar chart",
    "line chart",
    "pie chart",
    "scatter",
)

_FOLLOWUP_HINTS = (
    "what about",
    "how about",
    "and for",
    "same for",
    "same but",
    "also for",
    "also show",
    "now for",
    "instead",
    "for that",
    "those",
    "them",
    "again",
    "continue",
    "same metric",
    "same thing",
)

_HISTORY_HINTS = (
    "what did i ask",
    "what did i asked",
    "what was my last",
    "what was my previous",
    "previous question",
    "previous query",
    "last question",
    "last query",
    "what did i say",
    "remind me what i asked",
    "conversation history",
    "earlier question",
)

# Exact short closers (punctuation stripped). Keep ambiguous words exact-only.
_CLOSING_EXACT = {
    "bye",
    "bai",
    "byee",
    "bye bye",
    "goodbye",
    "good bye",
    "goodnight",
    "good night",
    "cya",
    "see ya",
    "see you",
    "see you later",
    "later",
    "ttyl",
    "peace",
    "cheers",
    "thanks",
    "thank you",
    "thanks a lot",
    "thank you so much",
    "thx",
    "ty",
    "thanku",
    "fine",
    "ok",
    "okay",
    "k",
    "kk",
    "cool",
    "great",
    "alright",
    "all right",
    "done",
    "stop",
    "end",
    "thats all",
    "that's all",
    "that is all",
    "nothing else",
    "no thanks",
    "no thank you",
    "nope",
    "nm",
    "never mind",
    "nevermind",
    "im good",
    "i'm good",
    "im fine",
    "i'm fine",
    "all good",
    "im done",
    "i'm done",
    "we're done",
    "we are done",
    "thats it",
    "that's it",
    "got it",
    "perfect",
    "nice",
}

_CLOSING_PREFIXES = (
    "bye ",
    "bai ",
    "goodbye ",
    "good bye ",
    "thanks ",
    "thank you ",
    "ok thanks",
    "okay thanks",
    "thats all",
    "that's all",
    "i'm done",
    "im done",
    "see you",
)

_STOPWORDS = {
    "a",
    "an",
    "the",
    "of",
    "by",
    "for",
    "to",
    "in",
    "on",
    "and",
    "or",
    "vs",
    "versus",
    "with",
    "from",
    "about",
    "how",
    "what",
    "which",
    "show",
    "me",
    "please",
    "now",
    "same",
    "also",
    "instead",
    "again",
    "my",
    "i",
    "did",
    "ask",
    "asked",
    "previously",
    "previous",
    "last",
    "question",
    "query",
    "chart",
    "graph",
    "plot",
    "bar",
    "line",
    "pie",
    "scatter",
    "total",
    "sum",
    "average",
    "avg",
    "highest",
    "lowest",
    "most",
    "least",
    "has",
    "have",
    "had",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "do",
    "does",
    "did",
    "can",
    "could",
    "would",
    "should",
    "will",
    "get",
    "got",
    "give",
    "find",
    "tell",
    "need",
    "want",
    "like",
    "just",
    "only",
    "very",
    "much",
    "many",
    "more",
    "than",
    "then",
    "this",
    "that",
    "these",
    "those",
    "into",
    "over",
    "under",
    "per",
    "each",
    "all",
    "any",
    "some",
    "every",
    "where",
    "when",
    "who",
    "whom",
    "whose",
    "why",
    "there",
    "here",
    "across",
    "among",
    "between",
}



@dataclass
class SessionMemory:
    session_id: str
    turns: list[dict[str, Any]] = field(default_factory=list)
    last_intent: str | None = None
    last_engine: str | None = None
    last_entities: dict[str, Any] = field(default_factory=dict)
    last_query: str | None = None
    dataset_id: str | None = None
    updated_at: float = field(default_factory=time.time)

    def snapshot(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_count": len(self.turns),
            "last_intent": self.last_intent,
            "last_engine": self.last_engine,
            "last_entities": dict(self.last_entities or {}),
            "last_query": self.last_query,
            "recent_turns": list(self.turns[-4:]),
            "dataset_id": self.dataset_id,
        }


class SessionMemoryStore:
    """Thread-safe in-memory session store (process lifetime)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionMemory] = {}

    def get(self, session_id: str | None) -> SessionMemory | None:
        if not session_id:
            return None
        with self._lock:
            self._purge_locked()
            memory = self._sessions.get(session_id)
            if memory is None:
                return None
            memory.updated_at = time.time()
            return memory

    def get_or_create(self, session_id: str) -> SessionMemory:
        with self._lock:
            self._purge_locked()
            memory = self._sessions.get(session_id)
            if memory is None:
                memory = SessionMemory(session_id=session_id)
                self._sessions[session_id] = memory
            memory.updated_at = time.time()
            return memory

    def remember_turn(
        self,
        session_id: str,
        *,
        query: str,
        intent: str,
        engine: str,
        entities: dict[str, Any],
        dataset_id: str | None,
    ) -> SessionMemory:
        memory = self.get_or_create(session_id)
        with self._lock:
            memory.turns.append(
                {
                    "query": query,
                    "intent": intent,
                    "engine": engine,
                    "entities": dict(entities or {}),
                }
            )
            memory.turns = memory.turns[-_MAX_TURNS:]
            # Only persist actionable topics — not unknown/none.
            if intent not in {"unknown", None} and engine not in {"none", None}:
                memory.last_intent = intent
                memory.last_engine = engine
                memory.last_entities = dict(entities or {})
                memory.last_query = query
            if dataset_id:
                memory.dataset_id = dataset_id
            memory.updated_at = time.time()
            return memory

    def reset_topic(self, session_id: str | None) -> SessionMemory | None:
        """Clear active topic so the next ask does not resume the old engine."""
        if not session_id:
            return None
        with self._lock:
            memory = self._sessions.get(session_id)
            if memory is None:
                return None
            memory.last_intent = None
            memory.last_engine = None
            memory.last_entities = {}
            memory.last_query = None
            memory.updated_at = time.time()
            return memory

    def clear(self, session_id: str | None = None) -> None:
        with self._lock:
            if session_id:
                self._sessions.pop(session_id, None)
            else:
                self._sessions.clear()

    def _purge_locked(self) -> None:
        now = time.time()
        expired = [
            key
            for key, value in self._sessions.items()
            if now - value.updated_at > _SESSION_TTL_SEC
        ]
        for key in expired:
            self._sessions.pop(key, None)
        if len(self._sessions) <= _MAX_SESSIONS:
            return
        ordered = sorted(self._sessions.items(), key=lambda item: item[1].updated_at)
        overflow = len(self._sessions) - _MAX_SESSIONS
        for key, _ in ordered[:overflow]:
            self._sessions.pop(key, None)


_STORE = SessionMemoryStore()


def get_session_memory_store() -> SessionMemoryStore:
    return _STORE


def looks_like_visualization(query: str) -> bool:
    text = (query or "").lower()
    return any(token in text for token in _VIZ_HINTS)


def looks_like_history_question(query: str) -> bool:
    text = (query or "").strip().lower()
    if not text:
        return False
    if any(hint in text for hint in _HISTORY_HINTS):
        return True
    return bool(
        re.search(
            r"\b(what|which).*(did i|was my).*(ask|asked|question|query|say)\b",
            text,
        )
    )


def looks_like_conversation_end(query: str) -> bool:
    """Detect short closings like bye / bai / fine / thanks / ok."""
    text = _normalize_closing(query)
    if not text:
        return False
    if looks_like_visualization(text) or looks_like_history_question(text):
        return False
    if text in _CLOSING_EXACT:
        return True
    words = text.split()
    if len(words) <= 4 and any(text.startswith(prefix) for prefix in _CLOSING_PREFIXES):
        return True
    return False


def build_closing_reply(query: str) -> str:
    text = _normalize_closing(query)
    if any(
        token in text
        for token in ("thank", "thx", "ty", "cheers")
    ):
        return "You're welcome. Ask anytime if you want another KPI, chart, or forecast."
    if any(
        token in text
        for token in ("bye", "bai", "goodbye", "cya", "see you", "later", "ttyl", "peace")
    ):
        return "Bye! I'm here whenever you want to explore the data again."
    return "Sounds good. I'm ready when you want to dig into the data again."


def build_history_reply(memory: SessionMemory | None) -> str:
    if memory is None or not memory.turns:
        return "No earlier questions in this chat yet."

    actionable = [
        turn
        for turn in memory.turns
        if turn.get("intent") not in {"unknown", None}
        and turn.get("engine") not in {"none", None}
    ]
    source = actionable or list(memory.turns)
    lines = []
    for index, turn in enumerate(source[-5:], start=1):
        lines.append(f"{index}. {turn.get('query')}")

    last = memory.last_query or (source[-1].get("query") if source else None)
    head = "You previously asked:"
    if last:
        head = f"Most recent topic: “{last}”. Earlier asks:"
    return f"{head}\n" + "\n".join(lines)


def looks_like_followup(
    query: str,
    memory: SessionMemory | None,
    columns: list[dict[str, Any]] | None = None,
) -> bool:
    """True only when the query clearly continues the prior topic."""
    if memory is None or not memory.last_intent:
        return False
    text = (query or "").strip().lower()
    if not text:
        return False
    if looks_like_history_question(text):
        return False
    if looks_like_conversation_end(text):
        return False
    if looks_like_visualization(text):
        # Explicit chart asks are fresh visualization tasks (entities may still inherit).
        return False

    if any(hint in text for hint in _FOLLOWUP_HINTS):
        return True

    # Short queries resume only when they reference schema/prior entities —
    # not arbitrary gibberish like "dsd".
    words = re.findall(r"[a-z0-9]+", text)
    if len(words) > 8:
        return False
    return bool(_schema_signal_tokens(query, columns, memory))


def merge_entities(
    current: dict[str, Any] | None,
    remembered: dict[str, Any] | None,
    *,
    inherit_filters: bool = True,
) -> dict[str, Any]:
    """Fill missing entity slots from memory; never blank out new values."""
    current = dict(current or {})
    remembered = dict(remembered or {})
    merged = dict(remembered)

    for key, value in current.items():
        if value in (None, "", [], {}):
            continue
        if key == "grounding":
            continue
        if isinstance(value, list):
            if value:
                merged[key] = value
            continue
        merged[key] = value

    if not current.get("chart_type") and remembered.get("chart_type"):
        merged["chart_type"] = remembered.get("chart_type")

    # Fresh ranking/aggregation questions must not keep stale viz/topic filters.
    if not inherit_filters:
        if current.get("filters"):
            merged["filters"] = list(current.get("filters") or [])
        else:
            merged["filters"] = []
    return merged


def enrich_entities_from_followup(
    query: str,
    entities: dict[str, Any],
    columns: list[dict[str, Any]] | None,
    memory: SessionMemory | None,
) -> dict[str, Any]:
    """Update metrics/dimensions/filters from follow-up tokens (profit, technology, 2014)."""
    enriched = dict(entities or {})
    tokens = _content_tokens(query, columns, memory)
    if not tokens and not re.search(r"\[[^\]]+\]", query or ""):
        return enriched

    lookup = _column_lookup(columns)
    role_by_name = {
        str(col.get("name")): str(col.get("role_hint") or "categorical")
        for col in (columns or [])
        if isinstance(col, dict) and col.get("name")
    }

    metrics = list(enriched.get("metrics") or [])
    dimensions = list(enriched.get("dimensions") or [])
    filters = list(enriched.get("filters") or [])
    changed = False
    allow_value_filters = _allows_value_filters(query)

    # Bracketed values like [technology] are almost always filter values.
    for raw in re.findall(r"\[([^\]]+)\]", query or ""):
        value = raw.strip()
        if not value:
            continue
        field = _preferred_filter_field(dimensions, memory, role_by_name)
        if field and not _has_filter(filters, field, value):
            filters.append({"field": field, "op": "eq", "value": _title_value(value)})
            changed = True

    for token in tokens:
        # Year-like tokens → datetime filter when available.
        if re.fullmatch(r"(19|20)\d{2}", token):
            if not allow_value_filters:
                continue
            date_field = next(
                (
                    name
                    for name, role in role_by_name.items()
                    if role == "datetime"
                    or "date" in name.lower()
                    or "year" in name.lower()
                ),
                None,
            )
            if date_field and not _has_filter(filters, date_field, token):
                filters.append({"field": date_field, "op": "eq", "value": token})
                changed = True
            continue

        matched = match_column(token, lookup) if lookup else None
        if matched:
            role = role_by_name.get(matched, "categorical")
            # Object-dtype KPI columns (sales/profit) must stay metrics, never dimensions.
            if is_measure_column(matched, role):
                if metrics != [matched]:
                    metrics = [matched]
                    changed = True
                # Keep measures out of the dimension slot.
                if matched in dimensions:
                    dimensions = [item for item in dimensions if item != matched]
                    changed = True
            elif role in {"categorical", "boolean", "datetime", "unknown"}:
                if matched in metrics:
                    continue
                if dimensions != [matched]:
                    dimensions = [matched]
                    changed = True
            continue

        # Free-text values only for soft follow-ups ("what about technology").
        # Full questions like "which country has lowest sales" must not invent
        # filters such as Region=Has from leftover words.
        if not allow_value_filters:
            continue
        field = _preferred_filter_field(dimensions, memory, role_by_name)
        if field and not _has_filter(filters, field, token):
            filters.append({"field": field, "op": "eq", "value": _title_value(token)})
            changed = True

    # Final guard: never group by the same column used as the metric.
    if metrics and dimensions:
        metric_set = set(metrics)
        cleaned_dims = [item for item in dimensions if item not in metric_set]
        if cleaned_dims != dimensions:
            dimensions = cleaned_dims
            changed = True

    if not changed:
        return enriched

    enriched["metrics"] = metrics
    enriched["dimensions"] = dimensions
    enriched["filters"] = filters
    return enriched


def _allows_value_filters(query: str) -> bool:
    text = (query or "").strip().lower()
    if re.search(r"\[[^\]]+\]", text):
        return True
    return any(hint in text for hint in _FOLLOWUP_HINTS)


def _is_fresh_analysis_question(query: str, entities: dict[str, Any] | None) -> bool:
    """True when the user asked a complete new ranking/KPI question."""
    entities = entities or {}
    if _allows_value_filters(query):
        return False
    if not entities.get("metrics") or not entities.get("dimensions"):
        return False
    text = (query or "").strip().lower()
    return bool(
        re.search(
            r"\b(which|what|who|show|find|list|top|bottom|lowest|highest|maximum|minimum)\b",
            text,
        )
    )


def apply_conversation_memory(
    *,
    query: str,
    intent: str,
    target_engine: str,
    confidence: float,
    entities: dict[str, Any],
    rationale: str | None,
    provider: str,
    memory: SessionMemory | None,
    columns: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Continue prior topic for follow-ups without hijacking explicit visualization."""
    base = {
        "intent": intent,
        "target_engine": target_engine,
        "confidence": confidence,
        "entities": entities,
        "rationale": rationale,
        "provider": provider,
        "memory_applied": False,
        "reply": None,
        "end_conversation": False,
    }

    # Closings always win: short polite reply + clear active topic.
    if looks_like_conversation_end(query):
        return {
            "intent": "unknown",
            "target_engine": "none",
            "confidence": 0.99,
            "entities": {},
            "rationale": "Conversation closing",
            "provider": f"{provider}+memory_close",
            "memory_applied": True,
            "reply": build_closing_reply(query),
            "end_conversation": True,
        }

    if memory is None:
        return base

    # Meta: answer from conversation turns, do not re-run last engine.
    if looks_like_history_question(query):
        return {
            "intent": "unknown",
            "target_engine": "none",
            "confidence": 0.95,
            "entities": {},
            "rationale": "Answered from session conversation memory",
            "provider": f"{provider}+memory_recall",
            "memory_applied": True,
            "reply": build_history_reply(memory),
            "end_conversation": False,
        }

    if not memory.last_intent:
        return base

    followup = looks_like_followup(query, memory, columns)
    explicit_viz = looks_like_visualization(query)

    # Hard protection: explicit visualization requests keep their own intent.
    if explicit_viz and intent == "visualization":
        filled = merge_entities(entities, memory.last_entities)
        filled = enrich_entities_from_followup(query, filled, columns, memory)
        changed = filled != entities
        return {
            "intent": "visualization",
            "target_engine": "visualization",
            "confidence": max(confidence, 0.7),
            "entities": filled,
            "rationale": (
                f"{rationale or ''} | filled chart entities from session memory"
                if changed
                else rationale
            ),
            "provider": f"{provider}+memory_entities" if changed else provider,
            "memory_applied": changed,
            "reply": None,
            "end_conversation": False,
        }

    if not followup:
        return base

    inherit_filters = not _is_fresh_analysis_question(query, entities)

    # Follow-up with unknown / low confidence → resume last actionable topic.
    if intent in {"unknown"} or confidence < 0.55 or target_engine == "none":
        filled = merge_entities(
            entities,
            memory.last_entities,
            inherit_filters=inherit_filters,
        )
        filled = enrich_entities_from_followup(query, filled, columns, memory)
        logger.info(
            "Memory resumed topic intent=%s engine=%s session=%s",
            memory.last_intent,
            memory.last_engine,
            memory.session_id,
        )
        return {
            "intent": memory.last_intent,
            "target_engine": memory.last_engine or "none",
            "confidence": max(confidence, 0.66),
            "entities": filled,
            "rationale": (
                f"{rationale or 'Follow-up'} | continued from prior "
                f"{memory.last_intent} turn"
            ).strip(" |"),
            "provider": f"{provider}+memory",
            "memory_applied": True,
            "reply": None,
            "end_conversation": False,
        }

    # Follow-up with a confident new intent: keep intent, inherit missing entities.
    filled = merge_entities(
        entities,
        memory.last_entities,
        inherit_filters=inherit_filters,
    )
    filled = enrich_entities_from_followup(query, filled, columns, memory)
    if intent != "visualization":
        filled.pop("chart_type", None)
        if entities.get("chart_type"):
            filled["chart_type"] = entities["chart_type"]

    return {
        "intent": intent,
        "target_engine": target_engine,
        "confidence": confidence,
        "entities": filled,
        "rationale": (
            f"{rationale or ''} | inherited entities from session memory"
        ).strip(" |"),
        "provider": f"{provider}+memory_entities",
        "memory_applied": True,
        "reply": None,
        "end_conversation": False,
    }


def _normalize_closing(query: str) -> str:
    text = (query or "").strip().lower()
    text = re.sub(r"[!?.,~]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _column_lookup(columns: list[dict[str, Any]] | None) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for col in columns or []:
        if not isinstance(col, dict):
            continue
        name = str(col.get("name") or "").strip()
        if name:
            lookup[normalize_column_name(name)] = name
    return lookup


def _raw_content_tokens(query: str) -> list[str]:
    text = (query or "").strip().lower()
    for hint in sorted(_FOLLOWUP_HINTS, key=len, reverse=True):
        if text.startswith(hint):
            text = text[len(hint) :].strip(" :,-")
            break

    bracketed = [
        item.strip().lower() for item in re.findall(r"\[([^\]]+)\]", query or "")
    ]
    words = bracketed + re.findall(r"[a-z0-9]+", text)
    cleaned: list[str] = []
    for word in words:
        if word in _STOPWORDS or len(word) < 2:
            continue
        if word not in cleaned:
            cleaned.append(word)
    return cleaned


def _schema_signal_tokens(
    query: str,
    columns: list[dict[str, Any]] | None,
    memory: SessionMemory | None,
) -> list[str]:
    """Tokens that prove the query references the dataset/prior topic."""
    lookup = _column_lookup(columns)
    prior_names = set()
    if memory and memory.last_entities:
        for key in ("metrics", "dimensions"):
            for item in memory.last_entities.get(key) or []:
                prior_names.add(normalize_column_name(str(item)))

    useful: list[str] = []
    for token in _raw_content_tokens(query):
        if re.fullmatch(r"(19|20)\d{2}", token):
            useful.append(token)
            continue
        if lookup and match_column(token, lookup):
            useful.append(token)
            continue
        if normalize_column_name(token) in prior_names:
            useful.append(token)
    return useful


def _content_tokens(
    query: str,
    columns: list[dict[str, Any]] | None,
    memory: SessionMemory | None,
) -> list[str]:
    """Tokens used to enrich a confirmed follow-up (includes filter values)."""
    lookup = _column_lookup(columns)
    has_prior_dim = bool((memory.last_entities or {}).get("dimensions")) if memory else False
    useful: list[str] = []
    for token in _raw_content_tokens(query):
        if re.fullmatch(r"(19|20)\d{2}", token):
            useful.append(token)
            continue
        if lookup and match_column(token, lookup):
            useful.append(token)
            continue
        if has_prior_dim:
            useful.append(token)
    return useful


def _preferred_filter_field(
    dimensions: list[str],
    memory: SessionMemory | None,
    role_by_name: dict[str, str],
) -> str | None:
    for name in dimensions:
        if role_by_name.get(name, "categorical") != "numeric":
            return name
    prior = list((memory.last_entities or {}).get("dimensions") or []) if memory else []
    for name in prior:
        if role_by_name.get(name, "categorical") != "numeric":
            return name
    # Fall back to any categorical schema column with common names.
    for preferred in ("Category", "Segment", "Region", "Sub-Category", "Ship Mode"):
        if preferred in role_by_name:
            return preferred
    for name, role in role_by_name.items():
        if role == "categorical":
            return name
    return None


def _has_filter(filters: list[Any], field: str, value: str) -> bool:
    needle = str(value).strip().lower()
    for item in filters:
        if not isinstance(item, dict):
            continue
        item_field = item.get("field") or item.get("column") or item.get("name")
        if str(item_field) != field:
            continue
        if str(item.get("value", "")).strip().lower() == needle:
            return True
    return False


def _title_value(value: str) -> str:
    text = str(value).strip()
    if not text:
        return text
    if text.isupper() or text.islower():
        return text.title()
    return text
