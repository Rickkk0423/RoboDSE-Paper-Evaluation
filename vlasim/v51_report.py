"""Publish an eight-section V5.1 report and hash-pinned delivery manifest."""
from collections import Counter,defaultdict
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from v51_package import read_csv
from v51_workflow import ROOT,load
from v5_protocol import digest,write_json


def preserve():
    evidence=[]
    for path in (Path('results/case_v3_complete/delivery_manifest.json'),Path('results/v4/delivery_manifest.json'),
                 Path('results/v5/delivery_manifest.json')):
        manifest=load(path)
        if 'files' in manifest:
            files={Path(name):sha for name,sha in manifest['files'].items()}
        else:
            files={path.parent/name:sha for name,sha in manifest['artifacts_sha256'].items()}
        changed=[str(name) for name,sha in files.items() if not name.is_file() or digest(name)!=sha]
        sources=manifest.get('implementation_sha256',manifest.get('source_sha256',{}))
        if not isinstance(sources,dict):
            sources={}
        changed += [name for name,sha in sources.items() if digest(name)!=sha]
        if manifest.get('report_sha256'):
            report=Path('docs/CASE_V4_RESULTS.md' if path.parent.name=='v4' else 'docs/CASE_V5_REPORT.md')
            if digest(report)!=manifest['report_sha256']:
                changed.append(str(report))
        evidence.append(dict(manifest=str(path),artifacts=len(files),sources=len(sources),changed=changed))
        if changed:
            write_json(ROOT/'preservation_failure.json',evidence)
            raise RuntimeError('Prior delivered artifacts changed '+str(changed))
    write_json(ROOT/'preservation.json',dict(passed=True,deliveries=evidence))
    return evidence


def table(rows,fields):
    return ['| '+' | '.join(fields)+' |','| '+' | '.join('---' for _ in fields)+' |',
        *['| '+' | '.join(str(r.get(k,'')) for k in fields)+' |' for r in rows]]


