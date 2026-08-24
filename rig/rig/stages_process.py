"""加工变换：text 上的纯函数变换集，可组合。

内置：trim / clamp_length / filter
- trim：去首尾空白
- clamp_length：超长截断（max_chars，默认 200，截断补 …）
- filter：空内容 / 命中 forbidden 关键词时替换为占位文本

transform 两种写法：字符串短写（默认参数），或 {name: ..., 参数...} 映射。
"""

from __future__ import annotations

from .config import ConfigError
from .objects import snapshots, set_text_view, text_view
from .stages import register

TRANSFORMS: dict[str, callable] = {}


def transform(name: str):
    """装饰器：注册纯函数变换，签名 fn(text, args) -> (new_text, note)"""
    def deco(fn):
        TRANSFORMS[name] = fn
        return fn
    return deco


@transform("trim")
def _trim(text: str, args: dict) -> tuple[str, str]:
    out = text.strip()
    return out, f"去首尾空白 {len(text) - len(out)} 字符"


@transform("clamp_length")
def _clamp(text: str, args: dict) -> tuple[str, str]:
    max_chars = int(args.get("max_chars", 200))
    if len(text) <= max_chars:
        return text, f"长度 {len(text)} <= {max_chars}，未截断"
    return text[:max_chars] + "…", f"超长截断：{len(text)} → {max_chars}"


@transform("filter")
def _filter(text: str, args: dict) -> tuple[str, str]:
    forbidden = [str(w) for w in args.get("forbidden", [])]
    if not text.strip():
        return "[内容已被过滤：空内容]", "空内容已过滤"
    for w in forbidden:
        if w in text:
            return f"[内容已被过滤：命中关键词「{w}」]", f"命中关键词「{w}」已过滤"
    return text, f"通过 {len(forbidden)} 个关键词过滤"


def _parse_transform(t) -> tuple[str, dict]:
    if isinstance(t, str):
        return t, {}
    if isinstance(t, dict):
        name = t.get("name")
        return str(name), {k: v for k, v in t.items() if k != "name"}
    raise ConfigError(f"transforms 项必须是字符串或映射（当前: {t!r}）")


@register("process", "text")
def process(ctx: dict, cfg: dict) -> tuple[dict, dict]:
    transforms = cfg.get("transforms") or []
    text = text_view(ctx["messages"])
    applied: list[dict] = []
    for t in transforms:
        name, args = _parse_transform(t)
        if name not in TRANSFORMS:
            raise ConfigError(
                f"process 变换未知: {name!r}（已知: {', '.join(sorted(TRANSFORMS))}）"
            )
        text, note = TRANSFORMS[name](text, args)
        applied.append({"name": name, "args": args, "note": note})
    set_text_view(ctx["messages"], text)

    return ctx, {
        "stage": "process",
        "obj_type": "text",
        "snapshot": {"text": text, "messages": snapshots(ctx["messages"])},
        "meta": {"transforms": applied},
    }
