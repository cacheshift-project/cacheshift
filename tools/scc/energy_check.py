"""Assumption A6 on a BU SCC GPU: read NVML energy idle and under load, and
measure joules per output token for one ~8B model in full precision and 4-bit.

Run inside a GPU job (see tools/scc/energy_check.qsub). Heavy imports (pynvml,
torch, transformers) happen only when a phase needs them, so the measurement
helpers can be unit-tested on a laptop without a GPU.
"""

import argparse
from datetime import datetime, timezone
import gc
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ROOT / "data/router_smoke/questions.jsonl"
DEFAULT_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
LOAD_PROMPT = ("Explain step by step how you would reason about this question before answering it. "
               "Question: {question}")


def job_gpu(visible=None):
    """Which physical GPU this job owns, as NVML sees it.

    NVML ignores CUDA_VISIBLE_DEVICES and numbers every GPU in the node, while
    PyTorch's cuda:0 is the first *visible* GPU. On a shared SCC node, NVML
    index 0 can be another user's GPU, so read the scheduler's assignment.
    Returns ("index", n) or ("uuid", "GPU-...").
    """
    visible = os.environ.get("CUDA_VISIBLE_DEVICES") if visible is None else visible
    first = (visible or "").split(",")[0].strip()
    if not first:
        return ("index", 0)  # no restriction: a whole-node or single-GPU machine
    if first.isdigit():
        return ("index", int(first))
    if first.startswith(("GPU-", "MIG-")):
        return ("uuid", first)
    raise ValueError(f"Unrecognised CUDA_VISIBLE_DEVICES entry: {first!r}")


class NvmlMeter:
    """Total-energy counter (millijoules since driver load) and power (milliwatts) of one GPU."""

    def __init__(self, target=None):
        import pynvml
        self._nvml = pynvml
        pynvml.nvmlInit()
        self.target = target or job_gpu()
        kind, value = self.target
        self._handle = (pynvml.nvmlDeviceGetHandleByIndex(value) if kind == "index"
                        else pynvml.nvmlDeviceGetHandleByUUID(value))

    def energy_mj(self):
        return self._nvml.nvmlDeviceGetTotalEnergyConsumption(self._handle)

    def power_mw(self):
        return self._nvml.nvmlDeviceGetPowerUsage(self._handle)

    def info(self):
        nvml, handle = self._nvml, self._handle
        name = nvml.nvmlDeviceGetName(handle)
        driver = nvml.nvmlSystemGetDriverVersion()
        return {"name": name.decode() if isinstance(name, bytes) else name,
                "driver": driver.decode() if isinstance(driver, bytes) else driver,
                "memory_gib": round(nvml.nvmlDeviceGetMemoryInfo(handle).total / 2**30, 1),
                "compute_capability": ".".join(map(str, nvml.nvmlDeviceGetCudaComputeCapability(handle))),
                "power_limit_w": nvml.nvmlDeviceGetEnforcedPowerLimit(handle) / 1000,
                "nvml_target": list(self.target),
                "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
                "gpus_in_node": nvml.nvmlDeviceGetCount()}


def measure(meter, work, clock=time.perf_counter):
    """Run work() and return its energy use from the NVML counter.

    work() returns a dict that may contain "output_tokens", "input_tokens" and
    "requests"; per-token and per-request figures are added when present.
    """
    e0, t0 = meter.energy_mj(), clock()
    counts = work() or {}
    e1, t1 = meter.energy_mj(), clock()
    joules, seconds = (e1 - e0) / 1000, t1 - t0
    if seconds <= 0 or joules < 0:
        raise ValueError("Energy counter or clock did not advance; this GPU may not support NVML energy readings")
    result = {"seconds": round(seconds, 3), "joules": round(joules, 3), "mean_watts": round(joules / seconds, 2)}
    result.update(counts)
    if counts.get("output_tokens"):
        result["joules_per_output_token"] = round(joules / counts["output_tokens"], 4)
        result["output_tokens_per_second"] = round(counts["output_tokens"] / seconds, 2)
    if counts.get("requests"):
        result["joules_per_request"] = round(joules / counts["requests"], 3)
    return result


def idle(meter, seconds, sleep=time.sleep):
    """Hold the GPU idle; sample instantaneous power once a second as a cross-check."""
    samples = []

    def work():
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            samples.append(meter.power_mw() / 1000)
            sleep(1)
        return {"power_samples": len(samples)}

    result = measure(meter, work)
    if samples:
        result["sampled_watts_min_mean_max"] = [round(min(samples), 2), round(sum(samples) / len(samples), 2),
                                                round(max(samples), 2)]
    return result


def load_questions(path=QUESTIONS):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    if len(rows) != 10:
        raise ValueError(f"Expected the 10 committed smoke questions, found {len(rows)}")
    return rows


