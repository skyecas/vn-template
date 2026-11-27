"""Artifact: IR -> story.json v2 (design 2.1). Serialization only."""

from __future__ import annotations

from typing import Any

from .ir import PRESENTATION_KEYS, NodeIR, VariantIR

# ---------------------------------------------------------------------------
# emit story.json v2 (design 2.1): serialization only, no decisions here
# ---------------------------------------------------------------------------


def node_title(node: NodeIR) -> str | None:
    """frontmatter title, else the first text line (design 1.2)"""
    if node.title:
        return node.title
    for variant in node.variants:
        for line in variant.lines:
            text = "".join(tok["v"] for tok in line if tok["t"] == "lit").strip()
            if text:
                return text
    return None


def emit_variant(variant: VariantIR) -> dict[str, Any]:
    out: dict[str, Any] = {
        "lines": variant.lines,
        "choices": [
            {
                "label": choice.label,
                "to": choice.target,
                "once": choice.once,
                "chance": choice.chance,
                "fallback": choice.fallback,
                "call": choice.call,
                "return": choice.return_,
            }
            | ({"if": choice.cond} if choice.cond else {})
            | ({"effects": choice.effects} if choice.effects else {})
            for choice in variant.choices
        ],
    }
    if variant.effects:
        out["effects"] = variant.effects
    for attr in PRESENTATION_KEYS.values():
        if value := getattr(variant, attr):
            out[attr] = value
    return out


def generate_json(parts: dict[str, NodeIR]) -> dict[str, Any]:
    nodes: dict[str, Any] = {}
    for node_id, node in parts.items():
        entry: dict[str, Any] = {
            "start": node.is_start,
            "end": node.is_end,
            "revisit": node.revisit,
            "title": node_title(node),
            "chapter": node.chapter,
        }
        if node.next:
            entry["next"] = node.next
        if node.next_if:
            entry["nextIf"] = node.next_if
        entry["variants"] = [emit_variant(v) for v in node.variants]
        nodes[node_id] = entry

    ends = [node_id for node_id, node in parts.items() if node.is_end]
    return {
        "version": 2,
        "nodes": nodes,
        "ends": ends,
        "meta": {"endings": [{"id": i, "title": node_title(parts[i])} for i in ends]},
    }
