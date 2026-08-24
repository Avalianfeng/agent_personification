"""流程引擎：steps 编排 + 阶段输入要求校验 + 全链轨迹组装。

steps 是数据，顺序由 flow 文件决定（可重排、可重复、可只写 stage 名）。
inject/think/generate 吃 messages；process 吃 text——
process 排在没有任何 assistant 消息的位置时，报错并点名步骤序号。
"""

from __future__ import annotations

import datetime

from . import stages
from .config import ConfigError, config_hash, config_ref
from .objects import Message, text_view

_DETERMINISTIC_EPOCH = datetime.datetime(2026, 1, 1, 0, 0, 0)


def run_flow(flow: dict) -> list[dict]:
    """逐 step 执行，返回全链 trace 条目（seq 0 为配置快照）。"""
    steps = flow["steps"]
    if not steps:
        raise ConfigError("flow 展开后 steps 为空，无法执行")
    provider = flow.get("provider", "mock")
    deterministic = provider == "mock"

    ctx = {
        "messages": [Message(role="user", content=flow["input"]["text"])],
        "flow": flow,
        "provider": provider,
        "config_ref": config_ref(flow),
        "base_dir": flow.get("_base_dir", "."),
    }

    entries: list[dict] = []
    entries.append(_config_snapshot(flow, ctx, deterministic))

    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict) or "stage" not in step:
            raise ConfigError(f"steps[{i - 1}] 必须是含 stage 字段的映射")
        stage = step["stage"]
        if stage not in stages.known_stages():
            raise ConfigError(
                f"步骤 {i}：未知阶段 {stage!r}（已知: {', '.join(stages.known_stages())}）"
            )
        # 阶段输入要求校验：process 吃 text，必须有 assistant 消息可加工
        if stages.stage_input_kind(stage) == "text" and text_view(ctx["messages"]) is None:
            raise ConfigError(
                f"步骤 {i}（stage={stage}）需要 text 视图——"
                f"process 必须排在至少一次 generate/think(visible) 之后，"
                f"当前消息列表最后一条不是 assistant"
            )
        cfg = {k: v for k, v in step.items() if k != "stage"}
        ctx, trace = stages.stage_transform(stage, ctx, cfg)
        entry = dict(trace)
        entry["seq"] = i
        entry["ts"] = _ts(i, deterministic)
        entry["cfg"] = cfg
        entry["config_ref"] = ctx["config_ref"]
        entries.append(entry)

    return entries


def _config_snapshot(flow: dict, ctx: dict, deterministic: bool) -> dict:
    return {
        "seq": 0,
        "ts": _ts(0, deterministic),
        "stage": "config",
        "config_ref": ctx["config_ref"],
        "obj_type": "config",
        "snapshot": {
            "experiment": flow.get("experiment"),
            "provider": flow.get("provider"),
            "preset": flow.get("preset_name") or flow.get("preset"),
            "input": flow.get("input"),
            "combo": flow.get("combo"),
            "steps": [
                {"stage": s.get("stage"), **{k: v for k, v in s.items() if k != "stage"}}
                for s in flow.get("steps", [])
            ],
            "config_hash": config_hash(flow),
        },
        "meta": {},
    }


def _ts(seq: int, deterministic: bool) -> str:
    if deterministic:
        # mock 下用确定性假时钟，保证两次运行轨迹逐字一致
        t = _DETERMINISTIC_EPOCH + datetime.timedelta(seconds=seq)
        return t.isoformat(timespec="milliseconds")
    return datetime.datetime.now().isoformat(timespec="milliseconds")
