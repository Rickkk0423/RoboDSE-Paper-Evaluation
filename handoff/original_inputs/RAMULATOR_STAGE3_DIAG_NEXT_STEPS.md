# Ramulator 分桶诊断解读与下一步（交给执行 AI）

2026-11-16。依据：`STAGE3_DIAGNOSIS_20261116.md`、`STAGE3_BUCKETS.md`、`ADAPTIVE_EVENTS.md`（profile 源 b083fce，build 2050165；adaptive pilot build 2051996）。

## 0. 当前阻塞：SSH 连不上 einst

错误是 `kex_exchange_identification: Connection closed by remote host`，对端地址 `198.18.0.74`。**198.18.0.0/15 是 RFC 2544 保留的基准测试网段，Clash、Surge 一类代理工具在 TUN/fake-ip 模式下常用它作虚拟地址。** 所以这次连接很可能没有直接到达集群，而是被本机代理接管后断开了。按顺序检查：

1. 本机是否开着代理 / VPN 的 TUN 或 fake-ip 模式。如果开着，给 einst 的域名或真实 IP 加一条 DIRECT 规则，或者把它加进 fake-ip 过滤列表，然后用 `ssh -v einst` 确认解析出来的是真实地址。
2. 如果确实已经直连真实地址仍然失败，再考虑服务器端原因。短时间内大量新建 SSH 连接，可能触发 sshd 的 `MaxStartups` 限制或 fail2ban。之后的连接统一走 `ControlMaster auto` / `ControlPersist` 复用同一条会话，避免并发新建握手。
3. 恢复连接后，按报告里已经写好的只读流程，先检查中断时可能残留的上传目录和作业状态，不要盲目重新提交。

## 1. 数据里最重要的三个发现

### 发现 A：「扫描」桶的很大一部分，是空队列时的固定开销

`requests scanned` 直方图显示，下面几个配置绝大多数周期一个请求都没扫，扫描桶却占了很高比例：

| 配置 | 扫描 0 个请求的周期占比 | 扫描桶占比 | 估算每控制器周期的扫描 Ir |
| --- | ---: | ---: | ---: |
| LPDDR5 sparse | 39%（另有 54% 只扫 1 个） | 57.8% | 约 790 |
| HBM3 SimpleO3 | 约 90% | 43.3% | 约 480 |
| DDR4 SimpleO3 | 约 88% | 27.4% | 约 215 |

（估算方法：run 窗口 Ir × 桶占比 ÷ 直方图里的周期总数。）

这部分开销与队列长度无关。原因是每个周期都会把 `pick_best_ready_from` / `pick_priority_if` / `pick_rw_if`、write mode 判断、lambda 构造这一整套流程走一遍；HBM 有双槽位，要走两遍；LPDDR 还要处理 ACT2/CAS/WCK 相关逻辑。**位图候选结构解决不了这类开销，需要的是空队列快路径。** 这一项是精确、便宜、通用的，并且直接对应 SimpleO3、sparse、HBM 和 LPDDR 这几个最慢的类别。

### 发现 B：开关在运行时判断，本身就有成本

`ADAPTIVE_EVENTS.md` 里，关闭状态（OFF）比冻结前的 reference 版本还慢：DDR4 sequential 慢 4.8%，DDR4 random 慢 1.8%。random 上打开事件推进后，比 OFF 又慢 4.4%，但事件桶的 Ir 只占 1.93%。合理的解释是：热循环里的运行时开关判断和多出来的代码，破坏了内联和代码布局。all-off 比 pristine 多出 6.6–10.3% 的 Ir，也和这个解释吻合。

### 发现 C：固定阈值 K 的思路走不通

不同配置的跳跃长度分布差别很大。DDR4 sequential 有 86% 的跳跃落在 1–3 个周期，DDR5 sequential 有 71% 落在 4–7，DDR4 sparse 有 88% 落在 8–31。所以 K=4 会把 DDR4 sequential 的有效跳跃丢掉，K=2 又压不住 random 上的查询开销：DDR4 random 做了 3447 次事件查询，只换来 118 个跳过的周期。门控不能用一个固定阈值，而要根据运行中的实际命中情况在线调整。

### 归一化的单位成本（按估算，请执行者用精确计数复核）

DDR4 random 一共 8584 个控制器周期，run 窗口 56.3M Ir，平均每周期约 6.6k Ir。由此估算：

- 扫描：每个被扫描的请求约 60 Ir；
- 发射：约 1.6k Ir/周期。如果每周期发约 0.7 条命令，相当于每条命令约 2.3k Ir；
- 前端与映射：约 850 Ir/周期，摊到 2000 个请求上，每个请求约 3.7k Ir。

最后一项高得不正常，最可能的原因是：**队列满时前端每周期都重试 `send`，而每次失败的 send 都要重新做一次地址映射并构造 `Request`。**

## 2. 下一步（按顺序）

### 步骤 1：补一份按单位成本的表

