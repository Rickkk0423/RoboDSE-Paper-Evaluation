# Evaluation 的正文、逐图数据和新 DSE 消融

生成依据：已完成的新搜索 `results/v9_no_batching_domain/`；冻结 V7 不修改。
当前主结果是硬件模拟证据；没有启动新的 robotic simulator episode。

## 一、正文只保留三个小节

### 5.1 Experimental Setup and Methodology

用一张设置表交代 workload、硬件域、执行域、搜索和证据边界，不占用主结果图。

- Workload：估计的 VLM/DiT 结构，H=16，10 个 denoising steps，权重/activation/KV 均为 2 bytes。不是从验证过的 checkpoint 完整提取的结构。
- 新消融硬件域：9 个 memory/channel 档位 × 8 个核数 × 4 档 shared SRAM × 2 档 private SRAM，共 576 个硬件身份。这不是 576 个实物芯片，也不是原文的 192 个配置口径。
- 核数：1,2,3,4,6,8,12,16；shared SRAM：8,16,32,64 MB；private SRAM：512/2048 KB per core。
- Memory：LPDDR5_c4/c8/c16/c32、HBM2_c8/c16/c32、GDDR6_c16/c24。GDDR6 两档保留 conditional NoRefresh 标记；另报 refreshed-only 敏感性。
- 每个硬件：serial 一组；每个合法 VLM split（1 到 n-1）各跑 k=1、k=2/3 batched、k=2/3 unbatched。单核仅 serial。
- 共 16,416 个配置，4,113 个精确 operation-template 语义，82,070 个通过搜索 gate 的候选身份。等价模板复用不是独立重复试验。
- 原计划 82,080 个配置/period 身份，其中 HBM2_c32 的 10 个身份（3 个独立语义/period 组合）不通过原周期 gate，明确排除，不放宽数值门限；见 `excluded_curve_points.csv`。这不是 960-request 前沿复核失败。
- 每个组织独立搜索 Tmin，不使用 incumbent 剪枝；保留 1/1.1/1.25/1.5/2 倍 Tmin。不是连续 period 域的全局最优证明。
- 480-request 搜索；各比较/敏感性前沿的并集共 510 个身份复核，复用为 132 次 960-request / 192-warmup 检查。失败 0；最大 L/S 相对差 2.11e-11。这检查调度稳态一致性，不校准真实硅片。
- 三组严格嵌套：serial；serial + k1 + unbatched k2/k3；前述全部 + batched k2/k3。无 batching 组仍可重新选硬件、split、k、period，不是把 full 获胜配置简单关掉 batching。
- serial 按 V7 定义 L<=Smax；joint 两组按实际 L<=Lmax 且 S<=Smax。明确这是 serial latency-only reference，而不是允许流水线的另一种 min-L 优化器。
- Box 共 22 个：Lmax∈{100,150,200,250,300}，Smax∈{50,75,100,150,200}，Smax<=Lmax。
- SR 表：33 个聚合点；仅在真正凸包内部线性插值，不能用 L>=100、S>=50 两个下界替代 hull 判断。模型/checkpoint/protocol 元数据未充分核实，无分速度有效局分母。

旧 V7 的 39,928 个候选与新搜索候选数分别报告，不混算；17,992/21,936 的 SR 覆盖统计只属于旧 V7。

### 5.2 Effectiveness of Cross-Chunk Batching

顺序：流量减少 → 同 k 的 L/S 改善 → 跨 k 的延迟/刷新折中 → 高带宽反例。
核心图只有 Fig. E1，三面板。无需用 SR 数字证明这一节。

**主控制硬件**：LPDDR5_c8_c4_s64_p512，102.4 GB/s，4 cores，VLM3/DiT1，shared 64 MB，private 512 KB/core。

| 组织 | DiT GB/req | 总 GB/req | L ms | S ms | SR 插值 % |
| --- | --- | --- | --- | --- | --- |
| k=1 control | 6.407 | 11.188 | 120.554 | 120.538 | 46.757 |
| k=2 batched | 3.293 | 8.074 | 178.164 | 89.073 | 47.277 |
| k=3 batched | 2.670 | 7.451 | 248.481 | 82.848 | 43.963 |
| k=2 unbatched | 6.407 | 11.188 | 241.092 | 120.538 | 45.108 |
| k=3 unbatched | 6.407 | 11.188 | 361.630 | 120.538 | 36.383 |

