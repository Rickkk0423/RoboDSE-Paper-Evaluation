# DSE 项目整理与交接验收

日期：2026-11-16，America/Los_Angeles。

## 结果

主项目已整理到 `/Users/mr.meeseeks/gemini`，DSE 代码和结果直接位于根目录。主入口是 `START_HERE.md`，完整交接提示词是 `handoff/HANDOFF_PROMPT.md`。此次没有执行新的科学实验或删除原始证据。

原目录 `/Users/mr.meeseeks/orca/workspaces/RoboDSE/Neusim_ramulator_DSE` 和相邻后端目录均保留。此次为经 SHA-256 验证的复制，不是删除源目录的移动，也不提供双向同步。后续 DSE 工作统一在新目录开展。

## 已收集内容

- 主项目代码、配置、测试、文档、锁文件、全部本地 results、冷存档及 `.native`。
- 相邻 `Ramulator_parallel` 的源码及已有本地阶段证据快照，位于 `dependencies/Ramulator_parallel/`。
- Downloads 仍可找到的 `NEXT_STEPS_V7.md` 和两份 Stage3 诊断计划，位于 `handoff/original_inputs/`。
- 原项目 HEAD 和后端 upstream、stage0 HEAD、fmt、yaml-cpp 的 Git bundle。
- 新目录 Python 环境、项目索引、Gemini 工作规则、交接提示词、完整复制清单与验证工具。

初始复制清单：40,453 个文件或软链接，普通文件合计 15,375,719,387 字节，约 14.32 GiB。不包括新建环境、交接文档和另一条工作线新增的文件。

排除项仅为 `.git`、`.venv`、`.pytest_cache`、`__pycache__`、`.DS_Store`。Git 历史另以 bundle 保留，不复制失效 worktree 指针；新根目录建立独立 Git 仓库并导入原主项目 HEAD 到 `main`，没有擅自创建提交。原工作内容本来未跟踪，仍保留为未提交文件。结果仍由原 `.gitignore` 排除，**不能只用 Git clone 代替本交接包**。

## 同目录的另一份交接包

整理期间，目标下新增独立 `Ramulator/` 包及其根 README 入口。本次未删除、覆盖其项目或改动其内部交接文件，仅在根 README 中补齐 DSE 入口。

- DSE 主项目：根目录的 `vlasim/`、`results/`、`docs/`。
- DSE 固定后端快照：`dependencies/Ramulator_parallel/`。
- 后端独立工作线：`Ramulator/README.md`、`Ramulator/STATUS.md` 和 `Ramulator/HANDOFF_PROMPT.md`。

这两份后端内容用途不同，不应交叉覆盖。本报告只对本次 DSE 复制载荷负责；`Ramulator/` 自身验收、远端状态和开发流程以其独立报告为准。

## 有记录的两项布局变化

1. 原 DSE README 的字节级原件保存到 `handoff/original_inputs/DSE_README_ORIGINAL.md`；根 README 改为两条项目线的总索引。
2. `uv sync` 自动重建了 `vlasim/vlasim_dse.egg-info/SOURCES.txt`；旧原件保存到 `handoff/original_inputs/DSE_EGG_SOURCES_ORIGINAL.txt`。

初始传输清单没有被重写。`verify_snapshot.py` 和 `verify_deliveries.py` 对这两项使用明确的原件位置映射，仍核对最初 SHA-256，不跳过、不重新背书变化后的文件。

## 验证结果

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 源目录与初始副本逐项比较 | 40,453 项，0 差异 | `handoff/transfer_manifest.json` |
| 只读新目录的全量快照验证 | 40,453 项，0 差异，不读取原目录 | `handoff/validation/snapshot_verification.json` |
| 新环境全量 pytest | 337 passed，90.06 秒 | `handoff/validation/pytest.xml` |
| V7 原脚本 verify | 19,626 artifacts + 17 sources 全部匹配 | `results/v7/delivery_verification.json` |
| 只读交付复核 | V7 同上；V6 38,748 项、V5.1 80,947 项、V5 249 项、V4 383 项、V3 完整交付 904 项，全通过 | `handoff/validation/delivery_verification.json` |
| 冷存档 | 压缩文件 SHA-256 全通过，索引覆盖 108,479 个文件 | 同上 |
| 软链接 | 原结果链接为项目内部相对路径，保持有效；环境解释器链接有效 | 快照清单与新环境 |

这些是文件完整性和软件回归检查，不是新的独立 heldout、跨主机或真实任务验证。原生 C++ 后端未在新路径重新构建，真实任务 episode 仍为 0。

## 环境与复查

使用本机 uv 管理的 CPython 3.12.10，执行 `uv sync --locked --python <该解释器> --all-extras` 重建环境。锁文件保持原字节。环境绑定新目录，未携带旧环境 shebang 或旧 editable 安装路径。

```bash
cd /Users/mr.meeseeks/gemini
.venv/bin/python -m pytest -q
.venv/bin/python handoff/verify_snapshot.py
.venv/bin/python handoff/verify_deliveries.py
PYTHONPATH=vlasim .venv/bin/python vlasim/v7_report.py verify
```

后两种验证中，只有 V7 原脚本会写其自校验状态；新增工具只写 `handoff/validation/`。因 README 原件已归档，直接调用旧 historical preservation 函数可能失败；用新增只读交付工具核对原件，不改冻结 manifest。

`handoff/transfer.py` 是本次一次性传输的实现记录，已有清单时拒绝再次 `--copy`。今后有意修改代码后，快照检查报差异是正常的，应为新版本另存清单。

## 未包含与后续边界

- 未复制 SSH 私钥、登录配置、账号凭据或全局 Python 环境。
- 当前主机看不到的原始 zip、V4 说明等不冒充已找回；V6 规格明确为工具读回重建。已保留的历史副本与路径见 START_HERE。
- 本次未访问 einst；未声称完整收回服务器上的大型构建和所有实验文件。现存远端材料的另一份索引见 `Ramulator/remote/`，执行时须重新核实。
- 动态库、旧 CMake 缓存和远端脚本可能含历史绝对路径。它们作为证据保留；新执行应建立新输出目录并显式选择后端，不能全局替换历史路径或覆盖冻结结果。
- 基础 Python、系统库、C++ 工具链及真实任务 checkpoint/环境不是自包含资源。现有回归通过不等于所有 native 实验可跨平台直接运行。
- 不应重跑历史 finisher、解压全部冷存档或新增大网格来“补齐”此次文件整理。下一阶段需由有效规格和真实依赖决定。