class Generator:
    """One Hugging Face causal LM on the GPU, in 'full' (bf16, or fp16 if unsupported) or '4bit' (NF4)."""

    def __init__(self, model_id, precision):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        kwargs = {"device_map": "cuda:0"}
        if precision == "4bit":
            from transformers import BitsAndBytesConfig
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=dtype)
        elif precision == "full":
            # transformers >= 4.56 renamed torch_dtype to dtype.
            from transformers import __version__ as tf_version
            major, minor = (int(x) for x in tf_version.split(".")[:2])
            kwargs["dtype" if (major, minor) >= (4, 56) else "torch_dtype"] = dtype
        else:
            raise ValueError("precision must be 'full' or '4bit'")
        start = time.perf_counter()
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs).eval()
        self.load_seconds = round(time.perf_counter() - start, 1)
        self.precision, self.dtype = precision, str(dtype).replace("torch.", "")
        self.revision = getattr(self.model.config, "_commit_hash", None)
        props = torch.cuda.get_device_properties(0)
        self.torch_gpu = {"name": props.name, "uuid": str(getattr(props, "uuid", "")) or None}

    def generate(self, text, max_new_tokens, min_new_tokens=0):
        torch, tok = self.torch, self.tokenizer
        ids = tok.apply_chat_template([{"role": "user", "content": text}], add_generation_prompt=True,
                                      return_tensors="pt")
        if not hasattr(ids, "shape"):  # newer versions return a BatchEncoding
            ids = ids["input_ids"]
        ids = ids.to(self.model.device)
        with torch.inference_mode():
            out = self.model.generate(ids, attention_mask=torch.ones_like(ids), do_sample=False,
                                      max_new_tokens=max_new_tokens, min_new_tokens=min_new_tokens,
                                      pad_token_id=tok.pad_token_id or tok.eos_token_id)
        torch.cuda.synchronize()
        return ids.shape[1], out.shape[1] - ids.shape[1], tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True)

    def close(self):
        del self.model
        gc.collect()
        self.torch.cuda.empty_cache()


def model_phases(meter, model_id, precision, questions, load_seconds, load_tokens):
    gen = Generator(model_id, precision)
    try:
        gen.generate(questions[0]["text"], 8)  # warm-up, not measured
        answers = []

        def answer_all():
            totals = {"requests": 0, "input_tokens": 0, "output_tokens": 0}
            for row in questions:
                n_in, n_out, text = gen.generate(row["text"], max_new_tokens=16)
                answers.append({"question_id": row["question_id"], "answer": text.strip()[:16]})
                totals["requests"] += 1
                totals["input_tokens"] += n_in
                totals["output_tokens"] += n_out
            return totals

        def sustained():
            totals = {"requests": 0, "input_tokens": 0, "output_tokens": 0}
            end, i = time.perf_counter() + load_seconds, 0
            while time.perf_counter() < end:
                question = questions[i % len(questions)]["text"].split("\n")[0]
                n_in, n_out, _ = gen.generate(LOAD_PROMPT.format(question=question),
                                              max_new_tokens=load_tokens, min_new_tokens=load_tokens)
                totals["requests"] += 1
                totals["input_tokens"] += n_in
                totals["output_tokens"] += n_out
                i += 1
            return totals

        return {"precision": precision, "dtype": gen.dtype, "model_revision": gen.revision,
                "torch_gpu": gen.torch_gpu,
                "load_seconds": gen.load_seconds,
                "ten_questions": {**measure(meter, answer_all), "answers": answers},
                "sustained_load": {**measure(meter, sustained), "batch_size": 1,
                                   "output_tokens_per_request": load_tokens}}
    finally:
        gen.close()


def versions():
    found = {"python": platform.python_version()}
    for name in ("torch", "transformers", "bitsandbytes", "accelerate", "pynvml"):
        try:
            found[name] = __import__(name).__version__
        except Exception:
            found[name] = None
    try:
        import torch
        found["cuda_runtime"] = torch.version.cuda
    except Exception:
        pass
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", type=Path, required=True, help="New JSON file for the report")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Hugging Face model id (gated models need HF_TOKEN)")
    parser.add_argument("--idle-seconds", type=int, default=300)
    parser.add_argument("--load-seconds", type=int, default=300, help="Sustained-load time per precision")
    parser.add_argument("--load-tokens", type=int, default=128, help="Output tokens per sustained-load request")
    parser.add_argument("--skip-model", action="store_true", help="Only the idle energy reading (quick first check)")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.exit(2, "Output exists; choose a new report file.\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    meter = NvmlMeter()
    report = {"scope": "Assumption A6 feasibility check: one GPU, batch size 1, greedy decoding",
              "started": datetime.now(timezone.utc).isoformat(), "host": platform.node(),
              "gpu": meter.info(), "versions": versions(), "model": None if args.skip_model else args.model,
              "settings": {k: v for k, v in vars(args).items() if k != "output"} | {"output": args.output.name}}
    print(f"GPU: {report['gpu']}", flush=True)
    print(f"Idle reading for {args.idle_seconds} s ...", flush=True)
    report["idle"] = idle(meter, args.idle_seconds)
    print(f"Idle: {report['idle']}", flush=True)
    report["models"] = []
    if not args.skip_model:
        questions = load_questions()
        for precision in ("full", "4bit"):
            print(f"Loading {args.model} ({precision}) ...", flush=True)
            phase = model_phases(meter, args.model, precision, questions, args.load_seconds, args.load_tokens)
            report["models"].append(phase)
            print(f"{precision}: 10 questions {phase['ten_questions']['joules_per_request']} J/request; "
                  f"sustained {phase['sustained_load'].get('joules_per_output_token')} J/token, "
                  f"{phase['sustained_load'].get('output_tokens_per_second')} tok/s", flush=True)
    report["finished"] = datetime.now(timezone.utc).isoformat()
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {args.output}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
