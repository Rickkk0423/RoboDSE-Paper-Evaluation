# RoboDSE / NeuSim-Ramulator DSE 项目入口

整理日期：2026-11-16。当前工作目录：`/Users/mr.meeseeks/gemini/DSE`。

本次已从 gemini 根目录整体移入独立 DSE 子目录，见 `handoff/REORGANIZATION_REPORT.md`。旧版布局文档只作历史记录。

## 先读什么

1. 本文件：目录、状态和复现边界。
2. `docs/CASE_V7_REPORT.md`：最新交付，不是原始 README 中的 V5 状态。
3. `docs/CASE_V6_REPORT.md`：V7 依赖的修复、实验和适用范围。
4. `docs/STORAGE_CLEANUP_20261116.md`：冷存档与恢复方式。
5. `handoff/HANDOFF_PROMPT.md`：下一位执行者可直接使用的完整提示词。
6. `handoff/TRANSFER_REPORT.md`：此次复制及验证结果。

原 DSE `README.md` 已原字节保存在 `handoff/original_inputs/DSE_README_ORIGINAL.md`；父目录 README 是两条工作线的总入口。各版本报告保留原字节，其中“最新”只代表当时的版本。

## 目录索引

| 路径 | 内容 |
| --- | --- |
| `vlasim/` | 分析模型、调度器、V3-V7 执行和报告代码；Python 包位于 `vlasim/vlasim/` |
| `tests/` | 回归测试 |
| `configs/` | 实验配置 |
| `scripts/` | Einstein 批处理、存储压缩及维护脚本 |
| `docs/` | Phase1-5、V3-V7 报告、诊断与原生后端流程 |
| `results/v7/` | 最新论文数据、成本敏感性、Pareto、计时复查、任务采集计划 |
| `results/v6/`, `results/v5_1/`, `results/v5/`, `results/v4/` | 各历史版本的结果与交付清单 |
| `results/case_v3/`, `results/case_v3_complete/` | V3 分析与冻结原始证据；`raw_evidence` 是内部相对软链接 |
| `results/einst/` | 已回收的远端实验结果，不代表重新访问了远端 |
| `results/_cold_storage_20261116/` | 压缩原始证据、逐文件索引、哈希及清理记录，不能当缓存删除 |
| `.native/` | 固定计算后端源码、原生库、构建记录和清单 |
| `dependencies/Ramulator_parallel/` | 相邻后端项目完整文件快照，含 NeuSim、Ramulator2 与已有阶段证据；不导入外部 Git 指针 |
| `../Ramulator/` | 同级的独立后端交接包，有自身 README、STATUS、Git 和远端资源索引；本次未移动或修改 |
| `handoff/original_inputs/` | Downloads 仍存在的 V7 与 Stage3 诊断原始说明 |
| `handoff/transfer_manifest.json` | 从旧目录逐文件比较的 SHA-256 和软链接检查结果 |
| `handoff/source_history.bundle` | 原主项目 HEAD 的可移植 Git 历史；未跟踪的工作内容在实际目录中 |
| `handoff/backend_*_history.bundle` | 后端 upstream、stage0 HEAD、fmt 与 yaml-cpp 的 Git 历史备份 |
| `.venv/` | 在新目录重建的 Python 环境，不是旧虚拟环境副本 |

## 当前结论

- V7 已交付，22 个 Box 中 5 个 task_strictly_better、3 个 task_extends、14 个 identical。
- Box(200,100) 是前沿扩展，不是严格支配；不能把资源前沿扩展写成最终硬件优势。
- 32,288 个计时身份完成 960-request 检查。此前最终回归为 337 项通过；本次迁移复测见交接报告。
- 成本参数是文献估计；两项 Micron 能耗中心值是作者提供，未独立取回原文。不能跨内存类型做绝对能耗排名。
- 严格改进身份在 stress >=80% 的稳健数量为 0；中心面积系数下，严格面积获益 Box 数为 0/22。
- 真实 task episode 数为 0。16 点测量方案是计划，不是任务成功率实验。
- V7 没有新大网格、新 heldout 或新跨主机运行。不得把历史证据标为新增验证。

