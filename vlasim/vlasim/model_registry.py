"""Model/workload registry shared by Pi0.5 and DynamicVLA experiments."""
import json
from pathlib import Path

from .dynamicvla_workload import DynamicVLAWorkload
from .workload import Pi05Config, Pi05Workload


def load_workload(model, *, profile=None, pi05_config=None):
    """Construct a workload adapter without changing the legacy Pi0.5 path."""
    name = str(model).lower()
    if name in {"pi05", "pi_0_5", "pi0.5"}:
        return Pi05Workload(pi05_config or Pi05Config())
    if name == "dynamicvla":
        if profile is None:
            raise ValueError("DynamicVLA requires a profile JSON or decoded profile")
        data = json.loads(Path(profile).read_text()) if isinstance(profile, (str, Path)) else profile
        return DynamicVLAWorkload(data)
    raise ValueError(f"unsupported workload model: {model}")
