from __future__ import annotations

import hashlib
import json
import pathlib
from datetime import datetime
from typing import Any, Dict, List


def _stable_bucket(path: pathlib.Path) -> int:
    raw = str(path).encode("utf-8", errors="ignore")
    digest = hashlib.md5(raw).hexdigest()
    return int(digest[:8], 16) % 100


def _read_json(path: pathlib.Path) -> Dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def collect_rollout_item(
    output_path: pathlib.Path,
    rollout_percent: int,
    adaptive_master_enabled: bool,
) -> Dict[str, Any]:
    log_dir = output_path.parent / "log"
    base = output_path.stem
    guard_path = log_dir / f"{base}.adaptive_guard.json"
    shadow_path = log_dir / f"{base}.adaptive_shadow.json"
    decisions_path = log_dir / f"{base}.master_decisions.json"

    guard = _read_json(guard_path) or {}
    shadow = _read_json(shadow_path) or {}
    decisions = _read_json(decisions_path) or {}

    bucket = _stable_bucket(output_path)
    in_canary = bucket < max(0, min(100, int(rollout_percent)))
    guard_ok = bool(guard.get("overall_ok", False))
    apply_ready = bool((shadow.get("summary") or {}).get("apply_ready", False))
    recommended_mode = str(guard.get("recommended_mode", "shadow_only") or "shadow_only")

    # Fase 8: aún estamos en rollout seguro, decide "enable_apply" pero no aplica audio.
    enable_apply = bool(adaptive_master_enabled and in_canary and guard_ok and apply_ready and recommended_mode == "apply_candidate")

    return {
        "file": output_path.name,
        "output_path": str(output_path),
        "bucket": bucket,
        "in_canary": in_canary,
        "guard_ok": guard_ok,
        "apply_ready": apply_ready,
        "recommended_mode": recommended_mode,
        "enable_apply": enable_apply,
        "sections": len(decisions.get("section_decisions", [])) if isinstance(decisions.get("section_decisions"), list) else 0,
        "guard_path": str(guard_path),
        "shadow_path": str(shadow_path),
        "decisions_path": str(decisions_path),
    }


def build_rollout_report(
    items: List[Dict[str, Any]],
    rollout_percent: int,
    adaptive_master_enabled: bool,
) -> Dict[str, Any]:
    total = len(items)
    canary = sum(1 for i in items if i.get("in_canary"))
    guard_ok = sum(1 for i in items if i.get("guard_ok"))
    apply_ready = sum(1 for i in items if i.get("apply_ready"))
    enable_apply = sum(1 for i in items if i.get("enable_apply"))

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "rollout_percent": int(rollout_percent),
            "adaptive_master_enabled": bool(adaptive_master_enabled),
        },
        "summary": {
            "total_files": total,
            "canary_files": canary,
            "guard_ok_files": guard_ok,
            "apply_ready_files": apply_ready,
            "enable_apply_files": enable_apply,
            "guard_ok_rate": round((guard_ok / total) if total else 0.0, 4),
            "apply_ready_rate": round((apply_ready / total) if total else 0.0, 4),
        },
        "items": items,
    }


def write_rollout_report(
    report_dir: pathlib.Path,
    report: Dict[str, Any],
) -> Dict[str, pathlib.Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = report_dir / f"batch_rollout_{timestamp}.json"
    md_path = report_dir / f"batch_rollout_{timestamp}.md"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    config = report.get("config", {}) if isinstance(report.get("config"), dict) else {}
    lines = [
        "# Batch Rollout Report",
        "",
        f"- Rollout percent: {config.get('rollout_percent', 0)}%",
        f"- Adaptive master enabled: {config.get('adaptive_master_enabled', False)}",
        f"- Total files: {summary.get('total_files', 0)}",
        f"- Canary files: {summary.get('canary_files', 0)}",
        f"- Guard OK: {summary.get('guard_ok_files', 0)} ({summary.get('guard_ok_rate', 0):.2%})",
        f"- Apply ready: {summary.get('apply_ready_files', 0)} ({summary.get('apply_ready_rate', 0):.2%})",
        f"- Enable apply: {summary.get('enable_apply_files', 0)}",
        "",
        f"JSON: `{json_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json_path": json_path, "md_path": md_path}

