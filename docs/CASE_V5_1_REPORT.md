# V5.1 执行总报告

报告日期：2026-11-16（本轮工作区日期，与输入规格日期一致）；早期执行归档记录的洛杉矶日期为 2026-11-15。
所有结果位于 `results/v5_1/`。旧 V3/V4/V5 数据与报告未覆盖。
本轮是估计 checkpoint 形状、显式 SigLIP 解析回退、原生 DRAM 校准的模型研究，不是实际机器人或芯片测量。

## 1. 门禁总表

- 步骤 1：10 档分别完成阶梯自检，无 L3；完整周期大容量 HBM 验收通过；所选原生及周期内核跨主机对照均无差异（不声称全网格跨主机重跑）。
- 步骤 2：开发集 A=False、B=False，选择 A；冻结新留出后门禁为 `dual_model_DRAM_unvalidated`。
- 留出饱和逐流平均误差 11.6803%，最大 49.6809%；BG 主口径资格=False。
- 步骤 3：10 档原生校准完成；步骤 4：640 个硬件身份完成，前沿执行 960 请求原 Python 调度器复查。
- “原生校准完成”不是逐流模型通过：新增各档 VLA 拟合平均误差 plain=20.512%、BG=28.667%，残差仍大，不能把这些参数解释为已验证的通用器件混流效率。
- 独立归档审计通过：248 次完整原生回放的统计/计数/输入哈希均一致；未完成尝试不冒充完成结果。
- 任务侧仅准备：新闭环实测 0 局；面积、能耗均为空，不做成本或芯片推荐。

| memory | block_bytes | level | ratio | eta_seq |
| --- | --- | --- | --- | --- |
| LPDDR5_c4 | 8192 | 1 | 0.927457393 | 0.96810695 |
| LPDDR5_c8 | 16384 | 1 | 0.930213214 | 0.966579157 |
| LPDDR5_c16 | 32768 | 1 | 0.96083446 | 0.915051662 |
| LPDDR5_c32 | 1048576 | 2 | 0.990251999 | 0.814962197 |
| GDDR6_c16 | 524288 | 2 | 1.026278217 | 0.825147792 |
| GDDR6_c24 | 786432 | 2 | 1.10550019 | 0.688004691 |
| GDDR6_c36 | 1179648 | 2 | 1.019514588 | 0.626140724 |
| HBM2_c8 | 524288 | 2 | 1.040038388 | 0.932286332 |
| HBM2_c16 | 1048576 | 2 | 1.005610294 | 0.876524716 |
| HBM2_c32 | 2097152 | 2 | 0.972584453 | 0.543885274 |

## 2. DRAM 模型

开发集包括 V4 饱和 W3/W4 与原配置不同时间的新增窗口，并增加不与留出重叠的 GDDR 开发配置。A 每种内存/布局一个常数；B 使用精确发射序列每次切流前连续字节数的 log2 特征。两种都未全过开发门槛时保留较简单 A，明确失败，不用留出调参。
原生按字节份额合并发射；流体模型 max-min fair。二者的逐流仲裁不同，残差不应一概解释为 DRAM 时序误差。
| group | eta_mix | mean_pct | max_pct |
| --- | --- | --- | --- |
| GDDR6_bg | 0.730969 | 22.9228 | 29.0802 |
| GDDR6_plain | 0.541025 | 18.3769 | 25.7926 |
| HBM2_bg | 1.025973 | 0.7804 | 0.7925 |
| HBM2_plain | 0.858082 | 2.3193 | 3.2066 |
| LPDDR5_bg | 1.052331 | 1.6278 | 2.0013 |
| LPDDR5_plain | 0.798246 | 0.0044 | 0.0044 |

