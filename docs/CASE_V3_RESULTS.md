# Case v3：P0 执行与诊断结果

更新：本文保留当时 104 次原生实验的历史状态。后续主扫描、全部五组消融、
新增隔离测试、反例与长窗口复查已执行，完整汇报见 `CASE_V3_FULL_RESULTS.md`；
规范入口为 `results/case_v3/`，完整证据为 `results/case_v3_complete/`。

实际执行日期：2026-11-15（America/Los_Angeles）。输入规格
`/Users/mr.meeseeks/Downloads/CASE_V3_SPEC.md` 标注日期为 2026-11-16；
归档保留原件和 SHA-256，没有改写其日期或预期值。

**状态：已完成 P0 原配置实验与两轮诊断，共 104 次原生运行。
完整主网格、五组主 case 消融和 Pareto 前沿尚未执行。**
本轮定位了低效率的实际影响因素，但仍有 P0 和计算映射门禁，不能将诊断候选
直接作为整份规格已经完成的证据。

## 1. 非阻塞前端已实现并执行

`channel_frontend.py` 将原生事务按实际 `CacheLineInterleave` 通道位解码入队，
每通道内部保持 FIFO，通道间 round-robin。通道拒绝时仅跳过该通道，
同周期可继续向其他通道发射。全局 outstanding=512、事务=32 B、FRFCFS/Open
保持不变，原始发射宽度=8；宽度 16/32 仅在明确标记的诊断中改变。
队列存放已提供的微基准事务，本实现没有假装模拟有限容量的片上发射缓存。

前端版本：`per-channel-fifo-rr-v1`。回归测试检查拒绝旁路、通道内顺序、
时间戳、读写标记、outstanding 限制、事务对账和 cycle-budget 失败语义。

相同 4 MiB 流量、原 `RoBaRaCoCh` 映射下，HBM2 新旧前端结果：

| seq 粒度 | 旧全局 FIFO GB/s | 新通道队列 GB/s | 新效率 |
| --- | ---: | ---: | ---: |
| 4 KiB | 135.278 | 135.278 | 52.843% |
| 64 KiB | 132.536 | 132.536 | 51.772% |
| 1024 KiB | 132.914 | 132.914 | 51.920% |

三组结果相同，且这些新前端顺序流没有跨通道拒绝旁路周期。
因此在这些受控顺序流上，**不能把原来约 52% 的效率主要归因于全局 FIFO**。
这不等于证明全局 FIFO 对任意混合或不均衡负载均无影响。

## 2. 原配置 P0 与目标内存

固定快照支持 LPDDR5，无 LPDDR5X 预设。使用现有 LPDDR5-6400 x16、
8 Gb/通道组织与 PerBank 刷新，不虚构 8000 速率或加宽非标准通道。

| 规格名称 | 实际标准 / 通道 | 实际峰值 GB/s | 原映射 seq 效率范围 | 三组均 ≥80% |
| --- | --- | ---: | ---: | --- |
| M-H256 | HBM2 / 8 | 256.0 | 51.772%–52.843% | 否 |
| M-L256 | LPDDR5 / 16 | 204.8 | 68.577%–77.083% | 否 |
| M-L512 | LPDDR5 / 32 | 409.6 | 47.472%–48.541% | 否 |

名称中的 256/512 是规格目标名，不是本次 LPDDR 实际带宽。两种 LPDDR 配置
均比目标低 20%，不能将其与 HBM 的差异归为同带宽内存类型的纯对照。
每种内存已执行 seq×3、mix25/50/75；输出原配置 `dram_v3_<name>.json`，
门禁失败被保留，没有覆盖或升级既有 v2 校准。

预先冻结的验收口径要求三个 seq 粒度全部达到 80%，不以中位数隐藏失败点。
若只看 1024 KiB 粒度，后述高带宽 LPDDR/新映射/宽度16 已达 80.353%，
但 64 KiB 仍失败，两者在报告中明确区分。

## 3. 低效率诊断

在 HBM2 原映射的 seq_1024KB 上：

