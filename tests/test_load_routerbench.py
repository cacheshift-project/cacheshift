"""Safety tests for data/load_routerbench.py.

RouterBench is published as pickle files, which can run code when loaded. The
loader must accept ordinary pandas DataFrames and refuse anything else.
"""

import importlib.util
import os
import pickle
from pathlib import Path

import pandas as pd
import pytest

SPEC = importlib.util.spec_from_file_location(
    "load_routerbench", Path(__file__).resolve().parents[1] / "data" / "load_routerbench.py")
lr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lr)


class _RunsShellCommand:
    """A pickle that would run a shell command if loaded unsafely."""

    def __reduce__(self):
        return (os.system, ("echo should-never-run",))


def _refused(path: Path) -> list[str]:
    return [f"{m}.{n}" for m, n in lr.scan_imports(path) if not lr.is_allowed(m, n)]


@pytest.mark.parametrize("protocol", [2, 5])
def test_accepts_plain_dataframe(tmp_path, protocol):
    df = pd.DataFrame({"prompt": ["a", "b"], "m": [1.0, 0.0], "m|total_cost": [0.1, 0.2]})
    path = tmp_path / "ok.pkl"
    df.to_pickle(path, protocol=protocol)
    assert _refused(path) == []
    with path.open("rb") as f:
        assert lr.SafeUnpickler(f).load().equals(df)


@pytest.mark.parametrize("protocol", [2, 5])
def test_refuses_code_execution(tmp_path, protocol):
    path = tmp_path / "evil.pkl"
    path.write_bytes(pickle.dumps(_RunsShellCommand(), protocol=protocol))
    assert _refused(path), "scanner did not flag a pickle that calls os.system"
    with path.open("rb") as f, pytest.raises(pickle.UnpicklingError):
        lr.SafeUnpickler(f).load()