完整逐流误差见 `development_metrics.csv`、`heldout_metrics.csv`；按窗口/内存/发射分组如下。
| dataset | standard | window | launch | flows | mean_pct | max_pct |
| --- | --- | --- | --- | --- | --- | --- |
| development | GDDR6 | W3 | saturated | 8 | 22.9004 | 29.0802 |
| development | GDDR6 | W4 | saturated | 8 | 18.3993 | 28.8233 |
| development | HBM2 | W3 | saturated | 6 | 2.3746 | 2.9303 |
| development | HBM2 | W4 | saturated | 12 | 1.5222 | 3.2066 |
| development | LPDDR5 | W4 | saturated | 14 | 1.164 | 2.0013 |
| heldout | GDDR6 | W1 | open | 1 | 0.0031 | 0.0031 |
| heldout | GDDR6 | W1 | saturated | 1 | 5.707 | 5.707 |
| heldout | GDDR6 | W3 | open | 2 | 0.0059 | 0.0082 |
| heldout | GDDR6 | W3 | saturated | 2 | 32.4636 | 32.4659 |
| heldout | GDDR6 | W4 | open | 2 | 0.0033 | 0.0034 |
| heldout | GDDR6 | W4 | saturated | 2 | 34.6649 | 34.665 |
| heldout | GDDR6 | W5 | open | 2 | 0.0233 | 0.029 |
| heldout | GDDR6 | W5 | saturated | 2 | 11.2655 | 17.4449 |
| heldout | HBM2 | W1 | open | 2 | 0.0482 | 0.0486 |
| heldout | HBM2 | W1 | saturated | 2 | 2.725 | 2.7344 |
| heldout | HBM2 | W3 | open | 2 | 7.7766 | 7.7767 |
| heldout | HBM2 | W3 | saturated | 2 | 7.8222 | 7.8395 |
| heldout | HBM2 | W4 | open | 4 | 0.0235 | 0.0526 |
| heldout | HBM2 | W4 | saturated | 4 | 3.1435 | 4.2318 |
| heldout | HBM2 | W5 | open | 6 | 9.5915 | 17.9453 |
| heldout | HBM2 | W5 | saturated | 6 | 8.0295 | 19.8345 |
| heldout | LPDDR5 | W1 | open | 2 | 0.0147 | 0.0192 |
| heldout | LPDDR5 | W1 | saturated | 2 | 0.6522 | 1.1828 |
| heldout | LPDDR5 | W3 | open | 2 | 0.0125 | 0.013 |
| heldout | LPDDR5 | W3 | saturated | 2 | 13.369 | 13.3695 |
| heldout | LPDDR5 | W4 | open | 4 | 0.014 | 0.0194 |
| heldout | LPDDR5 | W4 | saturated | 4 | 5.3953 | 9.455 |
| heldout | LPDDR5 | W5 | open | 6 | 12.3593 | 36.6995 |
| heldout | LPDDR5 | W5 | saturated | 6 | 19.141 | 49.6809 |

抽样各级实际结果如下；L1通过的配置未额外执行L2，未列出的级别不是失败。
| memory | level | block_bytes | ratio | passed |
| --- | --- | --- | --- | --- |
| LPDDR5_c4 | 1 | 8192 | 0.927457393 | True |
| LPDDR5_c8 | 1 | 16384 | 0.930213214 | True |
| LPDDR5_c16 | 1 | 32768 | 0.96083446 | True |
| LPDDR5_c32 | 1 | 65536 | 0.79671699 | False |
| LPDDR5_c32 | 2 | 1048576 | 0.990251999 | True |
| GDDR6_c16 | 1 | 32768 | 0.875801215 | False |
| GDDR6_c16 | 2 | 524288 | 1.026278217 | True |
| GDDR6_c24 | 1 | 49152 | 0.831596167 | False |
| GDDR6_c24 | 2 | 786432 | 1.10550019 | True |
| GDDR6_c36 | 1 | 73728 | 0.623984713 | False |
| GDDR6_c36 | 2 | 1179648 | 1.019514588 | True |
| HBM2_c8 | 1 | 8192 | 0.859055906 | False |
| HBM2_c8 | 2 | 524288 | 1.040038388 | True |
| HBM2_c16 | 1 | 16384 | 0.801522837 | False |
| HBM2_c16 | 2 | 1048576 | 1.005610294 | True |
| HBM2_c32 | 1 | 32768 | 0.705873773 | False |
| HBM2_c32 | 2 | 2097152 | 0.972584453 | True |

