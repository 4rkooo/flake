"""A structured comparison of two policy versions: what the Retro actually changed.

versions.diff() gives the flat "key: a -> b" lines the CLI prints; the demo wants the
same facts grouped the way the presentation table names them -- rules, permissions,
guardrails, context settings -- plus the evidence attached to the newer version.
"""

from flake.harness.versions import _flatten


def _meta(v: dict) -> dict:
    return {"id": v["_id"], "version": v.get("version"), "status": v.get("status"), "parent": v.get("parent"),
            "created_by": v.get("created_by"), "created_at": v.get("created_at")}


def _rows(a: dict, b: dict) -> list[dict]:
    fa, fb = _flatten(a), _flatten(b)
    return [{"key": k, "from": fa.get(k), "to": fb.get(k), "changed": fa.get(k) != fb.get(k)}
            for k in sorted(set(fa) | set(fb))]


def _rule_key(rule: dict) -> tuple:
    return (rule.get("type"), tuple(rule.get("people") or []), rule.get("day_type"), rule.get("amount"))


def diff_lines(a: dict, b: dict) -> list[str]:
    # same format as versions.diff, computed from the documents in hand
    fa, fb = _flatten(a["policy"]), _flatten(b["policy"])
    return [f"{key}: {fa.get(key, '-')} -> {fb.get(key, '-')}"
            for key in sorted(set(fa) | set(fb)) if fa.get(key) != fb.get(key)]


def compare_policies(a: dict, b: dict) -> dict:
    pa, pb = a["policy"], b["policy"]
    keys_a = {_rule_key(r): r for r in pa.get("rules", [])}
    keys_b = {_rule_key(r): r for r in pb.get("rules", [])}
    return {
        "from": _meta(a),
        "to": _meta(b),
        "rules": {
            "added": [keys_b[k] for k in keys_b if k not in keys_a],
            "removed": [keys_a[k] for k in keys_a if k not in keys_b],
            "kept": [keys_b[k] for k in keys_b if k in keys_a],
        },
        "permissions": _rows(pa.get("tool_permissions", {}), pb.get("tool_permissions", {})),
        "guardrails": _rows(pa.get("guardrails", {}), pb.get("guardrails", {})),
        "context": _rows(pa.get("context_policy", {}), pb.get("context_policy", {})),
        "model": {"from": pa.get("model"), "to": pb.get("model"), "changed": pa.get("model") != pb.get("model")},
        "diff": diff_lines(a, b),
        "rationale": b.get("rationale"),
        "backtest": b.get("backtest"),
        "constitution_notes": b.get("constitution_notes") or [],
        "canary": b.get("canary"),
    }
