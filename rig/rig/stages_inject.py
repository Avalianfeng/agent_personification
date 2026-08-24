"""注入变换：块装配（persona / summary / instruction）。

块以 system 消息追加到用户消息之前的「开头区域」，
顺序固定：persona → summary → instruction → 用户消息。
输入里带 context 时，自动作为最后一块（对话上下文）追加。
"""

from __future__ import annotations

from .config import ConfigError, load_ref_text, resolve_ref
from .objects import Message, snapshots
from .stages import register


@register("inject", "messages")
def inject(ctx: dict, cfg: dict) -> tuple[dict, dict]:
    msgs = ctx["messages"]
    base_dir = ctx.get("base_dir", ".")
    blocks = list(cfg.get("blocks") or [])
    context = (ctx["flow"].get("input") or {}).get("context")

    assembled: list[tuple[str, str]] = []
    block_notes: list[dict] = []
    for b in blocks:
        btype = b["type"]
        content = _block_content(b, base_dir)
        if btype == "persona":
            assembled.append(("system", f"人格设定：{content}"))
            block_notes.append({"type": "persona", "ref": b.get("ref"), "chars": len(content)})
        elif btype == "summary":
            assembled.append(("system", f"对话背景摘要：\n{content}"))
            block_notes.append({"type": "summary", "ref": b.get("ref"), "chars": len(content)})
        elif btype == "instruction":
            assembled.append(("system", f"指令：{content}"))
            block_notes.append({"type": "instruction", "ref": b.get("ref") or b.get("text"), "chars": len(content)})
    if context:
        assembled.append(("system", f"对话上下文：{context}"))
        block_notes.append({"type": "context", "inline": True, "chars": len(context)})

    # 插入到第一条 user 消息之前（保持 persona → summary → instruction → user 顺序）
    user_idx = next((i for i, m in enumerate(msgs) if m.role == "user"), 0)
    for offset, (role, content) in enumerate(assembled):
        msgs.insert(user_idx + offset, Message(role=role, content=content))

    return ctx, {
        "stage": "inject",
        "obj_type": "messages",
        "snapshot": {"messages": snapshots(msgs), "blocks": block_notes},
        "meta": {"blocks": len(assembled), "mode": "assemble"},
    }


def _block_content(b: dict, base_dir: str) -> str:
    if b.get("text") is not None:
        return str(b["text"])
    ref = b.get("ref")
    if not ref:
        raise ConfigError(f"inject 块缺失内容来源（text 或 ref）: {b}")
    path = resolve_ref(ref, base_dir)
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    if path.lower().endswith((".yaml", ".yml")):
        import yaml

        data = yaml.safe_load(raw)
        content = data.get("content") if isinstance(data, dict) else None
        if content is None:
            raise ConfigError(f"ref 文件必须是含 content 字段的 YAML（{ref}）")
        return str(content)
    return raw