块跨度：物理 bank 行字节数=(Column/prefetch)×native32；L1=行字节数×channels；L2=L1×行前 rank/SID/pseudochannel/BG/bank 域数。MOP4CLXOR 通道剥离后的位序为 column_low_2、行前域、其余 column、row；XOR 还包含 Row，不能把 L2 说成“一个物理行”。所有 L1 失败及 L2 结果均保留在 `selfcheck_remote/` 和 `selfcheck_retry_remote/`。
抽样保留每十块中的一整块，地址不压缩、时间/10；饱和置零；serial 的 VLM→DiT 仍等待所有回调排空。

大容量HBM2_c8验收：三种seq粒度效率为 [0.932286332081484, 0.932286332081484, 0.9586892919836162]；与V3基准的相对差异为 1.729266%，低于3%。16GiB新容量身份仍单独保留；完整周期块抽样W5（含BG映射）原生回放完成，全部物理地址通过容量检查。

## 3. 校准表

每档 seq 3 粒度 + VLA 普通/BG 各 25/50/75，以及新身份的 legacy 普通/BG 各三比例；均为原生测量，不插值。V3 器件身份完全相同的 LPDDR 档保留原 V3 参数作双模型基线；新身份采用“V3 模型形式重新测量”，不能称为原 V3 结果。
VLA 的 A 常数对三个比例的逐流完成时间做最小二乘；V3-form 新身份基线严格用 50:50 总吞吐/顺序带宽。原生 FRFCFS 不保证流体 fair 份额，因此校准残差仍可能较大，完整残差在 `calibration_metrics.csv`，未据此宣称逐流验证通过。
| layout | flows | mean_error_pct | max_error_pct |
| --- | --- | --- | --- |
| vla_plain | 60 | 20.5117 | 30.7837 |
| vla_bg | 60 | 28.6666 | 37.0024 |

| memory | peak_GBps | capacity_GiB | eta_seq | mix_plain | mix_bg | mapper | seq_gate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LPDDR5_c4 | 51.2 | 8.0 | 0.968107 | 0.56513 | 0.632127 | MOP4CLXOR | True |
| LPDDR5_c8 | 102.4 | 8.0 | 0.966579 | 0.566965 | 0.634136 | MOP4CLXOR | True |
| LPDDR5_c16 | 204.8 | 16.0 | 0.915052 | 0.555134 | 0.658955 | MOP4CLXOR | True |
| LPDDR5_c32 | 409.6 | 32.0 | 0.814962 | 0.448389 | 0.652304 | MOP4CLXOR | False |
| GDDR6_c16 | 448.0 | 8.0 | 0.825148 | 0.4669 | 0.652758 | MOP4CLXOR | False |
| GDDR6_c24 | 672.0 | 12.0 | 0.688005 | 0.419414 | 0.738108 | MOP4CLXOR | False |
| GDDR6_c36 | 1008.0 | 18.0 | 0.626141 | 0.346126 | 0.71381 | MOP4CLXOR | False |
| HBM2_c8 | 256.0 | 16.0 | 0.932286 | 0.554466 | 0.669251 | MOP4CLXOR | True |
| HBM2_c16 | 512.0 | 32.0 | 0.876525 | 0.47868 | 0.661983 | MOP4CLXOR | True |
| HBM2_c32 | 1024.0 | 64.0 | 0.543885 | 0.449717 | 0.64286 | MOP4CLXOR | False |

seq 任一效率低于 .8 的失败组保留；替代 ChRaBaRoCo 的三粒度实测比较也保留，未用未执行的映射修正数值。大容量 HBM 的新旧 η_seq 比较与容量原生检查见 `gates.json` 和对应校准文件。
GDDR6 使用固定后端的 14Gbps double-rate 时序及 NoRefresh（与其 smoke 配置一致）；真实刷新影响未验证。24/36 通道采用独立 clocked 单通道实例与双射通道解复用，不做容量取模；6 组聚合/独立实例比较完全一致。