不新增任何实验，只用现有的计数器和 Callgrind 数据，为 12 个配置给出：

- 每个控制器周期的 Ir；
- 每个被扫描请求的 Ir；
- 每条发射命令的 Ir；
- 每个到达请求的前端/映射 Ir；
- 失败 send 的次数和对应的 Ir。

同时把两个大桶各拆一层：

- **Issue 桶**：`update_timing`、`raise_ready` 区间传播、`apply_action`、epoch 更新；
- **Framework 桶**（占 7–26%）：具体是哪些函数、哪些记账逻辑。

这份表用来确认上面的估算，并给步骤 2–6 排定顺序。

### 步骤 2：开关改为编译期特化（消除 OFF 状态的开销）

- 热循环里的运行时开关（EXACT_EVENTS、2a/2b/2c、FAST 等）改成模板参数。在 init 时根据配置只做一次分派，选中一个特化版本，比如 `run_loop<Events, Incremental>()`、`tick_impl<...>()`。
- 自检模式也作为一个特化版本存在，不在普通路径里留判断分支。
- 验收条件：all-off 特化版本与 pristine 的 wall time 差距不超过 1%；各 ON 特化版本相对当前版本不慢。

### 步骤 3：空队列 / 无事件快路径（针对发现 A）

- 如果控制器所有 buffer 都为空、没有到期的 refresh、`m_pending` 里也没有到期项，就直接跳过整个调度流程。
- 必须先审计：空队列时 write mode 的滞回逻辑、row policy 和 plugin 的 `pre_schedule`/`post_schedule`、refresh 的 `tick` 会不会改变状态。会改变的部分要用 O(1) 的方式精确执行，不能一起跳过。
- HBM 两个槽位分别判断；LPDDR 的 ACT2 owner / CAS 未来时钟 / WCK 状态要单独审计，未审计的部分保持原路径。
- 这一步与事件推进相互独立，对 SimpleO3 同样有效，因为 SimpleO3 不跳周期，但它的大部分周期队列都是空的。

### 步骤 4：用在线退避取代固定 K（针对发现 C）

- 对每个控制器统计最近一段时间事件查询的收益，即平均每次查询跳过的周期数。收益低于阈值时，查询间隔按 2 的幂次退避：每 1、2、4…个可查询的周期才查一次，上限比如 64。一旦某次查询真的跳过了周期，就把间隔重置为 1。
- 少做一次查询只会让本可以跳过的周期按逐周期正常执行，结果仍然精确，不影响正确性。
- 和 `a799266` 的 published bound（复用选择阶段已经算出的 bound，不再二次扫描证书）结合使用，降低每次查询本身的成本。
- 验收条件：12 个配置相对同版本 OFF 都 ≥ 0.99x，sequential/sparse 相对原 ON 不回退。达到后再走 full suite 和长程验证，然后评估是否默认开启。

### 步骤 5：失败 send 不再重复映射（针对前端成本）

- 前端缓存待发请求已经映射好的结果（`addr_vec`、channel），send 失败后的重试直接复用，不再重新构造 `Request`。
- 前提：先审计 mapper 是否无状态。报告中的陷阱提到「失败的 send 也经过 mapper」，只有对确认无状态的 mapper 才允许复用；有状态的（如 RIT 之类）保持原路径。
- 另一个可选做法：增加一个 O(1) 的 `can_accept(channel, type)` 预检查，队列满时直接返回。只有在已审计的 mapper 和 memory system 上，并且能证明可观察行为一致时才使用。

### 步骤 6：定长槽位 + 位图候选结构（满队列扫描）

内容同 `RAMULATOR_STAGE3_NEXT_STEPS.md` 第 3 步，第一版只做 GenericDDR。random/sequential 的大部分周期要扫 32–63 个请求，HBM 还有 64–127 的情况，这一步针对的就是这部分。等步骤 2–5 完成并重新分桶后再开工，因为前面几步会改变各桶的占比。

### 之后

- Issue 桶如果仍然很大（DDR5 sequential ON 为 37.7%，DDR4 sparse ON 为 42.6%），按步骤 1 的子桶决定优化 `update_timing` 还是 `raise_ready` 的传播。本轮被拒绝的「时序约束预分组」不再重做。
- 流式 / 二进制 trace 保持排在最后，作为独立的端到端和 RSS 优化，单独报告。
- 多核和 CUDA 仍然不启动。

## 3. 汇报节点

- SSH 恢复之后，先完成步骤 1 的单位成本表并汇报一次。
- 步骤 2、3 完成后合并汇报一次；这两步都是精确且通用的，预计收益覆盖全部 12 个配置。
- 步骤 4、5 完成后各汇报一次。
- 每项改动沿用现有规则：单独提交、普通/自检/FAST 三种模式下 equiv、反馈驱动验证、full suite、Slurm 三次配对计时。增量 < 1.01x 且增加复杂度的改动回退。
