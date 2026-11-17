"""Native V5.1 memory identities and mapper-derived row-span metadata."""
from contextlib import ExitStack, contextmanager
from math import prod
from pathlib import Path

import yaml

from case_v3_p0 import digest


def catalog():
    rows = []
    for channels in (4, 8, 16, 32):
        rows.append(dict(id=f'LPDDR5_c{channels}', standard='LPDDR5', channels=channels,
            organization='LPDDR5_16Gb_x16' if channels == 4 else 'LPDDR5_8Gb_x16',
            timing='LPDDR5_6400', controller='LPDDR5', refresh='PerBank'))
    for channels in (16, 24, 36):
        rows.append(dict(id=f'GDDR6_c{channels}', standard='GDDR6', channels=channels,
            organization='GDDR6_8Gb_x16', timing='GDDR6_14000_1250mV_double',
            controller='GenericDDR', refresh='NoRefresh'))
    for channels in (8, 16, 32):
        rows.append(dict(id=f'HBM2_c{channels}', standard='HBM2', channels=channels,
            organization='HBM2_8Gb', timing='HBM2_2000Mbps', controller='HBM12',
            refresh='HBMPerBankRefresh'))
    return rows


def row_spans(counts, levels, prefetch, transaction_bytes, channels):
    column = levels.index('Column')
    row = levels.index('Row')
    column_transactions = counts[column] // prefetch
    if column_transactions < 4 or column_transactions & (column_transactions-1):
        raise ValueError('unsupported MOP4CLXOR column geometry')
    domains = prod(counts[1:row])
    physical_row = column_transactions * transaction_bytes
    return dict(physical_row_bytes=physical_row, channels=channels,
                row_domains_per_channel=domains, B_ch=physical_row*channels,
                level1_bytes=physical_row*channels,
                level2_bytes=physical_row*channels*domains,
                mapper='MOP4CLXOR', native_transaction_bytes=transaction_bytes,
                prefetch=prefetch, hierarchy=dict(zip(levels, counts)),
                intra_channel_bit_order=['column_low_2', *levels[1:row],
                                        'column_remaining', 'row_remaining'],
                column_bits=column_transactions.bit_length()-1,
                xor='Every mapped pre-column field, including Row, is XORed with '
                    'successive column-bit slices, as in pinned mop4clxor.cpp. '
                    'Level2 covers all rank/SID/bank domains; it is not one physical row.',
                derivation='row_bytes = (columns / prefetch) * native_transaction_bytes; '
                    'B_ch = row_bytes * channels; B_all = B_ch * product(pre-row domains). '
                    'Channel demux removes native-transaction channel digits before MOP4CLXOR.')


def export(config, path, mapper='MOP4CLXOR', *, force_instances=False):
    from neusim_ramulator.upstream import add_upstream
    add_upstream('RAMULATOR_ROOT', 'third_party/ramulator2/python')
    import ramulator as ram
    standard = getattr(ram.dram, config['standard'])
    channels = config['channels']
    independent = force_instances or bool(channels & (channels-1))
    count = 1 if independent else channels
    controllers = []
    for _ in range(count):
        device = standard(org_preset=config['organization'], timing_preset=config['timing'])
        controllers.append(getattr(ram.controller, config['controller'])(dram=device,
            scheduler=ram.scheduler.FRFCFS(), row_policy=ram.row_policy.Open(),
            addr_mapper=getattr(ram.addr_mapper, mapper)(),
            refresh_manager=getattr(ram.refresh_manager, config['refresh'])()))
    expanded = ram.memory_system.GenericDRAM(clock_ratio=1, controllers=controllers,
        channel_mapper=ram.channel_mapper.CacheLineInterleave()).to_config()
    dram = expanded['controllers'][0]['dram']
    tx = dram.get('data_payload_bytes', standard.internal_prefetch_size*dram['channel_width']//8)
    counts = dram['org']['count']
    capacity = count*prod(counts)//standard.internal_prefetch_size*tx
    path = Path(path)
    path.write_text(yaml.safe_dump(dict(frontend=dict(impl='NeuSimExternal', num_cores=2,
        address_capacity_bytes=capacity), memory_system=expanded), sort_keys=False))
    rate = dram['timing'][standard.timing_params.index('rate')]
    levels = list(standard.levels)
    bits = [n.bit_length()-1 for n in counts[1:]]
    bits[-1] = (counts[-1]//standard.internal_prefetch_size).bit_length()-1
    spans = row_spans(counts, levels, standard.internal_prefetch_size, tx, channels)
    if mapper != 'MOP4CLXOR':
        spans['mapper'] = mapper
        spans['scope'] = 'alternative mapper diagnostic; do not reuse MOP-specific bit-order claims'
    return dict(config=config, peak_GBps=channels*dram['channel_width']/8*rate/1000,
        transaction_bytes=tx, capacity_bytes=capacity*(channels if independent else 1),
        instance_capacity_bytes=capacity, instances=channels if independent else 1,
        aggregate_bus_bits=channels*dram['channel_width'], mapper=mapper,
        frontend='v51-modulo-bijective-independent-channel-instances' if independent
                 else 'v5-real-cycle-channel-fifo-rr',
        instance_address_mapping='channel = (address/32) % channels; '
            'local_address = floor((address/32)/channels)*32; no capacity modulo or aliasing',
        mop_geometry=(bits, levels.index('BankGroup')-1), row_spans=spans,
        yaml_sha256=digest(path), expanded=expanded,
        refresh_scope='NoRefresh matches pinned GDDR6 smoke test; physical refresh impact unvalidated'
                      if config['refresh']=='NoRefresh' else config['refresh'])


@contextmanager
def memories(Ramulator, path, library, geometry):
    with ExitStack() as stack:
        devices = [stack.enter_context(Ramulator(path, library=library))
                   for _ in range(geometry['instances'])]
        yield devices if len(devices)>1 else devices[0]


def finalize(devices, directory, label):
    paths = []
    for i, device in enumerate(devices if isinstance(devices, list) else [devices]):
        path = Path(directory)/f'{label}_stats_{i}.yaml'
        device.finalize(path)
        paths.append(path)
    return paths


def check_accounting(native, stats, bytes_by_stream):
    reads = writes = served_reads = served_writes = 0
    for path in stats:
        raw = yaml.safe_load(Path(path).read_text())['memory_system']
        controllers = raw['controller']
        if isinstance(controllers, dict):
            controllers = [controllers]
        reads += raw['total_num_read_requests']
        writes += raw['total_num_write_requests']
        served_reads += sum(c.get('num_read_reqs_served',0)+c.get('num_read_reqs_forwarded',0)
                            for c in controllers)
        served_writes += sum(c.get('num_write_reqs_served',0)+c.get('num_write_reqs_coalesced',0)
                             for c in controllers)
    if (native['accepted'] != native['completed'] or native['completed'] != reads+writes
            or reads != served_reads or writes != served_writes
            or native['logical_bytes'] != sum(bytes_by_stream)
            or [n*32 for n in native['stream_transactions']] != bytes_by_stream):
        raise RuntimeError('HARD_STOP_native_accounting_mismatch')
    return dict(reads=reads, writes=writes, served_reads=served_reads,
                served_writes=served_writes, passed=True)
