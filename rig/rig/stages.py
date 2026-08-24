"""阶段注册表：stage 名 → 变换实现 + 输入要求（engine 据此校验排列）。

统一签名：`stage_transform(stage, ctx, cfg) -> (new_ctx, trace)`
- ctx：engine 维护的上下文（messages 主对象、flow 配置、config_ref 等）
- cfg：step 配置（去掉 stage 键后的剩余字段）
- 输入要求：inject/think/generate 吃 messages；process 吃 text
"""

from __future__ import annotations

from .config import ConfigError

_REGISTRY: dict[str, dict] = {}


def register(stage: str, input_kind: str):
    """装饰器：把阶段实现挂到注册表。input_kind: 'messages' | 'text'"""
    def deco(fn):
        _REGISTRY[stage] = {"fn": fn, "input": input_kind}
        return fn
    return deco


def known_stages() -> list[str]:
    return sorted(_REGISTRY)


def stage_input_kind(stage: str) -> str:
    return _REGISTRY[stage]["input"]


def stage_transform(stage: str, ctx: dict, cfg: dict) -> tuple[dict, dict]:
    entry = _REGISTRY.get(stage)
    if entry is None:
        raise ConfigError(f"未知阶段: {stage!r}（已知: {', '.join(known_stages())}）")
    return entry["fn"](ctx, cfg)


# 导入阶段实现模块，触发 @register 装饰器完成注册（放在 register 定义之后，避免循环导入）
from . import stages_generate, stages_inject, stages_process, stages_think  # noqa: E402,F401
