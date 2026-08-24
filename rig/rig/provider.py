"""LLM 生成原语：唯一的非纯变换点。

- `mock`：确定性替身——不回显输入，用模板化输出 + 假 usage/假耗时
  （保证同配置两次运行轨迹完全一致，用于全离线验证）；
- `openai_compat`：requests 直连 `{base_url}/chat/completions`
  （Ollama 默认 http://localhost:11434/v1；Gemini 用其 OpenAI 兼容端点），
  响应全文与 usage 完整落轨。
"""

from __future__ import annotations

import hashlib
import json
import os
import time

import requests

from .objects import Message

DEFAULT_BASE_URL = "http://localhost:11434/v1"


class ProviderError(RuntimeError):
    pass


def complete(messages: list[Message], gen_cfg: dict) -> tuple[str, dict]:
    """messages -> (text, meta)；meta 含 provider/model/usage/duration_ms。"""
    provider = gen_cfg.get("provider", "mock")
    if provider == "mock":
        return _mock_complete(messages, gen_cfg)
    if provider == "openai_compat":
        return _openai_compat_complete(messages, gen_cfg)
    raise ProviderError(f"未知 provider: {provider!r}")


# ---------------------------------------------------------------- mock

def _mock_complete(messages: list[Message], gen_cfg: dict) -> tuple[str, dict]:
    """确定性替身：输出由（模型名、温度桶、输入指纹、草稿数）唯一决定，零随机。"""
    model = gen_cfg.get("model", "mock-model")
    temperature = float(gen_cfg.get("temperature", 0.7))
    if temperature < 0.34:
        tone = "冷静"
    elif temperature < 0.67:
        tone = "平稳"
    else:
        tone = "积极"

    user_text = next(
        (m.content for m in reversed(messages) if m.role == "user"), ""
    )
    drafts = [m.content for m in messages if m.role == "assistant"]

    sig_input = "|".join(f"{m.role}:{m.content}" for m in messages)
    sig = hashlib.sha256(sig_input.encode("utf-8")).hexdigest()[:8]

    reply = f"[mock·{model}·{tone}] 输入指纹 {sig}"
    if drafts:
        reply += f"，草稿 {len(drafts)} 篇"
    snippet = user_text.strip()[:40]
    if len(user_text.strip()) > 40:
        snippet += "…"
    reply += f"。回应：{snippet}——先歇一歇，压力会小一点。"

    # 假 usage / 假耗时：仅由文本长度决定，保证两次运行完全一致
    prompt_tokens = sum(len(m.content) for m in messages) // 3 + 10
    completion_tokens = len(reply) // 2 + 5
    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    duration_ms = 60 + (len(reply) % 40)
    return reply, {
        "provider": "mock",
        "model": model,
        "usage": usage,
        "elapsed_ms": duration_ms,
    }


# ---------------------------------------------------------------- openai_compat

def _openai_compat_complete(messages: list[Message], gen_cfg: dict) -> tuple[str, dict]:
    model = gen_cfg.get("model") or os.environ.get("RIG_MODEL")
    if not model:
        raise ProviderError(
            "openai_compat 需要 model（steps 里配置或 RIG_MODEL 环境变量）"
        )
    base_url = (
        gen_cfg.get("base_url")
        or os.environ.get("RIG_BASE_URL")
        or DEFAULT_BASE_URL
    ).rstrip("/")
    api_key = os.environ.get(gen_cfg.get("api_key_env") or "OPENAI_API_KEY")
    if not api_key:
        api_key = os.environ.get("RIG_API_KEY")
    url = f"{base_url}/chat/completions"
    payload = {"model": model, "messages": [m.to_dict() for m in messages]}
    for k in ("temperature", "max_tokens", "top_p", "seed"):
        if k in gen_cfg:
            payload[k] = gen_cfg[k]
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    t0 = time.monotonic()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
    except requests.RequestException as e:
        raise ProviderError(f"请求 {url} 失败: {e}") from e
    duration_ms = int((time.monotonic() - t0) * 1000)
    if resp.status_code != 200:
        raise ProviderError(f"{url} 返回 {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ProviderError(
            f"{url} 响应缺少 choices[0].message.content: "
            f"{json.dumps(data, ensure_ascii=False)[:500]}"
        ) from e
    usage = data.get("usage") or {}
    return text, {
        "provider": "openai_compat",
        "model": model,
        "usage": usage,
        "elapsed_ms": duration_ms,
    }
