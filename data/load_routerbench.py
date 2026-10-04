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
pickle can run arbitrary code. Before loading, this script lists every Python
object the file would import, without running anything, and refuses to continue
unless all of them are ordinary pandas/NumPy/built-in data types. It then loads
the file with an unpickler that enforces the same allowlist.
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

# Imports a pandas DataFrame pickle legitimately needs. Anything else is refused.
ALLOWED_MODULE_PREFIXES = ("pandas.", "numpy.")
ALLOWED_MODULES = {"pandas", "numpy", "copyreg", "collections", "datetime", "_codecs"}
ALLOWED_BUILTINS = {
    "slice", "set", "frozenset", "complex", "bytearray", "list", "dict",
    "tuple", "range", "int", "float", "str", "bytes", "bool", "object",
}


PY2_MODULE_NAMES = {"__builtin__": "builtins", "copy_reg": "copyreg"}  # used by protocol-2 pickles


def is_allowed(module: str | None, name: str | None) -> bool:
    if not module or not name:
        return False
    module = PY2_MODULE_NAMES.get(module, module)
    if module == "builtins":
        return name in ALLOWED_BUILTINS
    return module in ALLOWED_MODULES or module.startswith(ALLOWED_MODULE_PREFIXES)


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
    print(f"SHA-256: {sha256(RAW)}")

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
        "sha256": sha256(RAW),
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
