"""Publish V4 gates and reproducible delivery hashes without promoting blocked stages."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publish(root=Path('results/v4')):
    p0a = json.loads((root / 'p0a/status.json').read_text())
    p0b = json.loads((root / 'p0b/status.json').read_text())
    supplement = json.loads((root / 'p0b_replay_configs/status.json').read_text())
    supplemental_summaries = [json.loads(p.read_text()) for p in
                              (root / 'p0b_replay_configs').glob('*/summary.json')]
    supplemental_runs = sum(len(s['search']['trials']) + sum(c['gate960'] is not None for c in s['curve'])
                            for s in supplemental_summaries)
    supplemental_failed_searches = sum(not t['pass_gate'] for s in supplemental_summaries
                                       for t in s['search']['trials'])
    plan = json.loads((root / 'planning/stage_b_plan.json').read_text())
    mismatches = [name for name, digest in p0b['artifact_sha256'].items()
                  if sha(root / 'p0b' / name) != digest]
    if mismatches:
        raise RuntimeError(f'P0B artifact hash mismatch: {mismatches}')
    for name, digest in supplement['artifact_sha256'].items():
        if sha(root / 'p0b_replay_configs' / name) != digest:
            raise RuntimeError(f'P0B supplement artifact hash mismatch: {name}')
    tests = {}
    for label, filename in (('local', 'local_pytest.xml'), ('einst_core', 'remote_core_pytest.xml')):
        suites = list(ET.parse(root / 'validation' / filename).getroot().iter('testsuite'))
        tests[label] = {key: sum(int(s.get(key, 0)) for s in suites)
                        for key in ('tests', 'failures', 'errors', 'skipped')}
        if tests[label]['failures'] or tests[label]['errors']:
            raise RuntimeError(f'{label} has failing tests')
    stage_a = p0a['passed'] and p0b['periodic_all_strict'] and supplement['periodic_all_strict']
    if stage_a or p0a['completed_windows'] != p0a['expected_windows']:
        raise RuntimeError('This failed-gate report requires all frozen replays to be completed.')
    status = dict(spec='NEXT_STEPS_V4.md', execution_local_date='2026-11-15',
        spec_document_date='2026-11-16',
        stage_A=dict(passed=stage_a, P0A=p0a['status'],
                     P0B='finite_horizon_pass' if p0b['periodic_all_strict'] else 'failed'),
        stage_B=dict(status='not_executed_stage_A_gate', planned_rows=plan['planned_plain_mapping_rows']),
        P1B=dict(status='blocked_missing_closed_loop_environment', new_measured_episodes=0),
        stage_C='blocked_stage_B_and_measured_task_surface',
        stage_D='blocked_candidate_selection_and_closed_loop_environment',
        P0B_artifacts_verified=len(p0b['artifact_sha256']),
        P0B_exact_replay_configs=dict(configurations=supplement['configurations'],
            finite_horizon_all_strict=supplement['periodic_all_strict'],
            periodic_runs=supplemental_runs, failed_search_trials=supplemental_failed_searches,
            artifacts_verified=len(supplement['artifact_sha256'])), tests=tests,
        total_periodic_runs=440+supplemental_runs, total_curve_gate_checks=300,
        numeric_hardware_or_success_rankings_produced=False,
        scope='All feasible V4 preparation, diagnostics and frozen replay completed. '
              'Blocked dependent stages are not claimed as completed experiments.')
    (root / 'status.json').write_text(json.dumps(status, indent=2)+'\n')
    failing = sorted(p0a['failing_streams'], key=lambda r: -r['absolute_error_pct'])
    lines = ['# V4 执行与门禁汇报', '',
        '执行本地日期：2026-11-15（America/Los_Angeles）。输入规格页内日期为 2026-11-16；日期差不影响冻结验收标准。', '',
        '## 结论', '',
        '**阶段 A 未通过。P0-B 在所测配置与有限窗口内通过；P0-A 原生回放超标且覆盖不完整。因此未启动阶段 B 数值网格，也未输出联合选型或闭环验证结论。**', '',
        'V3 结果保持不变。本文的新结果不把模型生成轨迹称为独立执行捕获，不把估计形状称为已核实 checkpoint 布局。', '',
        '## P0-A：原生回放', '',
        f"- 先冻结 8 个 fair 配置、窗口与哈希，再在 einst 执行；完成 {p0a['completed_windows']}/{p0a['expected_windows']} 条轨迹、{p0a['stream_measurements']} 个流测量。",
        '- 3 种内存，serial、pipeline k=1/2/3，普通交织与 BG；MOP4CLXOR、FRFCFS/Open、native32、512 outstanding，与对应校准一致。',
        f"- 流完成时长平均绝对误差 **{p0a['mean_absolute_error_pct']:.4f}%**，最大 **{p0a['maximum_absolute_error_pct']:.4f}%**；超过 10% 的流测量共 **{len(failing)}** 个。硬门槛为每个≤10%、总体平均≤5%，不可只看平均。",
        f"- 完成分片 {p0a['complete_shards']}/8；完整性问题 {len(p0a['integrity_issues'])}；适用但缺失窗口 {len(p0a['coverage_gaps'])}。",
        f"- 等权窗口均值口径的平均绝对误差为 {p0a['mean_of_window_mean_absolute_errors_pct']:.4f}%；与等权流测量均值分开报告，不混用权重。",
        '- 误差定义为 `(原生完成时长 / 流体预测时长 - 1) × 100%`；负数表示原生更快，不能解释为流体模型低估耗时。所有失败保留，未用测试窗口重新拟合。', '',
        '| 窗口 | 流 | 有符号误差 | 原生 GB/s | 预测 GB/s |',
        '| --- | --- | ---: | ---: | ---: |']
    for row in failing:
        lines.append(f"| {row['id']} | {row['stream']} | {row['signed_error_pct']:+.3f}% | {row['actual_GBps']:.3f} | {row['predicted_GBps']:.3f} |")
    lines += ['', '| 发射方式 | 流测量数 | 平均绝对误差 | 最大绝对误差 | 超过 10% |',
              '| --- | ---: | ---: | ---: | ---: |']
    for launch, summary in p0a['summary_by_launch'].items():
        lines.append(f"| {launch} | {summary['stream_measurements']} | {summary['mean_absolute_error_pct']:.3f}% | {summary['maximum_absolute_error_pct']:.3f}% | {summary['failures_over_10pct']} |")
    lines += ['', '| 窗口类型 | 流测量数 | 平均绝对误差 | 最大绝对误差 | 超过 10% |',
              '| --- | ---: | ---: | ---: | ---: |']
    for kind, summary in p0a['summary_by_window'].items():
        lines.append(f"| {kind} | {summary['stream_measurements']} | {summary['mean_absolute_error_pct']:.3f}% | {summary['maximum_absolute_error_pct']:.3f}% | {summary['failures_over_10pct']} |")
    lines += ['', '| BG 窗口 | 总吞吐 / (η_seq × 峰值) |', '| --- | ---: |']
    for wid, ratio in p0a['bg_total_over_seq_reference'].items():
        lines.append(f'| {wid} | {ratio:.4f} |')
    lines += ['', '完整测量与 BG 总吞吐 / (η_seq × 峰值) 在 [stream_metrics.csv](../results/v4/p0a/stream_metrics.csv)；原生 YAML、原始统计、执行源码及后端哈希在 `results/v4/p0a_native/`。', '',
        '覆盖限制：HBM W5 的完整触及层布局约 5.4 GB，超过固定器件 4 GiB；BG 地址位还需额外容量。未取模混叠地址、未更换器件冒充同一实验。部分配置无连续 0.5 ms 独占段；不适用于某种 mode/k 的窗口另列为 N/A。', '',
        'W5 保留一个观察周期的每十条 64B 行之一，并把时间压缩为 1/10。这样保持名义平均需求，但改变地址步长/局部性，且并非独立完整周期验收。地址是窗口内完整层连续区域的实验布局，KV 写入/读取共享同一物理区域。', '',
        '饱和协议的另一个边界：原生前端把两流按窗口字节需求比例合并发射，而流体参照采用双流无限需求下的 max-min fair 分配。FRFCFS 控制器并不保证同样的逐流公平份额，因此该比较检验的是包含发射/仲裁假设的整套模型，不是隔离出来的 DRAM 时序误差；本轮不据此断言所有偏差都由某个 η 参数造成。', '',
        '## P0-B：稳态与周期发射', '',
        '- 原始 10 个未稳定 ID 保留原计算轨道、校准与 priority 策略，分别执行 jit/frozen20，共 20 次 1920 请求长跑（384 warmup）。',
        '- 另加 12 个真实 NeuSim fair 对照，覆盖三内存 × serial/k1/k2/k3，共 22 个配置。priority 诊断仅验证调度语义，不验证原生优先级控制器。',
        '- 共 440 次 periodic 运行，含 110 次 960 请求确认；保留全部 109 个失败搜索试点。五点曲线在 480/960 两种长度下的 220 次检查全部通过。',
        f"- 另对 P0-A 的精确 {supplement['configurations']} 个配置补做相同二分与五点曲线，覆盖原对照中未逐项匹配的 16 核/BG 变体；新增 {supplemental_runs} 次 periodic 运行、80 次曲线门禁检查，{'全部通过' if supplement['periodic_all_strict'] else '存在失败'}，并保留 {supplemental_failed_searches} 个失败搜索试点。独立冻结在 `p0b_replay_configs/`，不混入此前 440 次统计，不视为 BG 原生验证。",
        f"- 两批合计 {440+supplemental_runs} 次 periodic 运行、300 次曲线检查；同语义配置可能跨批重复，不能把批次配置数之和说成不同硬件设计数。",
        '- 可行性检查包括 L 前后第三段漂移<0.5%、稳态 VLM 等待队列≤1、每个 S/T 相对误差<1e-6，以及相邻完整周期组 L/S 误差≤1e-9 秒。最大 S 相对误差约 1.892e-11。',
        '- 原 jit 的 L 漂移约 1.44%–14.54%；冻结前 20 个观测均值后，10 个配置的稳态 L/S 都严格重复。这支持预测器与争用反馈解释，不证明唯一根因。',
        '- Tmin 二分 bracket 精度 0.1 ms，仅为有限窗口观察到的最小可行上端点，不是全局最优或无限时间稳定性证明。batch-means 95% 区间是确定性时间序列分块口径，不是独立实验置信区间。', '',
        'SRAM 仍采用原静态可放置性检查；periodic 过载试点不丢请求，未验证动态排队 KV 的 SRAM 容量约束。稳态门禁通过不等于完成真实 SRAM 生命周期验证。', '',
        '详见 [P0-B 报告](../results/v4/p0b/REPORT.md)、`Tmin.csv`、`L_of_T.csv`、`jit_analysis.csv` 和 10 张逐请求 L/S 图。', '',
        '## 阶段 B：准备而非实测', '',
        f"- 已展开 {plan['planned_hardware_points']} 个硬件点、{plan['planned_plain_mapping_rows']:,} 个普通交织映射计划，全部标记 planned/not executed，Tmin 与 L 曲线为空。",
        '- `planning/hardware_grid_plan.csv` 不是 `hw_grid.csv`；未声称已做 SRAM/解析下界剪枝，未产生校准、前沿或成本排名。BG 网格待动态验证通过。',
        '- 固定 CacheLineInterleave 明确拒绝 12/24 通道；GDDR6 只有 14000 Mbps 时序预设，缺少 16000/20000 Mbps；未发现 GDDR6X 模块。不能插值出一个当前后端无法实测验收的 24 通道点，也不能擅自缩放时序。',
        '- LPDDR/GDDR/HBM 面积与能耗分开列 null，保持 placeholder_not_calibrated。', '',
        '## P1-B：任务数据', '',
        '- 已准备两个 benchmark 共 56 个补测点：每个 6 个低延迟点、22 个平台点；速度与 episode 预算为空。',
        '- 严格逐局 JSONL 校验与池化二项比例/标准误实现完成，同时支持无效计失败与无效剔除口径。',
        '- 对本地及 einst 已知环境/目录的有限核查未找到可运行闭环依赖、checkpoint 或逐局证据。旧 CSV 为 33 行汇总，缺少分母、逐局及版本出处。**新增实测 0 局。**',
        '- 缺真实 checkpoint/hash、两套环境及版本、速度/试验预算、注入/adoption/无效局协议。详见 [任务数据说明](V4_TASK_DATA.md)。', '',
        '## 验证与复现', '',
        f"- 本地全套 pytest：{tests['local']['tests']} 项通过；einst 核心测试：{tests['einst_core']['tests']} 项通过。结果见 `results/v4/validation/local_pytest.xml` 和 `remote_core_pytest.xml`。",
        '- 18 个默认模式对照与冻结 V3 源码的输出和逐 op 时间线完全相同，证据见 `validation/legacy_defaults.json`。',
        '- V3 原交付清单 904 个产物全部重新核对，0 个哈希变化，见 `validation/v3_artifacts.json`。',
        f"- P0-B 的 {len(p0b['artifact_sha256'])} 个哈希由汇总入口重新核验；P0-A 核验轨迹、YAML、源码、校准后端身份、请求/回调/控制器读写记账。",
        '- 最初作业 2046177 因环境缺 PyYAML 启动失败，保留日志；切换已有原生依赖环境后，2046185 执行冻结输入，未修改参数。',
        '- 10 张 PNG 已验证可解码且像素非空；当前会话图像查看接口不可用，未声称完成肉眼图形审阅。', '',
        '```sh',
        '.venv/bin/python vlasim/v4_replay_audit.py --input results/v4/p0a_input --native results/v4/p0a_native --out results/v4/p0a',
        '.venv/bin/python vlasim/v4_scheduler.py --out results/v4/p0b --collect-only',
        '.venv/bin/python vlasim/v4_report.py',
        '```', '',
        '## 后续门禁', '',
        '1. 将本轮失败回放仅作开发集，改进混流/局部性建模；下一次验收必须另选并预先冻结全新留出窗口，不用本轮测试调参后自证。',
        '2. 解决 HBM 完整周期地址容量与窗口覆盖问题，并明确新器件/布局对应的新实验身份。',
        '3. P0-A 数值和覆盖通过后，先解决通道/时序能力与≤5%插值门禁，再执行硬件网格。',
        '4. 补齐真实闭环输入后才能联合选型及直接闭环回放；checkpoint、切片、成本与独立捕获不填常数。', '']
    report = Path('docs/CASE_V4_RESULTS.md')
    report.write_text('\n'.join(lines))
    artifacts = {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*'))
                 if p.is_file() and p.name != 'delivery_manifest.json'}
    implementations = list(Path('vlasim').glob('v4_*.py'))
    implementations += [Path('vlasim/ramulator_bridge/v4_replay_native.py'),
                        Path('vlasim/vlasim/sim.py'), Path('vlasim/vlasim/hw.py'),
                        Path('scripts/einst_v4_replay.sh')]
    implementations += list(Path('tests').glob('test_v4_*.py')) + [Path('tests/test_periodic_scheduler.py')]
    delivery = dict(status=status, artifacts_sha256=artifacts,
                    implementation_sha256={str(p): sha(p) for p in sorted(implementations)},
                    report_sha256=sha(report), task_plan_sha256=sha(root / 'task_data/sampling_plan.json'))
    (root / 'delivery_manifest.json').write_text(json.dumps(delivery, indent=2)+'\n')
    print(json.dumps(status, indent=2))
    print(f'Delivery manifest: {len(artifacts)} artifacts')


if __name__ == '__main__':
    publish()
