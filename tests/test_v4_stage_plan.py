import csv
import json

from v4_stage_plan import build


def test_grid_is_only_a_plan_and_preserves_missing_inputs(tmp_path):
    backend = tmp_path / 'backend'
    root = backend / 'source/third_party/ramulator2'
    dram = root / 'python/ramulator/dram/gddr6.py'
    mapper = root / 'src/ramulator/memory_system/channel_mapper/impl/cache_line_interleave.cpp'
    dram.parent.mkdir(parents=True)
    mapper.parent.mkdir(parents=True)
    dram.write_text("GDDR6.timing_presets = {'p': {'rate': 14000}}\n")
    mapper.write_text('power-of-two channel count')
    (backend / 'source_manifest.json').write_text('{}')
    out = tmp_path / 'plan'
    plan = build(backend, out)
    rows = list(csv.DictReader((out / 'hardware_grid_plan.csv').open()))
    assert len(rows) == len({r['config_id'] for r in rows}) == 11200
    hardware = {(r['cores'], r['memory'], r['shared_SRAM_MB'], r['private_SRAM_MB']) for r in rows}
    assert len(hardware) == plan['planned_hardware_points'] == 640
    assert plan['executed_simulations'] == 0
    assert all(not r['Tmin_s'] and not r['L_curve'] for r in rows)
    assert not (out / 'hw_grid.csv').exists()
    caps = json.loads((out / 'backend_capabilities.json').read_text())
    assert caps['requested_missing_rates_Mbps'] == [16000, 20000]
    assert caps['blocked_channel_counts'] == [12, 24]
    assert not caps['gddr6x_module_paths']
    assert all(v is None for k, v in plan['costs'].items() if k != 'status')
