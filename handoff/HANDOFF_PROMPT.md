# 交接提示词

你接手的是 RoboDSE 的 NeuSim/Ramulator VLA DSE 项目。唯一后续工作目录为 `/Users/mr.meeseeks/gemini/DSE`，不要再从 gemini 父目录运行 DSE 命令。用户希望你自主把明确范围内的工作推进到完成，除非遇到真正阻塞，不要反复等待提醒；用中文汇报，不能伪造实验、远端执行或验证。

先阅读 `START_HERE.md`、`handoff/REORGANIZATION_REPORT.md`、`docs/CASE_V7_REPORT.md`、`docs/CASE_V6_REPORT.md` 和 `docs/STORAGE_CLEANUP_20261116.md`，然后检查 Git、现有结果、测试状态和剩余磁盘。`handoff/TRANSFER_REPORT.md` 是首次复制的历史记录，其旧工作路径不再有效。原 DSE README 停留在 V5，已另存 `handoff/original_inputs/DSE_README_ORIGINAL.md`。整理工作没有产生新的科学实验。

代码、配置、报告、完整本地结果、失败证据、冷存档和 `.native` 都在该目录。相关后端源码和独立阶段证据在 `dependencies/Ramulator_parallel/`。仍存在的作者说明在 `handoff/original_inputs/`，历史规格副本见 START_HERE。V6 说明是工具读回重建，不是原始字节文件。原工作目录暂存不动，不要在那里继续工作，也不要删除它来冒充迁移验收。

父目录还有单独的 `../Ramulator/` 后端交接包，保留其独立 README、STATUS、Git 和远端资源说明。DSE 的 `dependencies/` 是固定复制快照，不要把两套后端目录交叉覆盖或同时当作开发真源；做后端优化时遵循 `../Ramulator/HANDOFF_PROMPT.md`，做 DSE 复查时保持本项目冻结输入身份。

首先执行：

```bash
cd /Users/mr.meeseeks/gemini/DSE
.venv/bin/python -m pytest -q
PYTHONPATH=vlasim .venv/bin/python vlasim/v7_report.py verify
.venv/bin/python handoff/verify_snapshot.py
```

当前 V7 是冻结交付：22 Boxes 中 5 strictly_better、3 extends、14 identical；Box(200,100) 是扩展，不是严格支配。32,288 个计时身份通过 960-request 检查，迁移前 337 项测试通过。具体本次验收结果看交接报告。V7 没有新 DSE 网格、heldout 或跨主机运行；真实 task episode 为 0。16 点任务采集方案尚未执行。stress>=80% 的严格改进稳健身份为 0，中心面积系数下严格面积获益为 0/22。两项 Micron 能耗中心值为作者提供而非独立取回。禁止跨内存类型绝对能耗排名。所有这些限制必须保持，不得把模型估计当作物理测量。

保护 `results/v7` 和各历史交付、固定源码、manifest、原始失败记录及其哈希。不要直接重跑 `v7_finish.py`、历史 publish/finisher，或全局替换历史绝对路径。新分析、新实验写到新版本或带时间戳目录，使用明确的输入身份、源码版本、配置及 SHA-256。修改后做与风险匹配的回归，保留失败结果。

`results/_cold_storage_20261116/` 是必要证据，不是可删除缓存。历史 validator 不一定支持归档；缺目录时先查清理清单，确需恢复再执行 `.venv/bin/python scripts/compact_results.py --restore <path>`。恢复前检查空间，不要默认全部解压，不要改写旧 manifest 来掩盖缺失。

本目录虚拟环境使用 CPython 3.12.10。基础解释器和系统库仍是外部运行依赖，不能声称项目跨平台完全自包含。用 `.venv/bin/python`，不要直接依赖此前异常的 Homebrew python3。后端旧构建缓存和动态库含历史路径，新增 native 实验应在新目录重建并核对源清单，不覆盖冻结 `.native`。远端 `einst` 必须重新核实连接、构建和队列，不得把本地保存的远端日志当作新远端运行。

后续用户若提供新阶段说明，以新说明定义范围，一次推进实现、实验、验证和报告。没有新说明时，先只读核实 V7 任务采集计划和缺失资源，明确 checkpoint、真实环境、采集协议与成本来源的依赖；可以落实不需要这些资源的准备工作，但不得擅自扩展大网格或声称完成真实任务闭环。最终报告区分已完成、仅准备、未执行、条件成立和真实阻塞。
