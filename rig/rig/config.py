"""配置加载与 schema 校验：YAML 解析、错误定位到字段、配置哈希、ref 解析。

错误消息形如「steps[2].rounds 必须是整数（当前: abc）」，便于定位。
"""

from __future__ import annotations

import hashlib
import json
import os

import yaml

STAGE_NAMES = ("inject", "think", "generate", "process")
PROVIDERS = ("mock", "openai_compat")
THINK_MODES = ("none", "cot", "multi")
BLOCK_TYPES = ("persona", "summary", "instruction")


class ConfigError(ValueError):
    """配置/流程错误：报错时点名字段或步骤序号。"""


# ---------------------------------------------------------------- 加载

def load_config(path: str) -> dict:
    if not os.path.exists(path):
        raise ConfigError(f"配置文件不存在: {path}")
    with open(path, encoding="utf-8") as f:
        try:
            cfg = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"YAML 解析失败（{path}）: {e}") from e
    if not isinstance(cfg, dict):
        raise ConfigError(f"配置根必须是映射（dict），当前是 {type(cfg).__name__}")
    return cfg


def _expect_type(cfg, key, types, where, optional=True, default=None):
    """校验 cfg[key] 类型；缺失时返回 default（可选字段）。"""
    if key not in cfg or cfg[key] is None:
        if optional:
            return default
        raise ConfigError(f"{where}.{key} 缺失，必填")
    v = cfg[key]
    if isinstance(types, tuple):
        if not isinstance(v, types):
            raise ConfigError(f"{where}.{key} 必须是 {'/'.join(t.__name__ for t in types)}（当前: {v!r}）")
    elif not isinstance(v, types):
        raise ConfigError(f"{where}.{key} 必须是 {types.__name__}（当前: {v!r}）")
    return v


# ---------------------------------------------------------------- flow 校验

def validate_flow(cfg: dict, source: str = "flow") -> None:
    _expect_type(cfg, "experiment", str, source, optional=False)
    _expect_type(cfg, "provider", str, source)
    if "provider" in cfg and cfg["provider"] not in PROVIDERS:
        raise ConfigError(f"{source}.provider 必须是 {'/'.join(PROVIDERS)} 之一（当前: {cfg['provider']!r}）")
    if not isinstance(cfg.get("input"), dict):
        raise ConfigError(f"{source}.input 必须是映射（含 text 字段）")
    _expect_type(cfg["input"], "text", str, f"{source}.input", optional=False)
    _expect_type(cfg["input"], "context", str, f"{source}.input")
    if "preset" in cfg:
        _expect_type(cfg, "preset", str, source)
    if "steps" in cfg:
        validate_steps(cfg["steps"], f"{source}.steps")
    if cfg.get("steps") is None and not cfg.get("preset"):
        raise ConfigError(f"{source} 必须提供 steps 或 preset（当前两者都没有）")


def validate_steps(steps, where: str) -> None:
    if not isinstance(steps, list):
        raise ConfigError(f"{where} 必须是列表")
    if not steps:
        raise ConfigError(f"{where} 不能为空")
    for i, step in enumerate(steps):
        w = f"{where}[{i}]"
        if not isinstance(step, dict):
            raise ConfigError(f"{w} 必须是映射（含 stage 字段）")
        stage = _expect_type(step, "stage", str, w, optional=False)
        if stage not in STAGE_NAMES:
            raise ConfigError(f"{w}.stage 必须是 {'/'.join(STAGE_NAMES)} 之一（当前: {stage!r}）")
        if stage == "inject":
            _validate_inject(step, w)
        elif stage == "think":
            _validate_think(step, w)
        elif stage == "generate":
            _validate_generate(step, w)
        elif stage == "process":
            _validate_process(step, w)


def _validate_think(step, w) -> None:
    mode = _expect_type(step, "mode", str, w)
    if mode is not None and mode not in THINK_MODES:
        raise ConfigError(f"{w}.mode 必须是 {'/'.join(THINK_MODES)} 之一（当前: {mode!r}）")
    if "rounds" in step:
        r = step["rounds"]
        if not isinstance(r, int) or isinstance(r, bool) or r < 1:
            raise ConfigError(f"{w}.rounds 必须是正整数（当前: {r!r}）")
    if "visible" in step:
        v = step["visible"]
        if not isinstance(v, bool):
            raise ConfigError(f"{w}.visible 必须是布尔值（当前: {v!r}）")