固定 k 才隔离 batching：k2 off→on，L 241.092→178.164 ms，S 120.538→89.073 ms；k3 off→on，L 361.630→248.481 ms，S 120.538→82.848 ms。
相对 k1，提高 k 则增大 L、减小 S，这是另一种比较。k1 pipeline 不是 independently optimized serial。

DiT 每请求流量减少约 48.6%/58.3%；总 DRAM 流量减少约 27.8%/33.4%。同类型、固定每字节能量系数下，动态 DRAM 能量比为 0.72165/0.66598 左右；不要称整机 power 降低，也不包括背景、刷新或静态能量。

逐轮构成可放补充表，不强塞主图：

| 组织 | compute ms | exposed memory ms | wait ms | cycle ms | DiT busy fraction |
| --- | --- | --- | --- | --- | --- |
| k=1 control | 31.288 | 38.276 | 50.974 | 120.538 | 0.577 |
| k=2 batched | 18.962 | 19.138 | 50.974 | 89.073 | 0.428 |
| k=3 batched | 16.497 | 15.310 | 51.041 | 82.848 | 0.384 |
| k=2 unbatched | 31.288 | 38.276 | 50.974 | 120.538 | 0.577 |
| k=3 unbatched | 31.288 | 38.276 | 50.974 | 120.538 | 0.577 |

busy 表示当前组织的活跃时间占比；每轮处理的工作不同，busy 下降不能单独解释为效率变差。所有流量采用 steady-state 口径，不能混用包含 tail drain 的 full-run 数字。

**反例硬件**：HBM2_c32_c4_s64_p512，1024 GB/s，其余资源与分核同主控制。

| 组织 | L ms | S ms |
| --- | --- | --- |
| k=1 control | 81.537 | 50.260 |
| k=2 batched | 119.470 | 50.260 |
| k=3 batched | 167.265 | 50.260 |
| k=2 unbatched | 131.797 | 50.260 |
| k=3 unbatched | 182.057 | 50.260 |

该反例 exposed memory 约为零，S 保持约 50.260 ms。流量减少不保证刷新变快，因此要由 DSE 联合选择，而不能一律提高 k。

### 5.3 Task-Aware Hardware-Resource Exploration

先呈现 Fig. E2 的三组硬件 DSE，再在同一小节末尾用 Fig. E3 解释 task-space projection。不另设一个重复的第四节。

第一段：新 no-incumbent-pruning 消融为主证据，旧 retained/matched-support 结果放附录说明历史覆盖问题。

| 比较 | 有严格支配改善 | 前沿扩展 | 前沿相同 |
| --- | --- | --- | --- |
| no_batching vs serial | 0 | 0 | 22 |
| full vs no_batching | 5 | 3 | 14 |
| full vs serial | 5 | 3 | 14 |

“strictly better”的实现含义是：新前沿至少有一个向量严格支配旧前沿的一个向量；不是新前沿每一点都支配旧前沿所有点。相同前沿按资源向量集合判断，映射/SRAM ties 保留。

第二段：用具体前沿解释不同收益类型，不只报汇总计数。

| Box ms | 搜索组 | (核数, GB/s) 非支配向量 |
| --- | --- | --- |
| (200, 50) | serial | (4, 1024); (6, 409.6); (8, 256) |
| (200, 50) | no_batching | (4, 1024); (6, 409.6); (8, 256) |
| (200, 50) | full | (4, 1024); (6, 256); (8, 204.8) |
| (200, 100) | serial | (2, 409.6); (3, 204.8) |
| (200, 100) | no_batching | (2, 409.6); (3, 204.8) |
| (200, 100) | full | (2, 409.6); (3, 204.8); (4, 102.4) |
| (250, 150) | serial | (2, 102.4) |
| (250, 150) | no_batching | (2, 102.4) |
| (250, 150) | full | (2, 102.4) |

