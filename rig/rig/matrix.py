"""组合生成：matrix 文件 → axes 候选集笛卡尔积 → flow 列表。

每个组合 = 一份完整 flow：
- preset 轴：展开成默认 steps（显式项覆盖）；
- think 轴：替换/插入 think 步骤（none 或 {mode: multi, rounds: n}）；
- temperature 轴：覆盖 generate 步骤的 temperature（无 generate 则追加）。

`--dry-run` 时只把组合 flow 写到 experiments/generated/，不执行。
"""

from __future__ import annotations

import copy
import itertools
import os

import yaml

from . import presets as presets_mod
from .config import ConfigError


def expand_matrix(cfg: dict, base_dir: str) -> list[dict]:
    axes = cfg["axes"]
    keys = list(axes)
    combos = list(itertools.product(*[axes[k] for k in keys]))
    if not combos:
        raise ConfigError("matrix.axes 笛卡尔积为空")

    flows = []
    for i, values in enumerate(combos, 1):
        combo = dict(zip(keys, values))
        flow = {
            "experiment": cfg["experiment"],
            "provider": cfg.get("provider", "mock"),
            "input": copy.deepcopy(cfg.get("input", {})),
            "combo": combo,
            "combo_index": i,
            "_base_dir": base_dir,
        }
        flow["steps"] = _build_steps(cfg, combo, base_dir)
        flows.append(flow)
    return flows


def _build_steps(cfg: dict, combo: dict, base_dir: str) -> list[dict]:
    steps: list[dict] = []
    if "preset" in combo:
        preset = presets_mod.load_preset(str(combo["preset"]))
        if preset.get("type", "steps") != "steps":
            raise ConfigError(
                f"预设 {combo['preset']!r} 是注入块模板（type=block），不能作为 steps 轴"
            )
        steps = copy.deepcopy(preset["steps"])
    elif cfg.get("steps"):
        steps = copy.deepcopy(cfg["steps"])
    else:
        steps = [{"stage": "generate"}]

    if "think" in combo:
        tv = combo["think"]
        think_cfg = {"stage": "think"}
        if isinstance(tv, dict):
            think_cfg.update(copy.deepcopy(tv))
        else:
            think_cfg["mode"] = tv
        idx = _first_stage(steps, "think")
        if idx is not None:
            steps[idx] = think_cfg
        else:
            gidx = _first_stage(steps, "generate")
            steps.insert(gidx if gidx is not None else len(steps), think_cfg)

    if "temperature" in combo:
        gidx = _first_stage(steps, "generate")
        if gidx is not None:
            steps[gidx]["temperature"] = combo["temperature"]
        else:
            steps.append({"stage": "generate", "temperature": combo["temperature"]})

    return steps


def _first_stage(steps: list[dict], stage: str) -> int | None:
    for i, s in enumerate(steps):
        if s.get("stage") == stage:
            return i
    return None


def combo_yaml(flow: dict) -> str:
    doc = {
        "experiment": flow["experiment"],
        "provider": flow["provider"],
        "input": flow["input"],
        "preset": flow.get("preset_name") or (flow.get("combo") or {}).get("preset"),
        "combo": flow.get("combo"),
        "combo_index": flow.get("combo_index"),
        "steps": flow["steps"],
    }
    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)


def write_generated(flows: list[dict], out_dir: str) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for flow in flows:
        path = os.path.join(
            out_dir, f"combo-{flow.get('combo_index', 1):03d}.yaml"
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(combo_yaml(flow))
        paths.append(path)
    return paths
