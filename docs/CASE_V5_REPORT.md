# CASE V5 执行报告

执行日期：2026-11-15（America/Los_Angeles）；规格文内日期为 2026-11-16。

**本轮在步骤 1 硬停止，未完成宽网格 DSE。原因是规定粒度的 W5 块抽样自检低于 0.90，不是混流留出误差门禁。V5 允许留出失败后双模型继续，但明确禁止越过块抽样失败。**

## 1. 门禁总表

| 阶段 / 门禁 | 状态 | 证据 |
| --- | --- | --- |
| 步骤 1：流量对账 | 通过 | 生成器逐 op/component 检查；双机 8 次完整回放采样字节对账 |
| 步骤 1：原生回调 / 控制器计数 | 通过 | accepted = completed = read + write；含 forwarded/coalesced |
| 步骤 1：新驱动与 V4 参考驱动等价 | 通过 | 每台主机 6 组，所有返回字段相同 |
| 步骤 1：跨主机 | 通过 | 6 组探针 + 4 条完整 W5，原生返回值完全相同，差异 0 ≤ 1e-6 |
| 步骤 1：2 KB / 单物理行块抽样 | **未通过，硬停止** | 两个饱和结果均为 0.893100962 < 0.90 |
| 步骤 1：大容量 HBM | 已导出，未原生验证 | HBM2_8Gb、8 通道、16 GiB，独立 YAML/hash；不能称为已校准 |
| 步骤 1：全量 pytest | 通过 | 201 项，无失败 |
| 步骤 2：开发拟合 / 新留出 | 未执行 | 被步骤 1 硬停止；未选定 V5 η_mix 或模型模式 |
| 步骤 3：逐档原生校准 | 未执行 | 不插值，不填写预期效率 |
| 步骤 4：宽网格 / 前沿复查 | 未执行 | 0 个硬件点，0 个映射；不输出假数据表 |
| 步骤 5：任务前沿连接 | 未执行 | 无 V5 attainable；新增任务局数 0 |

机器可读状态：`results/v5/gates.json`。最终 DRAM 模型模式为 `not_selected_no_v5_dse`。

## 2. DRAM 模型与抽样自检

未运行新开发集、未冻结或运行新留出集，不能报告 V5 留出误差、BG 动态验收或拟合参数。V4 原失败组保留，不作为新模型验证结果。

本阶段沿用 L_serial 的真实 NeuSim 不切片计算轨道、显式 SigLIP 解析回退、估计 workload 形状，以及原校准；不是独立执行捕获。
保留每 10 个连续块中的 1 个，块内地址连续，不压缩物理地址；只压缩时间为 1/10。饱和发射置零时间戳，保留 VLM→DiT 顺序并在组切换时等待全部旧回调，避免把 serial 误回放为并发。
该 LPDDR5 单 bank 物理行是 2 KB，所以两个指定标签产生相同输入数组；分别执行不是独立粒度样本。

| 粒度 | 发射 | 总吞吐 / (η_seq × peak) | 门禁 |
| --- | --- | ---: | --- |
| 2 KB | open | 0.892897314 | 仅报告，不作容量门禁 |
| 2 KB | saturated | 0.893100962 | 未通过 |
| 单物理行（2 KB） | open | 0.892897314 | 仅报告，不作容量门禁 |
| 单物理行（2 KB） | saturated | 0.893100962 | 未通过 |

η_seq = 0.914663293789，峰值为 204.8 GB/s；每条完整 W5 采样 1,099,364,352 字节，34,355,136 条 native32 事务。两台主机的 4 条返回记录分别一致，计数对账通过。

### 局部性诊断（不替代 W5 门禁）

固定同一 LPDDR5、MOP4CLXOR、8 issue/cycle、512 outstanding，另做每组 64 MiB 全读串行控制。下面是原生实测，不是校准、留出或完整 W5；固定样本字节数，抽样组地址跨度更大。

| 控制 | 保留块字节 | stride | 吞吐 GB/s | η_peak | 相对原 η_seq |
| --- | ---: | ---: | ---: | ---: | ---: |
| contiguous | 2048 | 1 | 188.277326 | 0.919322880 | 1.005094319 |
| line_stride_v4 | 64 | 10 | 95.164906 | 0.464672391 | 0.508025624 |
| block_2KB_v5 | 2048 | 10 | 167.055388 | 0.815700137 | 0.891803729 |
| channel_row_span_diagnostic | 32768 | 10 | 179.861072 | 0.878227892 | 0.960165230 |
| all_bank_row_span_diagnostic | 524288 | 10 | 187.247673 | 0.914295281 | 0.999597652 |

源码级解释：CacheLineInterleave 在 32 B native 事务粒度上剥离通道位。全局连续 2 KB 经 16 通道交织，每通道仅 128 B；MOP4CLXOR 又将低 2 个 column 位与 bank/rank 位交织。单行容量相同，不代表全局 2 KB 地址块保留完整 bank-row 局部性。
32 KB 为单行容量 × 通道数的跨度；512 KB 再乘 16 个 bank，是覆盖完整通道/bank 行跨度的诊断。512 KB 的恢复支持地址局部性损失解释，但这不是某一个物理行，也不是规格的 2 KB，不能据此把失败门禁改成通过。未改变 η_seq、阈值或已冻结输入。