## 4. DSE 规模与剪枝

- 640 硬件点：8 核数×10 内存档×4 共享 SRAM×2 私有 SRAM；映射/场景/模型合计 291,840 行。
- 状态计数：`{"bracket_found": 130336, "lower_bound_pruned": 161504}`。唯一语义完整执行 34,255，五点曲线行 651,680。
- 每一映射包含 serial 或全部 VLM:DiT 分配、k1/2/3 合批及 k2/3 不合批；fair 主口径，priority 独立未验证场景；解析切片独立敏感性组。
- 仅同硬件/模型/计算轨道/策略/布局内按解析下界排序；LB>1.2×当前最优的映射标记剪枝，未伪造其时间。
- 可达前沿是按指定吞吐下界剪枝后保留候选的前沿；该剪枝不保证保留所有较慢周期下的低 L 映射，故不是全映射的全局 Pareto 最优证明。
- 私有 SRAM 512/2048KB 均通过现有静态最小 tile 检查；现有 provider 不因私有容量改变时延，故复用完全相同模板但保留两种物理身份。
- 所有搜索失败试点及逐请求时间保存在分片 `requests.npz`；五个曲线点保存全部轮分解；每分片落盘并带哈希。
- 交付前重新打开 34,575 个语义执行归档，核对原始哈希、请求时间顺序及 83,182,875 个曲线轮的两套时间分解。
- 960 请求原 Python 前沿复查覆盖 13,562 项，对应 7,753 次唯一原调度器运行；相同操作模板/DRAM/策略/周期的硬件身份精确复用并留源身份，未计作重复运行。门禁失败前沿 0。
- 唯一执行归档共保存 356,405 个二分/扩展试点，其中失败 186,241 个；观察到非单调搜索 0 组，五点曲线门禁失败 46 点，全部保留。

## 5. 主要结果

下表仅汇总新模型、NeuSim unsliced、fair、符合主口径资格的前沿。L_ms_min与S_ms_min是分别取的极小值，不能拼成同一个可达点。不是硬件推荐；不同核心数/SRAM 的完整变化见 `attainable.csv`。
| memory | frontier_points | L_ms_min | S_ms_min | frontier_k_counts |
| --- | --- | --- | --- | --- |
| LPDDR5_c4 | 128 | 225.081 | 150.347 | {'serial': 16, '3': 56, '2': 56} |
| LPDDR5_c8 | 120 | 116.119 | 75.301 | {'serial': 24, '3': 48, '2': 48} |
| LPDDR5_c16 | 126 | 60.059 | 39.77 | {'serial': 40, '3': 48, '2': 38} |
| LPDDR5_c32 | 118 | 33.344 | 23.15 | {'serial': 64, '3': 30, '2': 24} |
| GDDR6_c16 | 120 | 30.15 | 21.398 | {'serial': 64, '3': 32, '2': 24} |
| GDDR6_c24 | 112 | 24.19 | 19.258 | {'serial': 64, '3': 24, '2': 24} |
| GDDR6_c36 | 88 | 19.705 | 17.781 | {'serial': 64, '3': 16, '2': 8} |
| HBM2_c8 | 142 | 46.886 | 31.341 | {'serial': 48, '3': 48, '2': 46} |
| HBM2_c16 | 120 | 24.908 | 19.47 | {'serial': 64, '3': 32, '2': 24} |
| HBM2_c32 | 120 | 21.078 | 18.328 | {'serial': 64, '3': 32, '2': 16, '1': 8} |

![各内存档离散可达前沿](../results/v5_1/figures/frontiers.png)

新模型主口径的硬件/S目标可达查询中，最低 L 映射计数为 `{'serial': 1512, 'k2': 336}`。同一硬件会出现在多个目标中，计数不是独立硬件数；不可达目标不计入。
新模型 plain、fair、unsliced 的 368 个可比较硬件身份中，保留 pipeline 的最低 Tmin 小于 serial 的有 246 个。这是各自 Tmin 下的吞吐对照，不是同 S 下的延迟胜负。

