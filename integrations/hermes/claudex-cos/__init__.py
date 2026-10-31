"""Hermes plugin: chief-of-staff / PA layer that routes work through claudex-route and claudex-loop."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

_DOCTRINE_PATH = Path(__file__).parent / "doctrine.md"
_MAX_CONTEXT_CHARS = 32_000
_DELEGATION_WAIT_SECONDS = 330

# Order matters: "never" is checked first, then "ask"; anything else is "act".
_NEVER_PATTERNS = [
    r"\b(store|save|write|keep)\b.{0,40}\b(password|credential|api[- ]?key|token)s?\b.{0,40}\b(plain ?text|unencrypted)\b",
    r"\b(fake|fabricate|invent|make up)\b.{0,40}\b(data|source|citation|result|evidence|figure)s?\b",
    r"\bmark\b.{0,20}\b(done|complete)\b.{0,30}\bwithout\b",
]
_ASK_PATTERNS = [
    r"\b(send|publish|tweet|dm)\b",
    r"\b(reply|forward|email|message|post)\b",
    r"\b(invite|schedule|book|reschedule|cancel)\b.{0,40}\b(meeting|call|event|appointment|attendee)s?\b",
    r"\b(delete|remove|erase|wipe|purge|drop|trash)\b",
    r"\b(pay|payment|transfer|wire|refund|purchase|buy|order|invoice|subscribe)\b",
    r"\b(sign|agree|accept|commit|contract|legal|tax|nda)\b",
    r"\b(cron|schedule[d]?\s+(task|routine|job)|routine|recurring)\b",
    r"\b(overwrite|outside)\b.{0,30}\b(folder|director(y|ies)|repo)\b",
]
_BUILD_PATTERNS = [
    r"\b(implement|build|refactor|migrate|integrate|architect|redesign)\b",
    r"\b(feature|service|pipeline|api|endpoint|schema|plugin)\b",
]
_REVIEW_PATTERNS = [
    r"\b(plan|proposal|strategy|decision|approach|design|trade-?off|roadmap)\b",
    r"\b(second opinion|sanity check|review|challenge|stress[- ]test)\b",
]
# Drafting is internal work: it only becomes "ask" when the task also says to send or publish.
_DRAFT_PATTERNS = [r"\b(draft|prepare|outline|summari[sz]e|proofread|compose)\b"]
_SEND_PATTERNS = [r"\b(send|publish|tweet|dm|submit)\b"]
_TRIVIAL_PATTERNS = [r"\b(typo|rename|one[- ]liner|tweak|small fix|comment)\b"]


def _matches(patterns: list[str], text: str) -> list[str]:
    return [p for p in patterns if re.search(p, text, re.I)]


def triage(task: str) -> dict[str, Any]:
    """Classify a task by autonomy tier and recommended route. Pure and deterministic."""
    text = (task or "").strip()
    never = _matches(_NEVER_PATTERNS, text)
    ask = _matches(_ASK_PATTERNS, text)
    if _matches(_DRAFT_PATTERNS, text) and not _matches(_SEND_PATTERNS, text):
        ask = [p for p in ask if not re.search(r"reply|forward|email|message|post", p)]
    if never:
        tier, reason = "never", "Request matches a prohibited category; refuse and say why."
    elif ask:
        tier, reason = "ask", "External, irreversible or money-related; prepare it and wait for an explicit yes."
    else:
        tier, reason = "act", "Reversible and internal; proceed without asking."

    build = bool(_matches(_BUILD_PATTERNS, text)) and not _matches(_TRIVIAL_PATTERNS, text)
    review = bool(_matches(_REVIEW_PATTERNS, text))
    if tier == "never":
        route, route_reason = "decline", "Do not route a prohibited request."
    elif build:
        route, route_reason = "claudex-loop", "Non-trivial build: plan review, build, independent inspection."
    elif review:
        route, route_reason = "claudex-route", "Consequential plan or decision: get an independent second opinion."
    else:
        route, route_reason = "self", "Small and clear: handle directly; handoff overhead is not worth it."
    return {
        "tier": tier,
        "tier_reason": reason,
        "route": route,
        "route_reason": route_reason,
        "requires_approval": tier == "ask",
    }


def _doctrine() -> str:
    """Packaged doctrine, with an optional per-user override under HERMES_HOME."""
    override = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes") / "claudex-cos" / "doctrine.md"
    try:
        if override.is_file():
            return override.read_text(encoding="utf-8")
    except OSError:
        pass
    return _DOCTRINE_PATH.read_text(encoding="utf-8")


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _context(task_info: dict[str, Any]) -> str:
    text = (
        f"{_doctrine()}\n\n## Triage for this task\n"
        f"Autonomy tier: {task_info['tier']} ({task_info['tier_reason']})\n"
        f"Recommended route: {task_info['route']} ({task_info['route_reason']})\n"
    )
    return text[:_MAX_CONTEXT_CHARS]


BRIEF_DESCRIPTION = "Return the chief-of-staff / PA operating doctrine: voice, autonomy tiers and routing rules."
BRIEF_SCHEMA = {
    "name": "claudex_cos_brief",
    "description": BRIEF_DESCRIPTION,
    "parameters": {"type": "object", "properties": {}, "required": []},
}
TRIAGE_DESCRIPTION = (
    "Classify a task before acting: autonomy tier (act / ask / never) and whether to handle it "
    "directly, get a second opinion via claudex-route, or run claudex-loop. Has no side effects."
)
TRIAGE_SCHEMA = {
    "name": "claudex_cos_triage",
    "description": TRIAGE_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {"task": {"type": "string", "description": "The task as the principal stated it."}},
        "required": ["task"],
    },
}
DELEGATE_DESCRIPTION = (
    "Delegate a task to a Hermes subagent that operates under the chief-of-staff doctrine. "
    "Tasks in the 'ask' tier need approved=true after the principal has said yes; 'never' tasks are refused."
)
DELEGATE_SCHEMA = {
    "name": "claudex_cos_delegate",
    "description": DELEGATE_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "Concrete task for the subagent."},
            "approved": {"type": "boolean", "description": "True only after the principal explicitly approved this action."},
        },
        "required": ["task"],
    },
}


def register(ctx):
    def brief(args: dict[str, Any], **kwargs) -> str:
        del args, kwargs
        return _json({"success": True, "doctrine": _doctrine()})

    def triage_tool(args: dict[str, Any], **kwargs) -> str:
        del kwargs
        task = str(args.get("task", "")).strip()
        if not task:
            return _json({"success": False, "error": "task is required"})
        return _json({"success": True, **triage(task)})

    def delegate(args: dict[str, Any], **kwargs) -> str:
        del kwargs
        task = str(args.get("task", "")).strip()
        if not task:
            return _json({"success": False, "error": "task is required"})
        info = triage(task)
        if info["tier"] == "never":
            return _json({"success": False, "delegated": False, "error": info["tier_reason"], **info})
        if info["tier"] == "ask" and args.get("approved") is not True:
            return _json({
                "success": False,
                "delegated": False,
                "error": "explicit approval from the principal is required before this action",
                **info,
            })
        try:
            from agent.subagent_lifecycle import SubagentLaunchRequest

            lifecycle = ctx.subagent_lifecycle
            handle = lifecycle.launch(SubagentLaunchRequest(goal=task, context=_context(info)))
            terminal = lifecycle.wait(handle, timeout_seconds=_DELEGATION_WAIT_SECONDS)
            if terminal.timed_out:
                return _json({"success": True, "delegated": True, "pending": True,
                              "subagent_id": handle.subagent_id, **info})
            result = lifecycle.result(handle)
            if not result.ready or result.terminal_state.value != "SUCCEEDED":
                detail = result.error_message or result.error_classification or result.terminal_state.value
                return _json({"success": False, "delegated": False,
                              "error": f"subagent delegation failed: {detail}", **info})
            return _json({"success": True, "delegated": True, "subagent_id": handle.subagent_id,
                          "result": result.summary, **info})
        except Exception as exc:  # depends on the Hermes runtime
            return _json({"success": False, "delegated": False,
                          "error": f"subagent delegation unavailable: {exc}", **info})

    for schema, handler, desc in (
        (BRIEF_SCHEMA, brief, BRIEF_DESCRIPTION),
        (TRIAGE_SCHEMA, triage_tool, TRIAGE_DESCRIPTION),
        (DELEGATE_SCHEMA, delegate, DELEGATE_DESCRIPTION),
    ):
        ctx.register_tool(name=schema["name"], toolset="claudex_cos", schema=schema,
                          handler=handler, description=desc)
