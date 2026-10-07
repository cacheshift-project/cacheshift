"""Download RouterBench (0-shot) and load it safely.

Feasibility proof for Sprint 1 (issue #8): the dataset is downloaded, loaded by
a script, and summarized, and a small sample is committed.

Usage (from the repo root):
    python data/load_routerbench.py

Writes:
    data/raw/routerbench_0shot.pkl            full download (~100 MB, NOT committed)
    data/samples/routerbench_summary.json     row count, models, benchmarks, columns
    data/samples/routerbench_0shot_sample.csv 20-question sample for development

Source: RouterBench, Hu et al. (2024), arXiv:2403.12031.
Data: https://huggingface.co/datasets/withmartian/routerbench
Code: https://github.com/withmartian/routerbench (MIT license)

Safety: RouterBench is only published as Python pickle files, and loading a
pickle can run arbitrary code. Three checks run before anything is unpickled:
1. The file's SHA-256 must match the version we reviewed (EXPECTED_SHA256).
2. Every object the pickle would import is listed without running anything,
   and each must be one of the exact constructors a DataFrame needs.
3. The file is then loaded with an unpickler that enforces the same list.
"""

from __future__ import annotations

import hashlib
import json
import pickle
import pickletools
import shutil
import ssl
import sys
import urllib.request
import warnings
from pathlib import Path

import certifi

URL = "https://huggingface.co/datasets/withmartian/routerbench/resolve/main/routerbench_0shot.pkl"
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "routerbench_0shot.pkl"
SAMPLES = ROOT / "data" / "samples"
SAMPLE_ROWS = 20
SEED = 0

# The routerbench_0shot.pkl we reviewed. A different file is refused, even if it looks safe.
EXPECTED_SHA256 = "ba4f77f19517610a707c374e99322d7750c30fc4ae7ff5527888595a1e65d36d"

# The exact constructors a DataFrame pickle needs: the RouterBench file (older NumPy
# names) plus DataFrames written by current pandas/NumPy. Whole modules are never
# allowed, because they also contain functions that write files (e.g. numpy.savetxt).
ALLOWED_GLOBALS = frozenset({
    ("builtins", "slice"),
    ("_codecs", "encode"),
    ("numpy", "dtype"),
    ("numpy", "ndarray"),
    ("numpy.core.multiarray", "_reconstruct"),
    ("numpy._core.multiarray", "_reconstruct"),
    ("numpy.core.numeric", "_frombuffer"),
    ("numpy._core.numeric", "_frombuffer"),
    ("pandas", "DataFrame"),
    ("pandas", "Index"),
    ("pandas", "RangeIndex"),
    ("pandas", "StringDtype"),
    ("pandas.arrays", "StringArray"),
    ("pandas.core.frame", "DataFrame"),
    ("pandas.core.indexes.base", "Index"),
    ("pandas.core.indexes.base", "_new_Index"),
    ("pandas.core.indexes.range", "RangeIndex"),
    ("pandas.core.internals.managers", "BlockManager"),
    ("pandas._libs.internals", "_unpickle_block"),
    ("pandas._libs.arrays", "__pyx_unpickle_NDArrayBacked"),
})

PY2_MODULE_NAMES = {"__builtin__": "builtins", "copy_reg": "copyreg"}  # used by protocol-2 pickles


def is_allowed(module: str | None, name: str | None) -> bool:
    if not module or not name:
        return False
    return (PY2_MODULE_NAMES.get(module, module), name) in ALLOWED_GLOBALS


def download(url: str, dest: Path) -> None:
    if dest.exists():
        print(f"Using cached download: {dest.relative_to(ROOT)}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url} ...")
    tmp = dest.with_suffix(".part")
    # Verify HTTPS with certifi's certificate bundle (python.org installs on macOS ship without one).
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(url, context=context) as response, tmp.open("wb") as out:
        shutil.copyfileobj(response, out)
    if sha256(tmp) != EXPECTED_SHA256:
        tmp.unlink()
        raise ValueError("Downloaded file does not match the reviewed version; not saved.")
    tmp.rename(dest)
    print(f"Saved {dest.relative_to(ROOT)} ({dest.stat().st_size / 1e6:.1f} MB)")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


