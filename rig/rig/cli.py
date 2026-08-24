"""CLI：run / matrix / compare / presets。

用法：
  python -m rig run experiments/sample.yaml [--input TEXT]
  python -m rig matrix experiments/ab-test.yaml [--dry-run]
  python -m rig compare traces/<实验名>
  python -m rig presets
"""

from __future__ import annotations

import argparse
import os
import sys

from . import engine, matrix as matrix_mod, presets as presets_mod, traces as traces_mod
from . import __version__
from .config import ConfigError, load_config, validate_flow, validate_matrix
from .provider import ProviderError
from .traces import traces_root


def _setup_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


def _load_flow(args) -> dict:
    path = args.config
    cfg = load_config(path)
    validate_flow(cfg)
    base_dir = os.path.dirname(os.path.abspath(path))
    cfg["_base_dir"] = cfg.get("_base_dir") or base_dir
    presets_mod.expand_preset(cfg)
    if args.input is not None:
        cfg["input"]["text"] = args.input
    if not cfg.get("steps"):
        raise ConfigError("flow 展开后 steps 为空")
    return cfg


def _write_full_run(run_dir_path: str, flow: dict, entries: list[dict]) -> None:
    traces_mod.write_run_start(run_dir_path, flow)
    for e in entries:
        traces_mod.write_line(run_dir_path, e)
    traces_mod.write_run_end(run_dir_path, flow)


def cmd_run(args) -> int:
    flow = _load_flow(args)
    entries = engine.run_flow(flow)

    run_id = traces_mod.new_run_id()
    d = traces_mod.run_dir(flow["experiment"], run_id)
    _write_full_run(d, flow, entries)

    print(f"实验 {flow['experiment']} · provider={flow.get('provider')} · run {run_id}")
    for e in entries:
        if e["stage"] == "config":
            continue
        detail = ""
        if e["stage"] == "generate":
            detail = f" model={e['meta'].get('model')} usage={e['meta'].get('usage', {}).get('total_tokens')}"
        elif e["stage"] == "think":
            detail = f" mode={e['meta'].get('mode')}"
        elif e["stage"] == "process":
            detail = " " + "；".join(t["note"] for t in e["meta"].get("transforms", []))
        print(f"  [{e['seq']}] {e['stage']}{detail}")
    final = next(
        (e["snapshot"].get("text") for e in reversed(entries) if e["obj_type"] == "text"),
        None,
    )
    print(f"最终输出：{final}")
    print(f"轨迹：{os.path.join(d, 'trace.jsonl')}")
    return 0


def cmd_matrix(args) -> int:
    path = args.matrix_path
    cfg = load_config(path)
    validate_matrix(cfg)
    base_dir = os.path.dirname(os.path.abspath(path))
    flows = matrix_mod.expand_matrix(cfg, base_dir)

    if args.dry_run:
        out_dir = os.path.join(base_dir, "generated", cfg["experiment"])
        paths = matrix_mod.write_generated(flows, out_dir)
        print(f"dry-run：生成 {len(flows)} 个组合 flow（未执行）→ {out_dir}")
        for flow, p in zip(flows, paths):
            combo = flow["combo"]
            summary = " ".join(f"{k}={v}" for k, v in combo.items())
            print(f"  [combo-{flow['combo_index']:03d}] {summary} → {p}")
        return 0

    print(f"矩阵执行：{cfg['experiment']} · {len(flows)} 个组合")
    ok = 0
    for flow in flows:
        combo = flow["combo"]
        summary = " ".join(f"{k}={v}" for k, v in combo.items())
        d = traces_mod.combo_dir(cfg["experiment"], flow["combo_index"])
        entries = engine.run_flow(flow)
        _write_full_run(d, flow, entries)
        final = next(
            (e["snapshot"].get("text") for e in reversed(entries) if e["obj_type"] == "text"),
            None,
        )
        print(f"  [combo-{flow['combo_index']:03d}] {summary}")
        print(f"      最终输出：{final}")
        ok += 1
    print(f"完成：{ok}/{len(flows)} 组合，轨迹在 {traces_root()}/{cfg['experiment']}/")
    return 0


def cmd_compare(args) -> int:
    name = args.experiment
    prefix = "traces" + os.sep
    if name.startswith(prefix):
        name = name[len(prefix):]
    elif name.startswith("traces/"):
        name = name[len("traces/"):]
    out = traces_mod.write_compare(name)
    print(f"对比报告：{out}")
    with open(out, encoding="utf-8") as f:
        content = f.read()
    overview = content.split("\n## ")[0]
    print(overview)
    print("…（完整 markdown 已写入上述文件）")
    return 0


def cmd_presets(args) -> int:
    items = presets_mod.list_presets()
    if not items:
        print("未找到任何预设（查找于 presets/ 目录）")
        return 1
    print(f"可用预设（{len(items)} 个）：")
    for p in items:
        kind = "步骤模板" if p["type"] == "steps" else "注入块模板"
        print(f"  {p['name']:<16} {kind}  {p['description']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    _setup_utf8()
    parser = argparse.ArgumentParser(prog="rig", description="试验机：嘴层语言实验台（配置驱动，全离线可验证）")
    parser.add_argument("--version", action="version", version=f"rig {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="执行单个 flow 配置")
    p_run.add_argument("config", help="flow YAML 路径，如 experiments/sample.yaml")
    p_run.add_argument("--input", help="覆盖配置里的输入文本")
    p_run.set_defaults(func=cmd_run)

    p_matrix = sub.add_parser("matrix", help="组合枚举执行（axes 笛卡尔积）")
    p_matrix.add_argument("matrix_path", help="matrix YAML 路径，如 experiments/ab-test.yaml")
    p_matrix.add_argument("--dry-run", action="store_true", help="只生成 flow 文件不执行")
    p_matrix.set_defaults(func=cmd_matrix)

    p_cmp = sub.add_parser("compare", help="同输入多配置并排输出 markdown")
    p_cmp.add_argument("experiment", help="实验名（或 traces/<实验名> 路径）")
    p_cmp.add_argument("--format", choices=["md"], default="md", help="输出格式（目前仅 md）")
    p_cmp.set_defaults(func=cmd_compare)

    p_pre = sub.add_parser("presets", help="列出可用预设")
    p_pre.set_defaults(func=cmd_presets)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, FileNotFoundError, ProviderError) as e:
        print(f"rig: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
