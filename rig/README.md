# 试验机（rig）— 嘴层语言实验台 MVP

配置驱动的 LLM 语言实验 CLI：注入 / 思考 / 生成 / 加工四段管线可独立开关、
可重排可重复，全链 JSONL 轨迹，`mock` 下全离线可验证（同配置两次运行轨迹逐字节一致）。

```
输入 → [注入] → [思考×N] → [生成] → [加工] → 输出
       人格/摘要/ 无/CoT/    采样参数   过滤/格式化/
       指令块    多轮草稿    温度/token  长度控制
```

三层结构：

- **机制层**：阶段原语 `inject / think / generate / process`，统一签名 `stage_transform(stage, ctx, cfg)`，注册表挂载（`rig/stages.py`）；
- **操作层**：flow 文件（显式 `steps` 数组）+ matrix 文件（候选集笛卡尔积）+ 预设（命名步骤模板）；
- **执行层**：CLI 四命令 `run / matrix / compare / presets`。

## 三分钟上手

```powershell
cd rig
pip install -r requirements.txt
```

### 1. 跑单个流程

```powershell
python -m rig run experiments/sample.yaml
```

输出轨迹：`traces/sample-demo/<run-id>/trace.jsonl`（run-id = 时间戳+短随机）。

覆盖输入文本：

```powershell
python -m rig run experiments/sample.yaml --input "今天加班到很晚"
```

### 2. 跑矩阵（组合枚举）

```powershell
python -m rig matrix experiments/ab-test.yaml
```

`axes` 笛卡尔积生成 2×2×2=8 个组合，逐组合执行，各落 `traces/ab-test/combo-001/trace.jsonl` 等。

只生成 flow 文件不执行：

```powershell
python -m rig matrix experiments/ab-test.yaml --dry-run
# → experiments/generated/ab-test/combo-001.yaml …
# 生成物可直接被 run 执行：
python -m rig run experiments/generated/ab-test/combo-001.yaml
```

### 3. 并排对比

```powershell
python -m rig compare traces/ab-test
# → traces/ab-test/compare.md（同输入多配置并排 markdown，人工判读）
```

### 4. 预设

```powershell
python -m rig presets
```

预设 = 命名步骤模板（`presets/*.yaml`）。flow 里 `preset: reply-simple` 展开成默认
steps；flow 显式写出的 step 键覆盖预设同名项（预设展开后再合并显式覆盖）。
注入块模板（`type: block`，如 `persona-lite.yaml`）被 `inject.blocks` 以 `ref` 引用。

## 配置说明

```yaml
# flow 文件
experiment: sample-demo        # 实验名（轨迹目录名）
provider: mock                 # mock | openai_compat
input:
  text: 今天有点累              # 必填
  context: 第三天对话           # 可选，自动作为 system 块注入
preset: reply-simple           # 可选：展开成默认 steps
steps:                         # 可选：显式 steps；缺省只写 stage 名也可
  - {stage: inject, blocks: [{type: persona, ref: presets/persona-lite.yaml}]}
  - {stage: think, mode: multi, rounds: 2}
  - {stage: generate, model: qwen2.5:7b, temperature: 0.8, max_tokens: 512}
  - {stage: process, transforms: [trim]}
```

- 注入块三种类型：`persona` / `summary`（需 `ref` 指向 YAML 或 md 文件）/ `instruction`（`text` 或 `ref`）；
- 思考模式：`none`（直通）/ `cot`（单轮，`visible` 决定思考是否留在消息流）/ `multi`（`rounds` 轮草稿→修订）；
- 加工变换：`trim` / `clamp_length`（`max_chars`）/ `filter`（`forbidden` 关键词列表）；
- 阶段输入要求：inject/think/generate 吃 messages，process 吃 text（须排在生成之后）；
  排列不合法报错并点名步骤序号与阶段名。

## Provider 切换与密钥

- `provider: mock`：确定性替身，不回显输入，按模板生成文本 + 假 usage/假耗时，全离线可用；
- `provider: openai_compat`：requests 直连 `{base_url}/chat/completions`
  （Ollama 默认 `http://localhost:11434/v1`；Gemini 用其 OpenAI 兼容端点
  `https://generativelanguage.googleapis.com/v1beta/openai/`）。

API key **只从环境变量读，绝不落盘**：默认 `OPENAI_API_KEY`；flow 里可指定
`api_key_env: GEMINI_API_KEY` 等变量名（写入 flow 的只是变量名）。`base_url` 与
`model` 也可用环境变量 `RIG_BASE_URL` / `RIG_MODEL` 覆盖。

## 轨迹

- 单流程：`traces/<实验名>/<run-id>/trace.jsonl`；
- matrix：`traces/<实验名>/combo-001/trace.jsonl` 等；
- 文件以 `run_start` header 行开始、`run_end` 行结束（含配置哈希 sha256 前 12 位），
  中间每行一条步骤 trace：`{seq, ts, stage, cfg, obj_type, snapshot, meta}`；
  generate 的 meta 含 `model / usage / elapsed_ms`；UTF-8、`ensure_ascii=False`；
- `traces/`、`experiments/generated/` 已入 .gitignore，不进仓库。

## 约束

- 依赖仅 `pyyaml`、`requests`（`requirements.txt` 已 pin）；
- 试验机独立于状态内核，不写任何状态；MVP 不做 UI / 自动评估 / 多模型路由。