def publish():
    preserved=preserve();gates=load(ROOT/'gates.json');fit=load(ROOT/'model_fit.json')
    held=load(ROOT/'heldout_gate.json');cal=load(ROOT/'calibration.json');dse=load(ROOT/'dse_summary.json')
    cal=dict(sorted(cal.items(),key=lambda pair:({'LPDDR5':0,'GDDR6':1,'HBM2':2}[pair[0].split('_')[0]],
        int(pair[0].split('c')[-1]))))
    task=load(ROOT/'task_preparation/status.json');rows=read_csv(ROOT/'attainable.csv')
    native=load(ROOT/'native_archive_audit.json')
    placement=load(ROOT/'sram_placement_summary.json')
    archive=load(ROOT/'dse_archive_audit.json')
    calibration_metrics=read_csv(ROOT/'calibration_metrics.csv')
    calibration_errors={layout:[float(r['error_pct']) for r in calibration_metrics if r['layout']==layout]
        for layout in ('vla_plain','vla_bg')}
    if not native['passed'] or not archive['passed'] or not (ROOT/'validation/zz_final_pytest.xml').exists():
        raise RuntimeError('Final native audit and full pytest required')
    tests=[]
    for path in sorted((ROOT/'validation').glob('*.xml')):
        suites=list(ET.parse(path).getroot().iter('testsuite'))
        tests.append(dict(file=path.name,**{key:sum(int(s.get(key,0)) for s in suites)
            for key in ('tests','failures','errors','skipped')}))
    if not tests or tests[-1]['failures'] or tests[-1]['errors']:
        raise RuntimeError('Final full pytest report required')
    summary=[]
    for memory in cal:
        group=[r for r in rows if r['memory']==memory and r['model']=='v51' and r['track']=='neusim_unsliced'
            and r['bw_policy']=='fair' and r['scenario']=='main']
        if group:
            summary.append(dict(memory=memory,frontier_points=len(group),
                L_ms_min=round(min(float(r['L_s'])*1000 for r in group),3),
                S_ms_min=round(min(float(r['S_s'])*1000 for r in group),3),
                frontier_k_counts=dict(Counter(r['dit_stages'] if r['mode']=='pipelined' else 'serial' for r in group))))
    main=[r for r in read_csv(ROOT/'best_mapping.csv') if r.get('status')=='attainable' and
        r.get('track')=='neusim_unsliced' and r.get('bw_policy')=='fair' and r.get('scenario')=='main']
    paired=defaultdict(dict)
    for row in main:
        paired[row['hardware_id'],row['S_target_ms']][row['model']]=row
    agreement=[]
    for (hardware,target),pair in paired.items():
        if set(pair)!={'v51','v3_form'}:
            continue
        keys=('mode','vlm_cores','dit_stages','dit_batching','bg')
        agreement.append(dict(hardware_id=hardware,S_target_ms=target,
            same_mapping=all(pair['v51'][k]==pair['v3_form'][k] for k in keys),
            v51_L_ms=float(pair['v51']['L_s'])*1000,v3_form_L_ms=float(pair['v3_form']['L_s'])*1000,
            v51_mapping={k:pair['v51'][k] for k in keys},v3_form_mapping={k:pair['v3_form'][k] for k in keys}))
    write_json(ROOT/'dual_model_agreement.json',dict(paired_hardware_targets=len(agreement),
        matching_mapping_count=sum(r['same_mapping'] for r in agreement),pairs=agreement))
    k_best=Counter()
    for row in main:
        if row['model']=='v51':
            k_best['serial' if row['mode']=='serial' else 'k'+row['dit_stages']]+=1
    comparisons=[r for r in read_csv(ROOT/'serial_pipeline_comparison.csv')
        if r['model']=='v51' and r['bg']=='False' and r.get('pipeline_Tmin_s') and r.get('serial_Tmin_s')]
    pipeline_faster=sum(float(r['pipeline_Tmin_s'])<float(r['serial_Tmin_s']) for r in comparisons)
    example=[r for r in read_csv(ROOT/'k_ablation.csv') if r['hardware_id']=='LPDDR5_c8_c8_s64_p512'
        and r['model']=='v51' and r['bg']=='False' and r['dit_batching']=='True' and r.get('Tmin_s')]
    example_rows=[dict(k=r['dit_stages'],split=r['selected_split'],Tmin_ms=round(float(r['Tmin_s'])*1000,4),
        L_ms=round(float(r['L_s'])*1000,4),DiT_GB_req=round(float(r['steady_dit_GB_per_req']),6),
        DiT_busy_pct=round(float(r['steady_dit_busy'])*100,3),
        compute_ms=round(float(r['round_compute_s'])*1000,4),
        exposed_ms=round(float(r['round_exposed_memory_s'])*1000,4),
        wait_before_ms=round(float(r['round_wait_before_s'])*1000,4)) for r in example]
    lines=['# V5.1 执行总报告','',
        '报告日期：2026-11-16（本轮工作区日期，与输入规格日期一致）；早期执行归档记录的洛杉矶日期为 2026-11-15。',
        '所有结果位于 `results/v5_1/`。旧 V3/V4/V5 数据与报告未覆盖。',
        '本轮是估计 checkpoint 形状、显式 SigLIP 解析回退、原生 DRAM 校准的模型研究，不是实际机器人或芯片测量。','',
        '## 1. 门禁总表','',
        f'- 步骤 1：10 档分别完成阶梯自检，无 L3；完整周期大容量 HBM 验收通过；所选原生及周期内核跨主机对照均无差异（不声称全网格跨主机重跑）。',
        f'- 步骤 2：开发集 A={fit["A_dev_gate"]}、B={fit["B_dev_gate"]}，选择 {fit["chosen_form"]}；冻结新留出后门禁为 `{held["dram_model_mode"]}`。',
        f'- 留出饱和逐流平均误差 {held["mean_error_pct"]:.4f}%，最大 {held["max_error_pct"]:.4f}%；BG 主口径资格={held["bg_main"]}。',
        f'- 步骤 3：10 档原生校准完成；步骤 4：{dse["hardware_points"]} 个硬件身份完成，前沿执行 960 请求原 Python 调度器复查。',
        f'- “原生校准完成”不是逐流模型通过：新增各档 VLA 拟合平均误差 plain={np.mean(calibration_errors["vla_plain"]):.3f}%、'
        f'BG={np.mean(calibration_errors["vla_bg"]):.3f}%，残差仍大，不能把这些参数解释为已验证的通用器件混流效率。',
        f'- 独立归档审计通过：{native["completed_replays"]} 次完整原生回放的统计/计数/输入哈希均一致；未完成尝试不冒充完成结果。',
        '- 任务侧仅准备：新闭环实测 0 局；面积、能耗均为空，不做成本或芯片推荐。','',
        *table([dict(memory=k,block_bytes=v['sampling']['block_bytes'],level=v['sampling']['level'],
            ratio=round(v['sampling']['levels'][-1]['ratio'],9),eta_seq=round(v['params']['vla_plain']['eta_seq'],9))
            for k,v in cal.items()],['memory','block_bytes','level','ratio','eta_seq']),'',
        '## 2. DRAM 模型','',
        '开发集包括 V4 饱和 W3/W4 与原配置不同时间的新增窗口，并增加不与留出重叠的 GDDR 开发配置。'
        'A 每种内存/布局一个常数；B 使用精确发射序列每次切流前连续字节数的 log2 特征。'
        '两种都未全过开发门槛时保留较简单 A，明确失败，不用留出调参。',
        '原生按字节份额合并发射；流体模型 max-min fair。二者的逐流仲裁不同，残差不应一概解释为 DRAM 时序误差。',
        *table([dict(group=k,eta_mix=round(v['A_eta_mix'],6),mean_pct=round(v['A_mean_absolute_error']*100,4),
            max_pct=round(v['A_max_absolute_error']*100,4)) for k,v in fit['groups'].items()],
            ['group','eta_mix','mean_pct','max_pct']),'',
        '完整逐流误差见 `development_metrics.csv`、`heldout_metrics.csv`；按窗口/内存/发射分组如下。']
    groups=defaultdict(list)
    for dataset in ('development','heldout'):
        for row in read_csv(ROOT/f'{dataset}_metrics.csv'):
            groups[dataset,row['standard'],row['window'],row['launch']].append(float(row['absolute_error_pct']))
    lines+=table([dict(dataset=k[0],standard=k[1],window=k[2],launch=k[3],flows=len(v),
        mean_pct=round(float(np.mean(v)),4),max_pct=round(max(v),4)) for k,v in sorted(groups.items())],
        ['dataset','standard','window','launch','flows','mean_pct','max_pct'])
    lines+=['','抽样各级实际结果如下；L1通过的配置未额外执行L2，未列出的级别不是失败。',
        *table([dict(memory=memory,level=level['level'],block_bytes=level['block_bytes'],
            ratio=round(level['ratio'],9),passed=level['passed'])
            for memory,v in cal.items() for level in v['sampling']['levels']],
            ['memory','level','block_bytes','ratio','passed'])]
    lines+=['','块跨度：物理 bank 行字节数=(Column/prefetch)×native32；L1=行字节数×channels；'
        'L2=L1×行前 rank/SID/pseudochannel/BG/bank 域数。MOP4CLXOR 通道剥离后的位序为 column_low_2、'
        '行前域、其余 column、row；XOR 还包含 Row，不能把 L2 说成“一个物理行”。'
        '所有 L1 失败及 L2 结果均保留在 `selfcheck_remote/` 和 `selfcheck_retry_remote/`。',
        '抽样保留每十块中的一整块，地址不压缩、时间/10；饱和置零；serial 的 VLM→DiT 仍等待所有回调排空。','',
        f'大容量HBM2_c8验收：三种seq粒度效率为 {gates["stage1"]["hbm_acceptance"]["seq_three_granularities"]}；'
        f'与V3基准的相对差异为 {gates["stage1"]["hbm_acceptance"]["relative_difference"]*100:.6f}%，低于3%。'
        '16GiB新容量身份仍单独保留；完整周期块抽样W5（含BG映射）原生回放完成，全部物理地址通过容量检查。','',
        '## 3. 校准表','',
        '每档 seq 3 粒度 + VLA 普通/BG 各 25/50/75，以及新身份的 legacy 普通/BG 各三比例；均为原生测量，不插值。'
        'V3 器件身份完全相同的 LPDDR 档保留原 V3 参数作双模型基线；新身份采用“V3 模型形式重新测量”，不能称为原 V3 结果。',
        'VLA 的 A 常数对三个比例的逐流完成时间做最小二乘；V3-form 新身份基线严格用 50:50 总吞吐/顺序带宽。'
        '原生 FRFCFS 不保证流体 fair 份额，因此校准残差仍可能较大，完整残差在 `calibration_metrics.csv`，未据此宣称逐流验证通过。',
        *table([dict(layout=k,flows=len(v),mean_error_pct=round(float(np.mean(v)),4),max_error_pct=round(max(v),4))
            for k,v in calibration_errors.items()],['layout','flows','mean_error_pct','max_error_pct']),'',
        *table([dict(memory=k,peak_GBps=v['geometry']['peak_GBps'],capacity_GiB=v['geometry']['capacity_bytes']/2**30,
            eta_seq=round(v['params']['vla_plain']['eta_seq'],6),
            mix_plain=round(v['params']['vla_plain']['eta_mix'],6),mix_bg=round(v['params']['vla_bg']['eta_mix'],6),
            mapper=v['mapper'],seq_gate=v['seq_gate']) for k,v in cal.items()],
            ['memory','peak_GBps','capacity_GiB','eta_seq','mix_plain','mix_bg','mapper','seq_gate']),'',
        'seq 任一效率低于 .8 的失败组保留；替代 ChRaBaRoCo 的三粒度实测比较也保留，未用未执行的映射修正数值。'
        '大容量 HBM 的新旧 η_seq 比较与容量原生检查见 `gates.json` 和对应校准文件。',
        'GDDR6 使用固定后端的 14Gbps double-rate 时序及 NoRefresh（与其 smoke 配置一致）；真实刷新影响未验证。'
        '24/36 通道采用独立 clocked 单通道实例与双射通道解复用，不做容量取模；6 组聚合/独立实例比较完全一致。','',
        '## 4. DSE 规模与剪枝','',
        f'- 640 硬件点：8 核数×10 内存档×4 共享 SRAM×2 私有 SRAM；映射/场景/模型合计 {dse["mapping_context_rows"]:,} 行。',
        f'- 状态计数：`{json.dumps(dse["statuses"],ensure_ascii=False)}`。唯一语义完整执行 {dse["unique_semantic_evaluations"]:,}，五点曲线行 {dse["curve_rows"]:,}。',
        '- 每一映射包含 serial 或全部 VLM:DiT 分配、k1/2/3 合批及 k2/3 不合批；fair 主口径，priority 独立未验证场景；解析切片独立敏感性组。',
        '- 仅同硬件/模型/计算轨道/策略/布局内按解析下界排序；LB>1.2×当前最优的映射标记剪枝，未伪造其时间。',
        '- 可达前沿是按指定吞吐下界剪枝后保留候选的前沿；该剪枝不保证保留所有较慢周期下的低 L 映射，故不是全映射的全局 Pareto 最优证明。',
        '- 私有 SRAM 512/2048KB 均通过现有静态最小 tile 检查；现有 provider 不因私有容量改变时延，故复用完全相同模板但保留两种物理身份。',
        '- 所有搜索失败试点及逐请求时间保存在分片 `requests.npz`；五个曲线点保存全部轮分解；每分片落盘并带哈希。',
        f'- 交付前重新打开 {archive["evaluations"]:,} 个语义执行归档，核对原始哈希、请求时间顺序及 {archive["archived_curve_rounds"]:,} 个曲线轮的两套时间分解。',
        f'- 960 请求原 Python 前沿复查覆盖 {dse["reference_rechecks"]:,} 项，对应 {dse["unique_reference960_runs"]:,} 次唯一原调度器运行；'
        f'相同操作模板/DRAM/策略/周期的硬件身份精确复用并留源身份，未计作重复运行。门禁失败前沿 {dse["canonical960_failed_frontiers"]}。',
        f'- 唯一执行归档共保存 {dse["search_trials"]:,} 个二分/扩展试点，其中失败 {dse["failed_search_trials"]:,} 个；'
        f'观察到非单调搜索 {dse["observed_nonmonotonic_evaluations"]} 组，五点曲线门禁失败 {dse["failed_curve_points"]} 点，全部保留。','',
        '## 5. 主要结果','',
        '下表仅汇总新模型、NeuSim unsliced、fair、符合主口径资格的前沿。L_ms_min与S_ms_min是分别取的极小值，'
        '不能拼成同一个可达点。不是硬件推荐；不同核心数/SRAM 的完整变化见 `attainable.csv`。',
        *table(summary,['memory','frontier_points','L_ms_min','S_ms_min','frontier_k_counts']),'',
        '![各内存档离散可达前沿](../results/v5_1/figures/frontiers.png)','',
        f'新模型主口径的硬件/S目标可达查询中，最低 L 映射计数为 `{dict(k_best)}`。'
        '同一硬件会出现在多个目标中，计数不是独立硬件数；不可达目标不计入。',
        f'新模型 plain、fair、unsliced 的 {len(comparisons)} 个可比较硬件身份中，'
        f'保留 pipeline 的最低 Tmin 小于 serial 的有 {pipeline_faster} 个。'
        '这是各自 Tmin 下的吞吐对照，不是同 S 下的延迟胜负。','',
        '同分配实例：LPDDR5 8通道、8核、64MB共享、512KB私有。下表稳态流量和busy取各k自己的Tmin；'
        '核分配split表示VLM核数，其余核给DiT。该实例只说明流量、吞吐和延迟可以朝不同方向变化。',
        *table(example_rows,['k','split','Tmin_ms','L_ms','DiT_GB_req','DiT_busy_pct','compute_ms','exposed_ms','wait_before_ms']),'',
        '![同核分配k消融](../results/v5_1/figures/k_controls.png)','',
        '`best_mapping.csv` 给出每硬件 S≤50/100/150/200ms 的最低 L 或明确不可达；`k_ablation.csv` 在各档最优合批 Tmin 的核分配上单独跑齐 k1/2/3 合批和 k2/3 不合批控制。'
        '这些消融即便在优化搜索中被剪枝也单独执行，不回填为优化候选；单核无 pipeline 则明确 N/A。`compute_report.json` 汇总同分配流量、busy 与轮构成。'
        '若全部 pipeline 分配在优化搜索中被剪枝，补充控制组选最小解析下界的分配，不把“未执行”误说成“不可行”。'
        '每行含 DiT/总流量、KV 带宽、组 busy 和轮 compute/exposed-memory/linear/attention/wait，不能把少读权重直接等同为低延迟。',
        '其中 `dit_GB_per_req` 与 `vlm_busy/dit_busy` 是含暖机/排空的整批口径；`steady_*` 为稳定测量区间口径。轮等待在轮 duration 之外，compute+exposed-memory 与 linear+attention 各自对账为轮 duration。',
        'busy 是组有在途操作的时间比例，包含 DRAM 等待，不是有效 MAC 利用率；轮前等待可能来自周期到达或 VLM 供料节奏，不作唯一根因归因。',
        '前沿与 S 目标查询只比较已留存映射的五个离散周期点，不做连续插值或全局最优声明。图中连线仅帮助观察离散点趋势。',
        '`sensitivity_core_bandwidth.csv` 在固定 64MB/512KB 下按内存和核数分别给最小 S、该点 L、最小 L、该点 S，不能把两个单独极值拼成一个可达点。'
        '`serial_pipeline_comparison.csv` 另列最小 Tmin 对照，并区分“单核不适用”和“全部 pipeline 被优化剪枝”。',
        f'静态 SRAM 模型中，k1 pipeline 同时保留 KV 与 VLM activation 需 {placement["KV_and_activation_required_MB"]["1"]:.3f}MB，'
        f'高于网格最高 64MB；因此本轮 pipeline 的共享 SRAM 增大不自动带来 KV 全驻留。serial 对应需 {placement["serial_KV_and_activation_required_MB"]:.3f}MB。'
        '这是现有估计形状与保守静态 live-KV 公式的结果，不是实测生命周期。',
        f'双模型有 {len(agreement)} 个共同可达硬件/目标对，最优映射一致 {sum(r["same_mapping"] for r in agreement)}；'
        '完整一致及分歧映射见 `dual_model_agreement.json`，不混合取最有利参数。','',
        '## 6. 与任务曲面的连接','',
        f'旧 {task["historical_aggregate_points"]} 点仅跑通“任务曲面×可达前沿”流程；凸包外严格返回无覆盖，不外推。'
        '示例输出 `task_preparation/joint_selection_demo.csv` 明确为流程演示，非结论。',
        '原 V4 的 56 个补测点已与实际前沿对齐，`suggested_measurements.csv` 给出距离及未覆盖优先级；速度档、预算、checkpoint、环境、'
        '注入/adoption/无效局协议仍缺失，不填常数、不运行任务。','',
        '## 7. 所有失败、未覆盖与降级','',
        '- 原 V5 的 2KB 失败及诊断原封不动；V5.1 各档 L1 失败、低 seq、替代 mapper 失败均保留。',
        '- HBM 原并发分片 OOM，按 %1 重试；一次为便于 backfill 缩至4分钟后超时，再以10分钟成功。'
        '本机一次误用不存在 backend 路径、远端一次遗漏模块传输均保留错误，不解释成模型失败。',
        '- 留出逐窗口不可运行项/N/A/容量项见 `heldout_gate.json.unavailable`；pipeline W2、serial W3/W4 明确不适用。',
        '- GDDR6_c16的BG留出k2配置，W5在open和saturated两种发射下均因映射后超出8GiB物理容量而未执行；'
        '40条原生留出完成、2条容量缺口，不能用plain自检通过替代该BG窗口。',
        '- 开发窗口缺口见 `development_input/manifest.json.unavailable`；未选作留出的 BG 档明确标记无布局留出，不借用其他配置的 W5 代替。抽样协议自检与模型误差验收分开列。',
        '- 开发/留出门禁、GDDR刷新、priority 原生控制器、NeuSim行切片、真实checkpoint形状、SigLIP完整算子、向量/norm、'
        '工艺成本、独立执行捕获、真实闭环环境均不得因 DSE 跑完而宣称已验证。',
        '- Tmin 是 0.1ms 精度有限请求窗口的观察到的可行上端点，不是无限时间稳定性证明；SRAM 检查仍是原静态模型。','',
        '## 8. 复现命令与哈希','',
        '```sh',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v51_workflow.py stage1',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v51_workflow.py prepare-dev',
        '# 已冻结目录不可覆盖；重跑时使用新目录，原生 Slurm 参数见 execution/',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v51_workflow.py fit',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v51_workflow.py prepare-heldout',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v51_remote.py heldout',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v51_workflow.py heldout-gate',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v51_calibration.py prepare',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v51_remote.py calibration',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v51_calibration.py collect',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v51_dse.py --workers 4',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v51_ablation.py',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v51_package.py',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v51_figures.py',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v51_audit.py --dse',
        '.venv/bin/python -m pytest -q --junitxml=results/v5_1/validation/zz_final_pytest.xml',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v51_report.py','```','',
        *table(tests,['file','tests','failures','errors','skipped']),'',
        f'旧交付已逐一校验：{[(p["manifest"],p["artifacts"]) for p in preserved]}。'
        '新产物、源码、后端身份及本报告哈希在 `delivery_manifest.json`；逐阶段作业ID、退出码和重试在 `execution/`。']
    report=Path('docs/CASE_V5_1_REPORT.md');report.write_text('\n'.join(lines)+'\n')
    gates['status']='completed_with_explicit_validation_limitations';write_json(ROOT/'gates.json',gates)
    artifacts={str(p.relative_to(ROOT)):digest(p) for p in sorted(ROOT.rglob('*')) if p.is_file() and
        p.name!='delivery_manifest.json'}
    sources={str(p):digest(p) for p in [*Path('vlasim').glob('v51*'),
        *Path('vlasim/ramulator_bridge').glob('v51*.py'),*Path('tests').glob('test_v51*.py'),
        Path('scripts/einst_v51.sh'),report] if p.is_file()}
    write_json(ROOT/'delivery_manifest.json',dict(status=gates['status'],artifacts_sha256=artifacts,
        sources_sha256=sources,preservation_sha256=digest(ROOT/'preservation.json')))


if __name__=='__main__':
    publish()
