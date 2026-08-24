"""轨迹：写入、读取与 compare 并排 markdown。

目录布局：
- 单流程：traces/<实验名>/<run-id>/trace.jsonl
- matrix：  traces/<实验名>/combo-001/trace.jsonl 等（combo 递增序号）

每个 trace.jsonl 以 header 行开始（{event: run_start, experiment, provider,
input}），以 run_end 行结束（含配置哈希）；中间为 trace 行
{seq, ts, stage, cfg, obj_type, snapshot, meta}——每行 JSON 完整可独立解析。
"""

from __future__ import annotations

import json
import os
import secrets
import time

TRACES_ROOT_ENV = "RIG_TRACES_DIR"


def traces_root() -> str:
    return os.environ.get(TRACES_ROOT_ENV, "traces")


def new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


def run_dir(experiment: str, run_id: str) -> str:
    d = os.path.join(traces_root(), experiment, run_id)
    os.makedirs(d, exist_ok=True)
    return d


def combo_dir(experiment: str, combo_index: int) -> str:
    d = os.path.join(traces_root(), experiment, f"combo-{combo_index:03d}")
    os.makedirs(d, exist_ok=True)
    return d


def write_line(run_dir_path: str, entry: dict) -> None:
    with open(os.path.join(run_dir_path, "trace.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def write_run_start(run_dir_path: str, flow: dict) -> None:
    write_line(run_dir_path, {
        "event": "run_start",
        "experiment": flow.get("experiment"),
        "provider": flow.get("provider"),
        "input": flow.get("input"),
    })


def write_run_end(run_dir_path: str, flow: dict) -> None:
    from .config import config_hash

    write_line(run_dir_path, {
        "event": "run_end",
        "experiment": flow.get("experiment"),
        "config_hash": config_hash(flow),
    })


# ---------------------------------------------------------------- 读取

def load_trace_file(path: str) -> list[dict]:
    entries = []
    if not os.path.isfile(path):
        return entries
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def load_combo_traces(experiment: str, combo_index: str) -> list[dict]:
    path = os.path.join(traces_root(), experiment, combo_index, "trace.jsonl")
    return load_trace_file(path)


# ---------------------------------------------------------------- compare

def build_compare(experiment: str) -> str:
    """同输入多配置并排输出 markdown（先人工判读）。

    优先取 combo-* 目录（matrix 结果）；无则取最近一次 run-id（单流程）。
    """
    root = os.path.join(traces_root(), experiment)
    if not os.path.isdir(root):
        raise FileNotFoundError(f"实验 {experiment!r} 没有任何轨迹（{root}）")
    dirs = sorted(
        d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))
    )
    combos = [d for d in dirs if d.startswith("combo-")]
    if not combos:
        combos = dirs[-1:]  # 单流程：最近一次 run

    lines = [
        f"# 对比报告：{experiment}",
        "",
        f"> 数据来源：{len(combos)} 个组合，同输入多配置并排，人工判读",
        "",
    ]

    lines.append("## 总览（最终输出并排）")
    lines.append("")
    lines.append("| 组合 | 配置摘要 | 最终输出 |")
    lines.append("|---|---|---|")
    for ci in combos:
        entries = _step_entries(experiment, ci)
        summary = _combo_summary(entries)
        final_text = _final_text(entries).replace("|", "\\|").replace("\n", "<br>")
        lines.append(f"| {ci} | {summary} | {final_text} |")
    lines.append("")

    for ci in combos:
        entries = _step_entries(experiment, ci)
        lines.append(f"## 组合 {ci}")
        lines.append("")
        lines.append("| seq | stage | obj_type | 说明 |")
        lines.append("|---|---|---|---|")
        for e in entries:
            lines.append(f"| {e['seq']} | {e['stage']} | {e['obj_type']} | {_stage_note(e)} |")
        lines.append("")
        lines.append("### 轨迹")
        lines.append("")
        lines.append("```jsonl")
        for e in load_combo_traces(experiment, ci):
            lines.append(json.dumps(e, ensure_ascii=False))
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def _step_entries(experiment: str, combo_index: str) -> list[dict]:
    """过滤掉 run_start/run_end header 行，只留步骤 trace。"""
    return [e for e in load_combo_traces(experiment, combo_index) if "event" not in e]


def _combo_summary(entries: list[dict]) -> str:
    parts = []
    for e in entries:
        if e["stage"] == "config":
            snap = e["snapshot"]
            combo = snap.get("combo") or {}
            preset = snap.get("preset") or combo.get("preset")
            if preset:
                parts.append(f"preset={preset}")
            for k in ("temperature", "think"):
                if k in combo:
                    parts.append(f"{k}={_fmt_value(combo[k])}")
        if e["stage"] == "generate":
            meta = e["meta"]
            parts.append(f"model={meta.get('model')} t={meta.get('temperature')}")
    return "，".join(parts) if parts else "—"


def _fmt_value(v) -> str:
    if isinstance(v, dict):
        inner = " ".join(f"{k}={v[k]}" for k in sorted(v))
        return "{" + inner + "}"
    return str(v)


def _final_text(entries: list[dict]) -> str:
    text = None
    for e in entries:
        if e["obj_type"] == "text":
            text = e["snapshot"].get("text")
    return (text or "").strip()


def _stage_note(e: dict) -> str:
    stage = e["stage"]
    if stage == "config":
        return f"{e['snapshot'].get('experiment')} · {e['snapshot'].get('provider')}"
    if stage == "inject":
        return f"装配 {e['meta'].get('blocks', 0)} 块"
    if stage == "think":
        return f"mode={e['meta'].get('mode')} visible={e['meta'].get('visible')} rounds={e['meta'].get('rounds')}"
    if stage == "generate":
        return f"{e['meta'].get('model')} usage={e['meta'].get('usage', {}).get('total_tokens')}"
    if stage == "process":
        notes = [t["note"] for t in e["meta"].get("transforms", [])]
        return "；".join(notes)
    return ""


def write_compare(experiment: str) -> str:
    md = build_compare(experiment)
    out = os.path.join(traces_root(), experiment, "compare.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)
    return out
