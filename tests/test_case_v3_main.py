import pytest

from vlasim import DRAMModel, HWConfig, MapConfig, Simulator


def test_remaining_suffix_matches_direct_sum():
    sim = Simulator(HWConfig(slice_mode=False), MapConfig())
    group = sim.g['dit']
    group.ops = sim._dit_round_ops([0])
    while group.load_next():
        group.rem = .37
        expected_c = group.cur.flops / group.cur.util / group.peak * group.rem
        expected_c += sum(o.flops / o.util / group.peak for o in group.ops)
        expected_b = group.cur.dram_bytes * group.rem + sum(o.dram_bytes for o in group.ops)
        c, b = sim._remaining()['dit']
        assert c == pytest.approx(expected_c, rel=1e-12)
        assert b == pytest.approx(expected_b, rel=1e-12)
    group.ops = sim._dit_round_ops([1])
    group.load_next()
    assert sim._remaining()['dit'][1] > 0


def test_partition_caps_independent_of_policy():
    hw = HWConfig(dram_bw=1e9, slice_mode=False)
    rates = []
    for policy in ('fair', 'vlm_priority', 'balance'):
        sim = Simulator(hw, MapConfig(stream_partition=.625, bw_policy=policy), dram=DRAMModel())
        sim.g['vlm'].ops = sim._vlm_ops()
        sim.g['dit'].ops = sim._dit_round_ops([0])
        for group in sim.g.values():
            group.load_next()
        rate = sim._rates()
        assert rate['vlm'] * sim.g['vlm'].cur.dram_bytes <= hw.dram_bw * .85 * .625
        assert rate['dit'] * sim.g['dit'].cur.dram_bytes <= hw.dram_bw * .85 * .375
        rates.append(rate)
    assert rates[0] == rates[1] == rates[2]


def test_partition_validation():
    with pytest.raises(ValueError, match='stream_partition'):
        Simulator(HWConfig(), MapConfig(stream_partition=1))


@pytest.mark.parametrize('k', [1, 2, 3])
def test_balance_suffix_cache_preserves_slow_reference(k):
    class SlowSimulator(Simulator):
        def _remaining(self):
            out = {}
            for name, group in self.g.items():
                if group.cur is None:
                    out[name] = (0., 0.)
                    continue
                ops = [(group.cur, group.rem)] + [(op, 1.) for op in group.ops]
                out[name] = (sum(f * op.flops / max(op.util, 1e-9) / group.peak for op, f in ops),
                             sum(f * op.dram_bytes for op, f in ops))
            return out
    hw = HWConfig(n_cores=8, sram_mb=64, local_kb=2048, slice_mode=False, dram_bw=256e9)
    mp = MapConfig(vlm_cores=5, dit_stages=k, bw_policy='balance')
    fast_sim = Simulator(hw, mp)
    fast = fast_sim.run(30, 6, diagnostics=True)
    slow = SlowSimulator(hw, mp).run(30, 6, diagnostics=True)
    for key in ('L_mean', 'S_mean', 'L_p95', 'S_p95', 'dit_GB_per_req', 'dram_GB_per_req', 'dit_busy', 'vlm_busy'):
        assert fast[key] == pytest.approx(slow[key], rel=1e-9, abs=1e-10)
    assert fast_sim.run(30, 6)['S_mean'] == fast['S_mean']