## 本地检查

```bash
cd /Users/mr.meeseeks/gemini/DSE
.venv/bin/python -m pytest -q
PYTHONPATH=vlasim .venv/bin/python vlasim/v7_report.py verify
.venv/bin/python handoff/verify_snapshot.py
```

第二条命令会重写 V7 自校验状态文件，但不会重建实验。不要直接运行 `v7_finish.py` 或各版本 publish/finisher：它们可能改写冻结输出。

第三条只读取新目录，逐项复核全部复制载荷，不需要原目录。`transfer.py` 用于与原目录进行比较，未来产生有意变更后出现快照不一致是预期现象，应另建新版本清单而非覆盖本次基线。

README 原件及因环境重建自动更新的 egg-info `SOURCES.txt` 原件另存于 `handoff/original_inputs/`；快照校验明确记录这两项归档位置，不放宽其原始哈希。只读校验所有历史交付和压缩证据可运行 `.venv/bin/python handoff/verify_deliveries.py`，不会写入旧 results。

环境重建：

```bash
uv sync --locked --python 3.12 --all-extras
```

此次使用本机 uv 管理的 CPython 3.12.10。虚拟环境仍依赖基础解释器及系统动态库，不是可跨操作系统携带的容器。系统 Homebrew `python3` 此前异常，请优先用 `.venv/bin/python`。

## 冷存档

不要默认解压所有历史结果；约 11 GB 压缩证据会占用更多磁盘。

```bash
.venv/bin/python scripts/compact_results.py --restore results/v6/dse/shards
# 确有必要且空间充足时：
.venv/bin/python scripts/compact_results.py --restore all
```

恢复拒绝覆盖并核对哈希。历史 validator 大多不认识冷存档，缺目录不等于实验未完成。V7 preservation 支持存档索引。

本次根 README 已合并入口，原件另存，因此历史 `preservation()` 若直接核对根 README 会报不一致；请用 `handoff/verify_deliveries.py`，它按原清单哈希核对归档原件，不修改旧 manifest、不跳过该项。

## 规格与来源

- V3 原文副本：`results/einst/case_v3_p0/CASE_V3_SPEC.md`。
- V5：`results/v5/NEXT_STEPS_V5.md`；V5.1 附加说明：`results/v5_1/NEXT_STEPS_V5_1_AMENDMENT.md`。
- V6：`results/v6/NEXT_STEPS_V6_READBACK.md` 是完整工具读回重建，**不是字节级原始文件**；来源状态在 `input_spec_provenance.json`。
- V7：`results/v7/NEXT_STEPS_V7.md`，并保留 Downloads 原件副本。
- 原始 `vlasim.zip` 和 `NEXT_STEPS_V4.md` 在 Downloads 已不可见，未冒充恢复原件；历史实现和证据仍完整保留。导入 zip 的原始 SHA-256 见 `handoff/original_inputs/DSE_README_ORIGINAL.md`。

## 外部依赖与边界

- 原工作目录保留，未删除；此次是经验证的独立文件副本，不是破坏性搬家。
- 新目录不使用旧 worktree `.git` 指针；原 `.git` 和所有缓存、旧 venv 均不作为有效交付导入。
- 后端历史清单中的绝对路径是来源记录，不应全局替换；新实验显式使用 `dependencies/Ramulator_parallel` 或另建后端快照。
- CMake 旧缓存、Mach-O 的动态库引用、Linux `.so` 及远端脚本可能不可直接在新路径执行；必要时在**新输出目录**重建，不覆盖冻结后端。
- 原生后端构建参考 `docs/NATIVE_WORKFLOW.md`，把示例的 `../Ramulator_parallel` 改为实际传入的 `dependencies/Ramulator_parallel`；不要改历史证据文件。
- 不含 SSH 密钥、账号配置、真实任务检查点、环境或尚未回收的远端文件。`einst` 的连接和队列状态需要执行时重新核实。
- 如果原目录继续产生修改，两目录不会自动同步；后续工作统一在本目录进行。