| 改变项 | GB/s | 判断 |
| --- | ---: | --- |
| 基线，刷新开启，512 outstanding，宽度8 | 132.914 | 参照 |
| 仅禁用刷新 | 134.298 | 约 +1.04%，不能解释到80%的缺口 |
| 仅映射改为 ChRaBaRoCo | 49.584 | 更差，映射确实重要 |
| 仅 outstanding=128 | 71.540 | 限制更紧会退化 |
| 仅 outstanding=1024 / 2048 | 132.914 / 132.914 | 增大上限没有修复 |
| 仅发射宽度16 / 32 | 132.846 / 132.851 | 增大发射宽度没有修复 |
| 映射改为 MOP4CLXOR，其余保持基线 | 241.867 | 达到94.479% |

事务粒度由原生设备和 ABI 双重核对，均为 32 B；64 B 逻辑请求拆成两个事务。
没有把 64 B 伪装成原生 payload 来抬高吞吐。原配置控制器平均 read queue
接近其 32 项容量，但这不是单凭计数即可证明全部瓶颈的硬件因果归因。

第二轮使用已有 `MOP4CLXOR`，其低地址位分配方式与 `RoBaRaCoCh` 不同，
并未修改 DRAM 时序。HBM2 三组 seq 为 242.865、243.023、241.867 GB/s。
旧全局 FIFO 在同一新映射上的三组数值仍完全相同，进一步隔离了映射与前端的影响。
这是单独诊断后的新校准候选，不是事后改写原 P0。

## 4. LPDDR5 映射与注入宽度

LPDDR5 的 tCK=1.25 ns。在宽度8、32 B 事务下，注入上限为：
`8 × 32 / 1.25 = 204.8 GB/s`。
因此对实际409.6 GB/s的高带宽档，原宽度8即使无任何DRAM损失也最多50%效率。

后续冻结对照保持 outstanding=512，分别测试 MOP4CLXOR 与宽度8/16/32：

| 内存 | 宽度 | seq 效率范围 | 中位 η_seq | balanced η_mix | 三组seq门禁 |
| --- | ---: | ---: | ---: | ---: | --- |
| HBM2 256.0 GB/s | 8 | 94.479%–94.931% | 0.948692 | 0.620442 | 通过 |
| LPDDR5 204.8 GB/s | 8 | 90.251%–98.446% | 0.914663 | 0.799041 | 通过 |
| LPDDR5 409.6 GB/s | 8 | 49.364%–49.453% | 0.493863 | 0.923902 | 未通过 |
| LPDDR5 409.6 GB/s | 16 | 76.186%–82.455% | 0.803527 | 0.592733 | 未全部通过 |
| LPDDR5 409.6 GB/s | 32 | 76.302%–82.424% | 0.805502 | 0.590036 | 未全部通过 |

每行均实际执行完整 seq×3、mix×3。η_mix 是 balanced mixed/seq 中位值的
相对因子，不是对所有比例、布局、尺寸通用的预测器。提高顺序效率也没有自动
消除混合流损失。所有诊断校准保存在 `results/case_v3/calib/`，明确标记
`usable_for_full_case_v3=false`，priority仍未测，宽度变化均写入元数据。

## 5. 流隔离

三种内存均执行 I0，以及 I1 的 p=0.5/0.625/0.75 × mix25/50/75，
和 I2 的半数 bank-group 分区 × mix25/50/75。
I1 原生事务被映射到严格不相交的通道集合；I2 两流共享所有通道但使用不相交BG。
地址编码遵循原 RoBaRaCoCh 的真实层次位，不能直接移用于 MOP4CLXOR。

| 原映射内存 | I2 总吞吐范围 GB/s | 0.95×η_seq×peak 门槛 | 三种比例 |
| --- | ---: | ---: | --- |
| HBM2 256.0 | 168.394–173.524 | 126.269 | 均通过 |
| LPDDR5 204.8 | 172.294–196.439 | 142.537 | 均通过 |
| LPDDR5 409.6 | 198.384–201.588 | 188.118 | 均通过 |

各流在共同10%–90%完成窗口内的可得带宽已写入原生 JSON 和 `p0_sweep.csv`。
例如 HBM2 I2/mix50：VLM=84.216、DiT=84.179 GB/s，总计168.394 GB/s。
这些是共同测量窗口的流吞吐，不是每个分区单独的峰值带宽。

