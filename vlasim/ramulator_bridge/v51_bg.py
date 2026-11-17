"""Bounded-memory logical64 BG transform, exactly equivalent for even channels."""
from pathlib import Path

import numpy as np

from channel_frontend import partition_address


def map_addresses(address,owner,channels,geometry,chunk=262144):
    if channels<2 or channels%2 or np.any(address%64):
        raise ValueError('logical64 BG transform requires even channels and aligned addresses')
    output=np.empty_like(address)
    for start in range(0,len(address),chunk):
        end=min(len(address),start+chunk)
        output[start:end]=partition_address(address[start:end]//32,
            owner[start:end].astype(np.uint64),channels,32,mop_geometry=geometry)
    return output


def transform(source,destination,channels,geometry):
    with np.load(source) as data:
        arrays={key:data[key] for key in data.files}
    arrays['address']=map_addresses(arrays['address'],arrays.get('owner',arrays['core']),channels,geometry)
    np.savez_compressed(destination,**arrays)
