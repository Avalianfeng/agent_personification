"""思考变换：none（直通）/ cot（单轮思考）/ multi（多轮草稿→修订）。

- none：原样返回，不产生任何消息；
- cot：调 provider 生成一轮思考消息，visible 决定是否留在最终消息列表
  （visible=false 时思考不出现在消息里，但轨迹完整记录）；
- multi：rounds 轮草稿→修订循环——每轮草稿作为 assistant 消息追加，
  轮间附「修订指令」system 消息再生成一轮。
"""

from __future__ import annotations

from .config import ConfigError
from .objects import Message, snapshots
from .provider import complete
from .stages import register


def _gen_cfg(ctx: dict, cfg: dict) -> dict:
    g = {"provider": ctx.get("provider", "mock")}
    for k in ("model", "temperature", "max_tokens", "base_url", "api_key_env", "seed"):
        if k in cfg:
            g[k] = cfg[k]
    return g


@register("think", "messages")
def think(ctx: dict, cfg: dict) -> tuple[dict, dict]:
    mode = cfg.get("mode", "none")
    msgs = ctx["messages"]
    gen_cfg = _gen_cfg(ctx, cfg)
    thoughts: list[str] = []
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    duration_ms = 0
    model = gen_cfg.get("model", "mock-model")

    if mode == "none":
        pass
    elif mode == "cot":
        text, meta = complete(msgs, gen_cfg)
        thoughts.append(text)
        _add_usage(usage_total, meta["usage"])
        duration_ms += int(meta.get("elapsed_ms", 0))
        model = meta["model"]
        if cfg.get("visible", False):
            msgs.append(Message(role="assistant", content=text))
    elif mode == "multi":
        rounds = int(cfg.get("rounds", 2))
        for r in range(rounds):
            text, meta = complete(msgs, gen_cfg)
            thoughts.append(text)
            _add_usage(usage_total, meta["usage"])
            duration_ms += int(meta.get("elapsed_ms", 0))
            model = meta["model"]
            msgs.append(Message(role="assistant", content=text))
            if r < rounds - 1:
                msgs.append(
                    Message(role="system", content=f"请基于上一稿做第 {r + 2} 轮修订，只输出修订后的全文。")
                )
    else:
        raise ConfigError(f"think.mode 必须是 none/cot/multi 之一（当前: {mode!r}）")

    return ctx, {
        "stage": "think",
        "obj_type": "messages",
        "snapshot": {
            "messages": snapshots(msgs),
            "mode": mode,
            "thoughts": thoughts,
        },
        "meta": {
            "mode": mode,
            "rounds": int(cfg.get("rounds", 2)) if mode == "multi" else None,
            "visible": cfg.get("visible", False),
            "model": model,
            "usage": usage_total,
            "elapsed_ms": duration_ms,
        },
    }


def _add_usage(total: dict, usage: dict) -> None:
    for k in total:
        total[k] += int(usage.get(k, 0))