STRING_OPS = {
    "SHORT_BINUNICODE", "BINUNICODE", "BINUNICODE8", "UNICODE",
    "STRING", "BINSTRING", "SHORT_BINSTRING",
}
GET_OPS = {"GET", "BINGET", "LONG_BINGET"}
PUT_OPS = {"PUT", "BINPUT", "LONG_BINPUT"}


def scan_imports(path: Path) -> set[tuple[str | None, str | None]]:
    """List every (module, name) the pickle would import. Runs no pickle code."""
    found: set[tuple[str | None, str | None]] = set()
    memo: dict[int, object] = {}
    pushed: list[object] = []   # recent string-ish pushes, for STACK_GLOBAL
    top: object = None          # best guess at the value on top of the stack
    with path.open("rb") as f:
        for opcode, arg, _pos in pickletools.genops(f):
            op = opcode.name
            if op in STRING_OPS:
                value = arg.decode("latin-1") if isinstance(arg, bytes) else arg
                pushed.append(value)
                top = value
            elif op in GET_OPS:
                value = memo.get(arg)
                pushed.append(value)
                top = value
            elif op in PUT_OPS:
                memo[arg] = top
            elif op == "MEMOIZE":
                memo[len(memo)] = top
            elif op == "GLOBAL":
                module, _, name = str(arg).partition(" ")
                found.add((module, name))
                top = None
            elif op == "STACK_GLOBAL":
                name = pushed[-1] if pushed else None
                module = pushed[-2] if len(pushed) > 1 else None
                found.add((module if isinstance(module, str) else None,
                           name if isinstance(name, str) else None))
                top = None
            elif op in ("FRAME", "PROTO", "STOP"):
                pass
            else:
                top = None
    return found


class SafeUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        if not is_allowed(module, name):
            raise pickle.UnpicklingError(f"Refused to import {module}.{name}")
        return super().find_class(module, name)


def main() -> int:
    download(URL, RAW)
    digest = sha256(RAW)
    print(f"SHA-256: {digest}")
    if digest != EXPECTED_SHA256:
        print("Refusing to load: this file is not the version we reviewed.\n"
              f"Expected {EXPECTED_SHA256}. Delete {RAW.relative_to(ROOT)} and run again.")
        return 1

    imports = scan_imports(RAW)
    refused = sorted(f"{m}.{n}" for m, n in imports if not is_allowed(m, n))
    print(f"Pickle imports {len(imports)} objects; {len(refused)} outside the allowlist.")
    if refused:
        print("Refusing to load. Unexpected imports:", *refused, sep="\n  ")
        return 1

    with RAW.open("rb") as f, warnings.catch_warnings():
        # The pickle was made with an older NumPy; its renamed-module warning is harmless.
        warnings.simplefilter("ignore", DeprecationWarning)
        df = SafeUnpickler(f).load()

    import pandas as pd  # only needed after the safety checks pass
    if not isinstance(df, pd.DataFrame):
        print(f"Expected a pandas DataFrame, got {type(df).__name__}.")
        return 1

    cost_cols = [c for c in df.columns if str(c).endswith("|total_cost")]
    models = [c.split("|")[0] for c in cost_cols]
    summary = {
        "source": URL,
        "sha256": digest,
        "rows": int(len(df)),
        "columns": [str(c) for c in df.columns],
        "models": models,
        "benchmarks": ({str(k): int(v) for k, v in df["eval_name"].value_counts().items()}
                       if "eval_name" in df.columns else None),
        "mean_score_by_model": {m: round(float(df[m].mean()), 4)
                                for m in models if m in df.columns},
        "total_cost_usd_by_model": {m: round(float(df[f"{m}|total_cost"].sum()), 2)
                                    for m in models},
    }

    SAMPLES.mkdir(parents=True, exist_ok=True)
    (SAMPLES / "routerbench_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    df.sample(n=min(SAMPLE_ROWS, len(df)), random_state=SEED).to_csv(
        SAMPLES / "routerbench_0shot_sample.csv", index=False)

    print(f"Loaded {summary['rows']:,} rows, {len(df.columns)} columns, {len(models)} models.")
    print("Models:", ", ".join(models))
    if summary["benchmarks"]:
        print("Benchmarks:", ", ".join(f"{k} ({v})" for k, v in summary["benchmarks"].items()))
    print(f"Wrote {(SAMPLES / 'routerbench_summary.json').relative_to(ROOT)} and "
          f"{(SAMPLES / 'routerbench_0shot_sample.csv').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