def _validate_generate(step, w) -> None:
    if "model" in step:
        _expect_type(step, "model", str, w)
    if "temperature" in step:
        t = step["temperature"]
        if not isinstance(t, (int, float)) or isinstance(t, bool) or not (0 <= t <= 2):
            raise ConfigError(f"{w}.temperature 必须是 0~2 之间的数字（当前: {t!r}）")
    if "max_tokens" in step:
        mt = step["max_tokens"]
        if not isinstance(mt, int) or isinstance(mt, bool) or mt < 1:
            raise ConfigError(f"{w}.max_tokens 必须是正整数（当前: {mt!r}）")


def _validate_inject(step, w) -> None:
    blocks = step.get("blocks")
    if blocks is None:
        return
    if not isinstance(blocks, list):
        raise ConfigError(f"{w}.blocks 必须是列表")
    for i, b in enumerate(blocks):
        bw = f"{w}.blocks[{i}]"
        if not isinstance(b, dict):
            raise ConfigError(f"{bw} 必须是映射")
        btype = _expect_type(b, "type", str, bw, optional=False)
        if btype not in BLOCK_TYPES:
            raise ConfigError(f"{bw}.type 必须是 {'/'.join(BLOCK_TYPES)} 之一（当前: {btype!r}）")
        if btype in ("persona", "summary") and not b.get("ref"):
            raise ConfigError(f"{bw}.ref 缺失：{btype} 块必须提供 ref")
        if btype == "instruction" and not (b.get("text") or b.get("ref")):
            raise ConfigError(f"{bw} 缺失：instruction 块必须提供 text 或 ref")


def _validate_process(step, w) -> None:
    transforms = step.get("transforms")
    if transforms is None:
        return
    if not isinstance(transforms, list):
        raise ConfigError(f"{w}.transforms 必须是列表")
    for i, t in enumerate(transforms):
        tw = f"{w}.transforms[{i}]"
        if isinstance(t, str):
            continue
        if isinstance(t, dict):
            name = t.get("name")
            if not isinstance(name, str):
                raise ConfigError(f"{tw} 必须含字符串 name 字段")
            continue
        raise ConfigError(f"{tw} 必须是阶段名（字符串）或含 name 的映射（当前: {t!r}）")


# ---------------------------------------------------------------- matrix 校验

def validate_matrix(cfg: dict) -> None:
    _expect_type(cfg, "experiment", str, "matrix", optional=False)
    _expect_type(cfg, "provider", str, "matrix")
    if "provider" in cfg and cfg["provider"] not in PROVIDERS:
        raise ConfigError(f"matrix.provider 必须是 {'/'.join(PROVIDERS)} 之一（当前: {cfg['provider']!r}）")
    if not isinstance(cfg.get("input"), dict):
        raise ConfigError("matrix.input 必须是映射（含 text 字段）")
    _expect_type(cfg["input"], "text", str, "matrix.input", optional=False)
    axes = cfg.get("axes")
    if not isinstance(axes, dict) or not axes:
        raise ConfigError("matrix.axes 必须是至少含一个候选集的映射")
    for name, values in axes.items():
        if not isinstance(values, list) or not values:
            raise ConfigError(f"matrix.axes.{name} 必须是至少含一个候选值的列表")
    if "steps" in cfg:
        validate_steps(cfg["steps"], "matrix.steps")


# ---------------------------------------------------------------- ref 解析

def resolve_ref(ref: str, base_dir: str) -> str:
    """ref 相对路径解析：先相对配置文件所在目录，再相对当前工作目录。"""
    candidates = []
    if os.path.isabs(ref):
        candidates.append(ref)
    else:
        candidates.append(os.path.join(base_dir, ref))
        candidates.append(os.path.join(os.getcwd(), ref))
    for c in candidates:
        if os.path.isfile(c):
            return c
    raise ConfigError(
        f"ref 无法解析: {ref!r}（尝试了 {', '.join(candidates)}，均不存在）"
    )


def load_ref_text(ref: str, base_dir: str) -> str:
    path = resolve_ref(ref, base_dir)
    with open(path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- 配置哈希

def config_hash(cfg: dict) -> str:
    """规范化 JSON 序列化后的 sha256 前 12 位，作为配置指纹。

    排除 _base_dir / combo_index 等执行内部键：同配置不因运行位置或
    组合序号而变，compare 分组与复现才有意义。
    """
    base = {k: v for k, v in cfg.items() if k not in ("_base_dir", "combo_index")}
    canonical = json.dumps(base, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def config_ref(cfg: dict) -> str:
    return "sha256:" + config_hash(cfg)
