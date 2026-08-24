"""对象模型：messages 是主对象，text 是「最后一条 assistant 消息」的视图。

- inject / think / generate 吃 messages（list[Message]），互插无需转换胶水；
- process 吃 text 视图，处理结果写回最后一条 assistant 消息，主对象仍自洽。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Message:
    role: str
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


def text_view(messages: list[Message]) -> str | None:
    """text 视图：最后一条 assistant 消息的内容；没有则返回 None。"""
    for m in reversed(messages):
        if m.role == "assistant":
            return m.content
    return None


def set_text_view(messages: list[Message], text: str) -> None:
    """把 text 视图写回最后一条 assistant 消息（process 专用）。"""
    for m in reversed(messages):
        if m.role == "assistant":
            m.content = text
            return
    raise ValueError("没有 assistant 消息可承载 text 视图")


def snapshots(messages: list[Message]) -> list[dict]:
    return [m.to_dict() for m in messages]