同核带宽下降、同带宽核数下降各自给 matched-resource 条件。Box(200,100) 的 4 核 102.4 GB/s 对 3 核 204.8 GB/s 是带宽减半且多一核，不是整体严格资源支配；Box 约束相同不等于任务成功率相同。

第三段：放 Fig. E3 的边界明确的任务投影。主控制 SR 插值约 46.757%、47.277%、43.963%（k1/k2/k3 batched）。k2 对 k1 为 +0.520 个百分点，只作固定分核轨迹的条件诊断；不是实测增益，也不是相对最优 serial 的 DSE gain。
49.85% 是实测网格 (200,100) 点，不能贴给 (178.164,89.073) 硬件点。既有 264 组 matched-hardware 比较的最小延迟 serial 基线均不在有效 hull 内，因此 abstain。不要为获取插值结果换成更慢 serial。

第四段：面积和压力测试放简短限制段/附录。中心文献系数下旧 V7 严格降低最优总面积 0/22；旧压力场景达到 >=80% 可行比例的严格改善 memberships 为 0/344。这两个统计未在本次新域上重跑，不能冒充新域结果；80% 是确定性场景比例，不是成功概率。

## 二、每张图的具体编辑方式

### Fig. E1：Batching reduces traffic and enables timing tradeoffs

- (a) stacked bar：横轴五种组织 k1、k2 on、k3 on、k2 off、k3 off；纵轴 DRAM GB/request，从零开始。下段 VLM 恒 4.781459456，上段 DiT；标注总量 11.188/8.074/7.451/11.188/11.188。数据 `E1a_LPDDR5_traffic.csv`。
- (b) L-S scatter/trajectory：横轴 L（0–400 ms），纵轴 S（0–150 ms）；点旁标 k，颜色区分 batch on/off。标注 k1→k2 时 S -26.1%、L +47.8%；固定 k on/off 用细虚线配对。Box(200,100) 的边界可以用灰虚线，不涂成 success 区域。数据 `E1b_LPDDR5_timing.csv`。
- (c) 高带宽反例：横轴 L（0–200 ms），纵轴 S（0–100 ms），五点均约在 S=50.26。无需再画同样流量柱。数据 `E1c_HBM2_timing.csv`。
- 样式：批处理与无批处理颜色全篇统一，k1 中性符号。小字号标明 fixed HW + allocation；不加 SR 标题。
- Caption 主句：At fixed hardware and core allocation, batching reduces DiT traffic and improves L and S relative to unbatched execution at matched k; increasing k trades latency for refresh rate, with no refresh gain in the VLM-limited control.
- 另一套 102.4 GB/s、8 核硬件控制仍在 `E1_all_controls.csv`，用于补充材料，不必主图全部铺开。

### Fig. E2：DSE-level batching ablation and hardware frontiers

- (a) 22-box 矩阵：列 Lmax、行 Smax，Smax>Lmax 留空，不能画成失败；色彩表示 full vs no batching 的 identical/extension/strict-improvement。附三组比较汇总。数据 `E2a_22box_three_arm.csv`。
- (b) Box(200,50)：横轴 core count，纵轴 peak bandwidth（GB/s），三组分别画非支配点。标同核带宽减少或同带宽核数减少，用导出前沿实际数值，不从旧图抄点。
- (c) Box(200,100)：相同坐标轴，标出新增的 (4,102.4) 与基线 (3,204.8)/(2,409.6)，用“bandwidth/core tradeoff”说明。数据 `E2b_box200_50_frontiers.csv` / `E2c_box200_100_frontiers.csv`。
- serial 与 no batching 重合时用空心/实心不同符号或明确注释，不让较后绘制的曲线遮盖证据。连接线只作视觉引导，不代表离散设计之间可插值。
- GDDR6 点用空心条件标记；refreshed-only 和 3D SRAM 比较在 `E2_sensitivity_all.csv`。2D 资源相等并不保证 SRAM 相等。
- Caption 必须写 fresh unpruned enumeration over retained hardware domain，避免继续标成 frozen-retained filtering；960 检查只保证本模拟器一致性。

