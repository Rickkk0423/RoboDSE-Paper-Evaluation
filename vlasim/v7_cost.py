"""V7 four-input patch and shared, correlated literature-cost sensitivity."""
import copy
import numpy as np

from v7_common import ROOT, load, write_json, digest
from v6_cost import coefficient, feature

PATCH = ('A_phy_LPDDR5', 'A_phy_GDDR6', 'e_dram_LPDDR5', 'e_dram_GDDR6')
AREA_KEYS = ('A_core', 'a_sram', 'A_misc', 'A_phy_LPDDR5', 'A_phy_GDDR6', 'A_phy_HBM2')


def prepare():
    base = load(ROOT / 'inputs/cost/coefficients.json')
    result = copy.deepcopy(base)
    c = result['coefficients']
    h = c['A_phy_HBM2']
    provenance = load(ROOT / 'cost/sources/numerical_verification.json')
    descriptions = {
        'A_phy_LPDDR5': (1.38, 1., 1.5, 'mm2/x16_channel', 'academic',
            'Feldmann et al., Enhanced LPDDR4X PHY in 12nm FinFET, arXiv:2503.11654',
            '(2.89-0.135)/2=1.3775, rounded to1.38. LPDDR4X->LPDDR5 proxy; bump-limited, no logic-node scaling.'),
        'A_phy_GDDR6': (h['value'] / 32 * 28 * 1.625,
            h['lower'] / 32 * 28 * 1.5, h['upper'] / 32 * 28 * 1.75,
            'mm2/28GBps_channel', 'derived_ratio', 'Rambus, Memory Systems for AI: Part6 (2020)',
            'HBM2 PHY area per32GB/s channel /32 *28 *GDDR6/HBM2 equal-bandwidth area ratio1.5-1.75.'),
        'e_dram_LPDDR5': (4., 2., 6., 'pJ/bit', 'vendor', 'Micron LPDDR5X CAMM2 Technical Brief',
            'LPDDR5X module marketing value; included components unspecified. LPDDR5 proxy;0.5-1.5 envelope.'),
        'e_dram_GDDR6': (7.5, 4.9, 11.3, 'pJ/bit', 'vendor',
            'Micron GDDR6/HBM2E comparison; Spartus arXiv:2108.02297 TableVII cross-check',
            '7.5 center;7.5*3.92/6=4.9 lower;1.5*7.5=11.25 rounded upper11.3. Not harmonized whole-system energy.'),
    }
    for key, values in descriptions.items():
        value, low, high, unit, source_type, source, conversion = values
        c[key] = coefficient(value, low, high, unit, source, conversion,
                             source_type=source_type, provenance=provenance[key],
                             supplied_by='NEXT_STEPS_V7.md Section1')
        c[key]['source_node_nm'] = 12 if key == 'A_phy_LPDDR5' else None
        if key == 'A_phy_LPDDR5':
            c[key]['node_nm'] = 12
            c[key]['technology_scaling_applied'] = False
        if key == 'A_phy_GDDR6':
            c[key].update(source_types=['derived_ratio', 'vendor'],
                          dependency='A_phy_HBM2/32*28*GDDR6_to_HBM2_PHY_ratio',
                          independent_sampling=False)
        if key == 'e_dram_GDDR6':
            c[key]['source_types'] = ['vendor', 'derived_ratio']
    for key in base['coefficients']:
        if key not in PATCH and c[key] != base['coefficients'][key]:
            raise RuntimeError('Unrequested coefficient modification')
    result.update(status='literature_estimate_V7_user_supplied_patch', blocked_inputs=[],
                  cross_type_energy_comparable=False,
                  cross_type_energy_reason='Micron device/module claims and FGDRAM whole-HBM2 accounting differ.',
                  primary_energy_scope='Same-memory-type DRAM traffic/energy ratios only; no cross-type absolute energy ranking.')
    write_json(ROOT / 'cost/coefficients.json', result)
    with np.load(ROOT / 'inputs/cost/draws.npz') as data:
        keys = list(data['keys'])
        old = data['samples'].copy()
    rng = np.random.default_rng(20261116)
    for _ in keys:
        rng.uniform(0, 1, 2000)
    columns = [old[:, i] for i in range(len(keys))]
    for key in ('A_phy_LPDDR5', 'e_dram_LPDDR5', 'e_dram_GDDR6'):
        keys.append(key)
        columns.append(rng.uniform(c[key]['lower'], c[key]['upper'], 2000))
    ratio = rng.uniform(1.5, 1.75, 2000)
    keys.append('A_phy_GDDR6')
    columns.append(old[:, list(keys[:old.shape[1]]).index('A_phy_HBM2')] / 32 * 28 * ratio)
    np.savez_compressed(ROOT / 'cost/draws.npz', keys=np.array(keys), samples=np.array(columns).T,
                        GDDR6_to_HBM2_PHY_ratio=ratio)
    write_json(ROOT / 'cost/sampling.json', dict(samples=2000, seed=20261116,
        old_draws_bitwise_preserved=True, shared_draws_across_designs=True,
        GDDR6_PHY_correlated_with_HBM2=True, ratio_distribution='uniform[1.5,1.75]',
        other_new_coefficients_distribution='independent uniform within provided bounds',
        status='model_sensitivity_not_cost_probability_or_confidence_interval',
        sha256=digest(ROOT / 'cost/draws.npz')))


def area_feature(row):
    phy = [0., 0., 0.]
    phy[('LPDDR5', 'GDDR6', 'HBM2').index(row['memory'].split('_')[0])] = int(row['memory'].split('_c')[-1])
    return np.r_[feature(row), phy]


def area_data():
    c = load(ROOT / 'cost/coefficients.json')['coefficients']
    center = np.array([c[k]['value'] for k in AREA_KEYS])
    with np.load(ROOT / 'cost/draws.npz') as data:
        keys = list(data['keys'])
        samples = data['samples'][:, [keys.index(k) for k in AREA_KEYS]]
    return c, center, samples


if __name__ == '__main__':
    prepare()
