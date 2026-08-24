"""预设：命名步骤模板（展开成默认 steps，显式项覆盖）。

- 步骤模板（type: steps）：含 steps 列表，flow 未显式写 steps 时展开为默认编排；
- 注入块模板（type: block）：被 inject 阶段以 ref 引用（如 persona-lite.yaml）。
"""

from __future__ import annotations

import copy
import os

import yaml

from .config import ConfigError

_PKG_PRESETS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "presets"))


def preset_dirs() -> list[str]:
    dirs = [os.path.join(os.getcwd(), "presets"), _PKG_PRESETS_DIR]
    seen = []
    for d in dirs:
        if os.path.isdir(d) and d not in seen:
            seen.append(d)
    return seen


def find_preset(name: str) -> str:
    for d in preset_dirs():
        for ext in (".yaml", ".yml"):
            p = os.path.join(d, name + ext)
            if os.path.isfile(p):
                return p
    raise ConfigError(f"预设不存在: {name!r}（查找于 {', '.join(preset_dirs())}）")


def load_preset(name: str) -> dict:
    path = find_preset(name)
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ConfigError(f"预设文件结构错误（{path}）：根必须是映射")
    data["_path"] = path
    return data


def list_presets() -> list[dict]:
    out = []
    for d in preset_dirs():
        for fn in sorted(os.listdir(d)):
            if not fn.endswith((".yaml", ".yml")):
                continue
            p = os.path.join(d, fn)
            try:
                with open(p, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            except yaml.YAMLError:
                continue
            if not isinstance(data, dict):
                continue
            name = data.get("name") or os.path.splitext(fn)[0]
            out.append({
                "name": name,
                "type": data.get("type", "steps"),
                "description": data.get("description", ""),
                "path": p,
            })
    # 去重（同一名字只留第一个），按名字排序
    seen = set()
    uniq = []
    for p in out:
        if p["name"] not in seen:
            seen.add(p["name"])
            uniq.append(p)
    return uniq


def expand_preset(cfg: dict) -> dict:
    """flow 未显式写 steps 时，用 preset 模板展开默认 steps（深拷贝防串扰）。"""
    if cfg.get("steps") is None:
        name = cfg.get("preset")
        if not name:
            raise ConfigError("flow 配置必须提供 steps 或 preset（展开后仍为空）")
        preset = load_preset(name)
        if preset.get("type", "steps") != "steps":
            raise ConfigError(
                f"预设 {name!r} 是注入块模板（type=block），不能展开为 steps——"
                f"请在 inject.blocks 里以 ref 引用它"
            )
        if not isinstance(preset.get("steps"), list) or not preset["steps"]:
            raise ConfigError(f"预设 {name!r} 的 steps 为空，无法展开")
        cfg["steps"] = copy.deepcopy(preset["steps"])
    if cfg.get("preset"):
        cfg["preset_name"] = cfg["preset"]
    return cfg