同分配实例：LPDDR5 8通道、8核、64MB共享、512KB私有。下表稳态流量和busy取各k自己的Tmin；核分配split表示VLM核数，其余核给DiT。该实例只说明流量、吞吐和延迟可以朝不同方向变化。
| k | split | Tmin_ms | L_ms | DiT_GB_req | DiT_busy_pct | compute_ms | exposed_ms | wait_before_ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 4 | 113.0428 | 113.0398 | 6.406963 | 57.263 | 7.8221 | 56.9093 | 48.3114 |
| 2 | 4 | 81.6506 | 163.2261 | 3.292692 | 40.743 | 4.7405 | 28.5265 | 48.3836 |
| 3 | 4 | 75.3008 | 225.8842 | 2.669838 | 35.822 | 4.1242 | 22.85 | 48.3267 |

![同核分配k消融](../results/v5_1/figures/k_controls.png)

`best_mapping.csv` 给出每硬件 S≤50/100/150/200ms 的最低 L 或明确不可达；`k_ablation.csv` 在各档最优合批 Tmin 的核分配上单独跑齐 k1/2/3 合批和 k2/3 不合批控制。这些消融即便在优化搜索中被剪枝也单独执行，不回填为优化候选；单核无 pipeline 则明确 N/A。`compute_report.json` 汇总同分配流量、busy 与轮构成。若全部 pipeline 分配在优化搜索中被剪枝，补充控制组选最小解析下界的分配，不把“未执行”误说成“不可行”。每行含 DiT/总流量、KV 带宽、组 busy 和轮 compute/exposed-memory/linear/attention/wait，不能把少读权重直接等同为低延迟。
其中 `dit_GB_per_req` 与 `vlm_busy/dit_busy` 是含暖机/排空的整批口径；`steady_*` 为稳定测量区间口径。轮等待在轮 duration 之外，compute+exposed-memory 与 linear+attention 各自对账为轮 duration。
busy 是组有在途操作的时间比例，包含 DRAM 等待，不是有效 MAC 利用率；轮前等待可能来自周期到达或 VLM 供料节奏，不作唯一根因归因。
前沿与 S 目标查询只比较已留存映射的五个离散周期点，不做连续插值或全局最优声明。图中连线仅帮助观察离散点趋势。
`sensitivity_core_bandwidth.csv` 在固定 64MB/512KB 下按内存和核数分别给最小 S、该点 L、最小 L、该点 S，不能把两个单独极值拼成一个可达点。`serial_pipeline_comparison.csv` 另列最小 Tmin 对照，并区分“单核不适用”和“全部 pipeline 被优化剪枝”。
静态 SRAM 模型中，k1 pipeline 同时保留 KV 与 VLM activation 需 69.386MB，高于网格最高 64MB；因此本轮 pipeline 的共享 SRAM 增大不自动带来 KV 全驻留。serial 对应需 33.702MB。这是现有估计形状与保守静态 live-KV 公式的结果，不是实测生命周期。
双模型有 1848 个共同可达硬件/目标对，最优映射一致 1848；完整一致及分歧映射见 `dual_model_agreement.json`，不混合取最有利参数。

## 6. 与任务曲面的连接

旧 33 点仅跑通“任务曲面×可达前沿”流程；凸包外严格返回无覆盖，不外推。示例输出 `task_preparation/joint_selection_demo.csv` 明确为流程演示，非结论。
原 V4 的 56 个补测点已与实际前沿对齐，`suggested_measurements.csv` 给出距离及未覆盖优先级；速度档、预算、checkpoint、环境、注入/adoption/无效局协议仍缺失，不填常数、不运行任务。

## 7. 所有失败、未覆盖与降级