### Fig. E3：Bounded task-space projection (not closed-loop validation)

- (a) 原始 33 点叠加三角插值 SR surface，L 横轴、S 纵轴，只在真实 hull 内填色。主轨迹放 k1/k2/k3，off 的两点可用较浅符号对照。可放大 L 0–500、S 0–250 的主要窗口，但必须说明是 crop，不是全表范围。原始表 `E3a_measured_grid.csv`。
- (b) 五种组织对应 SR 表或点图，列出 46.757/47.277/43.963/45.108/36.383%；无 trial-level 数据，不画伪造误差条。数据 `E3b_projected_SR.csv`。
- (c) 小覆盖表/图注：旧 V7 17,992 inside /21,936 outside，总 39,928；264 组最优 serial 对比全部 abstain。不是新消融候选覆盖率。数据 `E3c_frozen_V7_coverage.csv`。
- 不命名 overall in-loop SR。未来真的跑 matched-protocol robotic rollout 后再替换为闭环比较，目前保留为次要解释性证据。

## 三、22 个 Box 的新消融明细

| Lmax | Smax | full vs no batching | 无 batching 前沿向量数 | full 前沿向量数 |
| --- | --- | --- | --- | --- |
| 100 | 50 | task_strictly_better | 3 | 3 |
| 100 | 75 | identical | 2 | 2 |
| 100 | 100 | identical | 2 | 2 |
| 150 | 50 | task_strictly_better | 3 | 3 |
| 150 | 75 | identical | 2 | 2 |
| 150 | 100 | identical | 2 | 2 |
| 150 | 150 | identical | 1 | 1 |
| 200 | 50 | task_strictly_better | 3 | 3 |
| 200 | 75 | identical | 2 | 2 |
| 200 | 100 | task_extends | 2 | 3 |
| 200 | 150 | identical | 1 | 1 |
| 200 | 200 | identical | 2 | 2 |
| 250 | 50 | task_strictly_better | 3 | 3 |
| 250 | 75 | identical | 2 | 2 |
| 250 | 100 | task_extends | 2 | 3 |
| 250 | 150 | identical | 1 | 1 |
| 250 | 200 | identical | 2 | 2 |
| 300 | 50 | task_strictly_better | 3 | 3 |
| 300 | 75 | identical | 2 | 2 |
| 300 | 100 | task_extends | 2 | 3 |
| 300 | 150 | identical | 1 | 1 |
| 300 | 200 | identical | 2 | 2 |

## 四、论文主张和执行边界

可写：cross-chunk batching reduces modeled DiT traffic; the fresh DSE ablation quantifies how batching changes resource frontiers under joint latency/refresh constraints.

暂不能写：improves measured task success by xx pp at the same area，reduces chip area by xx% at matched success，或 validated in-loop hardware recommendation。

建议 Introduction 第三条：

> We use RoboDSE to jointly explore hardware resources and execution organizations. Controlled ablations quantify the traffic and timing benefits of cross-chunk batching, and resource-frontier comparisons show when these benefits enable lower-bandwidth or lower-core-count designs under joint latency and refresh constraints.

剩余闭环验证暂缓：冻结具体 design → 取得其 L/S → 在相同 observation/acquisition、chunk alignment/adoption 和 action-coverage 协议下注入 robotic simulator → 逐局测 SR，和预先选定的最优 serial 及资源参考设计对比。不能只延迟动作输出而改变观察采集语义。

## 五、文件及复现

- 新实验原始证据：`results/v9_no_batching_domain/shards/*/runs/*/requests.npz`。
- 原始前沿复核：`results/v9_no_batching_domain/checks960/`。
- 配置全集、候选全集、逐 Box 前沿、比较、checks、源文件哈希均位于新实验目录。
- 运行：`.venv/bin/python scripts/run_no_batching_domain.py --workers 4`。
- 本说明/图源数据：`.venv/bin/python scripts/document_evaluation_data.py`。
- 旧 `results/v7/`、旧 `v8_no_batching_case_final/` 均未覆盖。新报告不撤销旧报告，而是用更完整、无 incumbent 剪枝的域推进其证据覆盖。