**没有任何 I1 固定 p 在三个比例上全部通过。** 这并不表示每个分区条件都无效；
例如 p=0.5/mix50 有效，但流量比例与通道份额不匹配时另一流会成为限制。
所以没有把某个成功点升级成全局 `stream_partition` 模型。
此外，I2 的共享通道/BG隔离不能等同为 I1 的固定通道带宽上限。
在新 MOP4CLXOR 上还需重新定义并验证隔离地址编码，不能把旧映射的通过结果套用过来。

## 6. 主 Case 的明确状态

- 未执行主网格、五组主 case 消融、1024 GB/s区间转换检验或 Pareto 前沿。
- 原配置P0失败，新映射诊断已找到两个内存档的顺序效率修复方向；高带宽档仍有
  粒度失败，且改变发射宽度必须作为新配置单列，不得混入原条件。
- `slice_mode=on` 没有已验证的128×128行切片到现有方阵NeuSim接口的映射；
  没有通过忽略slice标志或手工倍增性能来伪造on/off对照。
- 原生FRFCFS不支持严格流优先级，priority/balance仍未经原生验证；后续解析策略
  探索必须标为假设控制器，而非已标定硬件行为。
- 规格本身有两个验收冲突：第1条要求所有配置 k2严格优于k1，第4条却预期高带宽
  下二者相同；1024GB/s的文字称k1=k2=23.5ms，而表中是27.5/23.5ms。
  不会挑选其中一项作为能让实验通过的目标。

按“P0必须先做，否则绝对数值不可信”的约束，当前输出
`results/case_v3/status.json` 为 `blocked_for_full_case_v3`。
`ablations.md` 明确保留五项未执行门禁；仅生成 `p0_sweep.csv`，没有生成虚假的
主网格 `sweep.csv` 或 `frontier.csv`。没有最终芯片、面积能耗或任务成功率结论。

## 7. 执行与复现

| Slurm作业 | 内容 | 原生次数 | 结果 / 时长 |
| --- | --- | ---: | --- |
| 2044736 | 原P0、旧前端对照和基础诊断 | 64 | COMPLETED 0:0 / 1m21s |
| 2044759 | HBM映射与LPDDR宽度诊断 | 16 | COMPLETED 0:0 / 15s |
| 2044782 | LPDDR MOP4CLXOR×发射宽度 | 24 | COMPLETED 0:0 / 25s |

所有作业在 `einst` 的隔离 node-local 目录运行；结果已复制到本机：
`results/einst/case_v3_p0/`、`case_v3_followup/`、`case_v3_lpddr_mapping/`，
对应 Slurm 日志也已复制。没有仍在运行的本次作业或必须等待的实验。

审计实际核对104次运行的 accepted/completed、每流事务数、4MiB字节数、
原生stats的总读数与row分类数、trace/YAML/冻结清单和已执行源码哈希。
原始前两轮执行源码已单独保存在各结果目录 `executed_sources/`，避免后续工具扩展
损坏历史来源说明。后端源码清单、桥接库和DRAM库哈希与此前固定构建一致。
本地与远程最终均为 **92项测试通过**，不是用较旧的批处理测试数冒充最终结果。

```bash
.venv/bin/python vlasim/ramulator_bridge/case_v3_p0.py --backend .native/hbm2 --spec /Users/mr.meeseeks/Downloads/CASE_V3_SPEC.md --out results/p0_new
.venv/bin/python vlasim/ramulator_bridge/case_v3_followup.py --backend .native/hbm2 --p0 results/p0_new --out results/followup_new
.venv/bin/python vlasim/ramulator_bridge/case_v3_followup.py --backend .native/hbm2 --p0 results/p0_new --lpddr-mapping --out results/lpddr_new
.venv/bin/python vlasim/case_v3_audit.py --p0 results/p0_new --followup results/followup_new --lpddr results/lpddr_new --out results/case_v3_new
```

本地后端目录为`.native/hbm2`；Einstein脚本使用远程既有`.native/backend`。
原生依赖与固定后端的构建方式见`NATIVE_WORKFLOW.md`，所有输出目录均不可覆盖。