要继续必须先获得满足指定粒度自检的可复现抽样修复，或在新的规格中明确批准更大行跨度的协议；本轮没有擅自执行该协议变更。

## 3. 校准表

V5 新网格实测校准档数为 0。自检仅引用 V3 的 `dram_v3_M-L256_mop4_width8`：η_seq=0.914663293789、η_mix=0.799040927847，不能将其称为新 VLA 混流拟合。
HBM2_8Gb、HBM2_2000Mbps、8 通道、16 GiB 的新器件身份、展开 YAML 和容量/hash 已导出到每个 selfcheck 分片；未实例化该大 HBM 做原生回放，因此容量和动态性能尚未完成原生验收。
GDDR6 24/36 通道的多实例驱动分支仅是未验证实现，不作为已支持档位或测量证据。未修改 pinned 后端或时序。

## 4. DSE 规模与剪枝

实际仿真硬件点 0；映射点 0；SRAM/解析界剪枝数 0（未执行，而非没有可剪枝点）。没有生成 `hw_grid.csv`、`attainable.csv`、`best_mapping.csv` 或 `k_ablation.csv`。V4 planning 表不是 V5 测量表。
T_min 二分、五点 L(T)、960 请求前沿确认、双模型、priority 场景、解析切片敏感性均未执行；成本/能耗也没有排名。

## 5. 主要结果

本轮仅有协议自检和诊断结果。不能从这些数据推出核数/带宽趋势、最优 k、serial 与 pipeline 优劣，或任何芯片推荐。未输出 V5 双模型一致性或分歧结论。

## 6. 与任务曲面的连接

新增闭环任务局数 0。V4 的 56 个补测计划和旧 33 点汇总原样保留；无 V5 前沿可用于对齐，未伪造联合选型演示。任务环境/版本、checkpoint/hash、各速度预算、注入/adoption/无效局定义仍需外部输入。

## 7. 所有失败、未覆盖和降级项

- 2 KB 与单物理行的饱和 W5 块抽样均失败，完整数据和原生统计保留。
- `selfcheck_input/` 是串行屏障修复前的未执行准备版；实际验收使用 `selfcheck_input_v2/`，两个目录均保留。
- 最初 dev 作业 2046330 因 QOSMaxJobsPerUserLimit 排队，仅取消本轮作业；2046374 因节点资源/预留无法启动后取消。
- enterprise 尝试 2046376 的 4 分片退出码 127：节点本地 `/tmp` 环境不可用，未产生模拟结果；未当成模型失败。Slurm accounting 与日志归档状态保留于 execution/，节点本地 stdout 通过额外 CPU 分配读取，不复制/修改该节点的其他数据。
- 根据 einst 的可用内存把本轮作业降为 4 GiB、单分片并发；2046440 的 4 分片均正常完成。未取消/修改用户其他任务。
- 初始原生驱动探针、修复后探针、所有失败/准备版产物均保留，未删失败组、未用留出调参。
- 全局时间缩放为 1/10，包括块内间隔；饱和容量门禁置零时间戳，因此本次失败不由该开环时间约定解释。
- 新 heldout 的 W1/W3/W4、BG 动态门禁、新 HBM 原生验收、新网格校准和全部 DSE 均未覆盖。pipeline W2、serial W3/W4 应标 N/A；当前只实际执行 serial W5，不拿其他窗口顶替。
- 真实 checkpoint/算子形状、独立捕获、NeuSim 行切片验证、工艺成本及原生优先级仍缺失。当前计算轨道保留估计形状和 SigLIP 回退限制。
- 新网格私有 SRAM 档位尚未测量；现有 NeuSimTiming 不消费 SRAM 容量，因此不能声称已测出其计算时延收益。

## 8. 复现命令与哈希清单

以下原生命令的输出目录必须为空，重新执行请使用新的目录，不覆盖交付。

```sh
.venv/bin/python vlasim/ramulator_bridge/v5_equivalence.py --backend .native/hbm2 --out /tmp/v5_eq_rerun
.venv/bin/python vlasim/ramulator_bridge/v5_selfcheck.py --input results/v5/selfcheck_input_v2 --backend .native/hbm2 --out /tmp/v5_selfcheck_rerun
.venv/bin/python vlasim/ramulator_bridge/v5_sampling_diagnostic.py --backend .native/hbm2 --out /tmp/v5_diag_rerun
.venv/bin/python -m pytest -q --junitxml=results/v5/validation/local_pytest.xml
.venv/bin/python vlasim/v5_report.py
```

einst 实际原生后端在 `/tmp/vlasim_phase4_20261115.Os3Bob/.native/backend`，运行源码、输入哈希、展开 YAML、原始 stats 均在交付分片中。成功 Slurm 作业 2046440 的覆盖参数记录在 `execution/slurm_accounting.txt` 与日志中；基脚本为 `scripts/einst_v5_selfcheck.sh`，提交时覆盖 `--partition=cpu-scavenger --qos=cpu-scavenger --mem=4G --time=00:10:00 --array=0-3%1`。

全量 pytest：201 项通过。V3 的 904 个原交付产物、V4 的 365 个原交付产物哈希全部保持不变。
本轮交付哈希见 `results/v5/delivery_manifest.json`；逐项源文件、规格、输入、后端及驱动身份可追溯。跨平台二进制哈希可以不同，跨主机一致性比较的是相同 YAML/输入下的原生结果。