- 原 V5 的 2KB 失败及诊断原封不动；V5.1 各档 L1 失败、低 seq、替代 mapper 失败均保留。
- HBM 原并发分片 OOM，按 %1 重试；一次为便于 backfill 缩至4分钟后超时，再以10分钟成功。本机一次误用不存在 backend 路径、远端一次遗漏模块传输均保留错误，不解释成模型失败。
- 留出逐窗口不可运行项/N/A/容量项见 `heldout_gate.json.unavailable`；pipeline W2、serial W3/W4 明确不适用。
- GDDR6_c16的BG留出k2配置，W5在open和saturated两种发射下均因映射后超出8GiB物理容量而未执行；40条原生留出完成、2条容量缺口，不能用plain自检通过替代该BG窗口。
- 开发窗口缺口见 `development_input/manifest.json.unavailable`；未选作留出的 BG 档明确标记无布局留出，不借用其他配置的 W5 代替。抽样协议自检与模型误差验收分开列。
- 开发/留出门禁、GDDR刷新、priority 原生控制器、NeuSim行切片、真实checkpoint形状、SigLIP完整算子、向量/norm、工艺成本、独立执行捕获、真实闭环环境均不得因 DSE 跑完而宣称已验证。
- Tmin 是 0.1ms 精度有限请求窗口的观察到的可行上端点，不是无限时间稳定性证明；SRAM 检查仍是原静态模型。

## 8. 复现命令与哈希

```sh
PYTHONPATH=vlasim .venv/bin/python vlasim/v51_workflow.py stage1
PYTHONPATH=vlasim .venv/bin/python vlasim/v51_workflow.py prepare-dev
# 已冻结目录不可覆盖；重跑时使用新目录，原生 Slurm 参数见 execution/
PYTHONPATH=vlasim .venv/bin/python vlasim/v51_workflow.py fit
PYTHONPATH=vlasim .venv/bin/python vlasim/v51_workflow.py prepare-heldout
PYTHONPATH=vlasim .venv/bin/python vlasim/v51_remote.py heldout
PYTHONPATH=vlasim .venv/bin/python vlasim/v51_workflow.py heldout-gate
PYTHONPATH=vlasim .venv/bin/python vlasim/v51_calibration.py prepare
PYTHONPATH=vlasim .venv/bin/python vlasim/v51_remote.py calibration
PYTHONPATH=vlasim .venv/bin/python vlasim/v51_calibration.py collect
PYTHONPATH=vlasim .venv/bin/python vlasim/v51_dse.py --workers 4
PYTHONPATH=vlasim .venv/bin/python vlasim/v51_ablation.py
PYTHONPATH=vlasim .venv/bin/python vlasim/v51_package.py
PYTHONPATH=vlasim .venv/bin/python vlasim/v51_figures.py
PYTHONPATH=vlasim .venv/bin/python vlasim/v51_audit.py --dse
.venv/bin/python -m pytest -q --junitxml=results/v5_1/validation/zz_final_pytest.xml
PYTHONPATH=vlasim .venv/bin/python vlasim/v51_report.py
```

| file | tests | failures | errors | skipped |
| --- | --- | --- | --- | --- |
| stage1_complete.xml | 283 | 0 | 0 | 0 |
| stage1_pytest.xml | 278 | 0 | 0 | 0 |
| stage1_pytest_bg_fix.xml | 283 | 0 | 0 | 0 |
| stage2_complete.xml | 291 | 0 | 0 | 0 |
| stage2_development.xml | 290 | 0 | 0 | 0 |
| stage2_pre_gate.xml | 291 | 0 | 0 | 0 |
| stage3_complete.xml | 293 | 0 | 0 | 0 |
| stage3_final.xml | 293 | 0 | 0 | 0 |
| stage4_implementation.xml | 295 | 0 | 0 | 0 |
| stage4_prepackage_pytest.xml | 297 | 0 | 0 | 0 |
| zz_final_pytest.xml | 297 | 0 | 0 | 0 |

旧交付已逐一校验：[('results/case_v3_complete/delivery_manifest.json', 904), ('results/v4/delivery_manifest.json', 365), ('results/v5/delivery_manifest.json', 237)]。新产物、源码、后端身份及本报告哈希在 `delivery_manifest.json`；逐阶段作业ID、退出码和重试在 `execution/`。
