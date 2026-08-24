"""生成变换：messages → text。

调 provider.complete，把结果作为 assistant 消息追加
（text 视图随之更新）。
"""

from __future__ import annotations

from .objects import Message, snapshots
from .provider import complete
from .stages import register


@register("generate", "messages")
def generate(ctx: dict, cfg: dict) -> tuple[dict, dict]:
    gen_cfg = {"provider": ctx.get("provider", "mock")}
    for k in ("model", "temperature", "max_tokens", "base_url", "api_key_env", "seed"):
        if k in cfg:
            gen_cfg[k] = cfg[k]

    text, meta = complete(ctx["messages"], gen_cfg)
    ctx["messages"].append(Message(role="assistant", content=text))

    return ctx, {
        "stage": "generate",
        "obj_type": "text",
        "snapshot": {"text": text, "messages": snapshots(ctx["messages"])},
        "meta": {
            "provider": meta["provider"],
            "model": meta["model"],
            "temperature": cfg.get("temperature"),
            "max_tokens": cfg.get("max_tokens"),
            "usage": meta["usage"],
            "elapsed_ms": meta["elapsed_ms"],
        },
    }
