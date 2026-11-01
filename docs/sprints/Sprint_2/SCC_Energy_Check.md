# SCC GPU energy check (assumption A6)

*Sprint 2 · owner: Anthony · runs on the BU Shared Computing Cluster (SCC), not a laptop*

**What it checks (proposal A6):** that we can read GPU energy on the SCC and run one ~8B model there in
full precision and in 4-bit. This is the feasibility step for the energy stretch goal (RQ4); it is not the
RQ4 experiment itself.

**What the script does** ([`tools/scc/energy_check.py`](../../../tools/scc/energy_check.py)):

1. **Idle:** 5 minutes with no model loaded. Energy comes from NVML's total-energy counter
   (`nvmlDeviceGetTotalEnergyConsumption`), cross-checked against once-a-second power samples.
2. **For each precision (full = bf16, or fp16 on older GPUs; then 4-bit NF4):** load
   `meta-llama/Llama-3.1-8B-Instruct`, warm up once (not measured), then
   - answer the 10 committed smoke questions (`data/router_smoke/questions.jsonl`): joules per request;
   - **sustained load:** 5 minutes of back-to-back 128-token answers at batch size 1: joules per output
     token and tokens per second.
3. Writes one JSON report with the GPU model, driver, library versions, model revision and every reading.
   It contains no token or credential.

Energy is the whole GPU's counter during each phase, so another job on the same GPU would inflate it; the
job requests a whole GPU (`-l gpus=1`). Batch size 1 and greedy decoding only: this is a feasibility
check, not the load-dependent measurement RQ4 needs.

## One-time setup (on the SCC)

**Shortcut:** after cloning (first two lines below), `bash tools/scc/setup_and_check.sh` does the rest of
this setup and the 2-minute check as a batch job, then prints the log. You still need step 3 (Llama
licence and token) before the full run.

```bash
ssh <bu_login>@scc1.bu.edu
# 1. Work in project space: home is only 10 GB and the model is ~16 GB.
cd /projectnb/ece601/$USER
git clone https://github.com/cacheshift-project/cacheshift.git && cd cacheshift
echo "export HF_HOME=/projectnb/ece601/$USER/hf" >> ~/.bashrc && source ~/.bashrc

# 2. A small venv on top of BU's PyTorch module, for the extra libraries.
module load miniconda academic-ml/fall-2025 && conda activate fall-2025-pyt
python -m venv --system-site-packages ~/.venvs/cacheshift-energy
source ~/.venvs/cacheshift-energy/bin/activate
pip install "transformers>=4.45" accelerate bitsandbytes nvidia-ml-py

# 3. Llama 3.1 is gated: accept the licence at
#    https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct, create a read token, then:
hf auth login          # older versions: huggingface-cli login
```

The token is saved under `$HF_HOME`, outside the repository. Never paste it into a file in the repo.
If the licence is not approved in time, use an open model instead (see below) and record which one.

## Run it

**Quick check first (2 minutes, interactive):** does NVML energy work on an SCC GPU at all?

```bash
qrsh -P ece601 -l gpus=1 -l gpu_c=7.0 -pe omp 4
cd /projectnb/ece601/$USER/cacheshift
module load miniconda academic-ml/fall-2025 && conda activate fall-2025-pyt
source ~/.venvs/cacheshift-energy/bin/activate
python tools/scc/energy_check.py --skip-model --idle-seconds 60 --output experiments/results/scc-energy-quick/report.json
exit
```

**Full check (batch job, about 20–30 minutes plus the first model download):**

```bash
qsub -P ece601 tools/scc/energy_check.qsub
qstat -u $USER                       # watch it; the log is cacheshift-energy.o<job id>
```

Fallback model if Llama is not approved yet:
`qsub -P ece601 -v CACHESHIFT_ENERGY_ARGS="--model Qwen/Qwen2.5-7B-Instruct" tools/scc/energy_check.qsub`

## What to commit

- `experiments/results/scc-energy-<job id>/report.json` and the job log (check the log contains no token).
- In this file, under **Result**: the GPU you got, the module and queue settings that actually worked,
  idle watts, and joules per output token and tokens per second for full precision and 4-bit.

## Result

**Quick check, 25 Oct 2026 (job 8282386, `--skip-model --idle-seconds 60`): NVML energy works on the SCC.**

| GPU | Driver | Memory | Compute capability | Power limit |
|---|---|---|---|---|
| NVIDIA L40S | 610.57.04 | 45 GiB | 8.9 | 350 W |

- Idle for 60.0 s: 2,088.8 J from the energy counter, i.e. **34.8 W**. The 60 once-a-second power samples
  read 35.0 to 35.3 W (mean 35.1 W), so the counter and the instantaneous readings agree within 1%.
- `-l gpu_c=7.0` was granted an L40S (bf16-capable), and the module/venv setup in
  `tools/scc/setup_and_check.sh` worked as written with `academic-ml/fall-2025`.
- **Caveat found:** the node had four L40S GPUs, and this run read NVML index 0, which is not necessarily
  the GPU the scheduler assigned to the job. The idle figure is therefore an L40S idle reading but possibly
  not of our GPU. The script now reads the GPU named in `CUDA_VISIBLE_DEVICES` and records it
  (`nvml_target`, `cuda_visible_devices`, and PyTorch's device) in the report.
- The quick-check `report.json` was not committed (it predates the fix); the full run will be.

**Full run, 26 Oct 2026 (job 8291245, `meta-llama/Llama-3.1-8B-Instruct`, default settings): A6 holds.**
The job was assigned GPU 0 (`CUDA_VISIBLE_DEVICES=0`) on a node with four L40S GPUs, and NVML read
that same GPU, so these readings are of our GPU.

| Phase | Full precision (bf16) | 4-bit (NF4) |
|---|---:|---:|
| 10 smoke questions (short answers), J per request | 17.54 | 17.80 |
| Sustained load: J per output token | **6.28** | **3.59** |
| Sustained load: output tokens per second | 41.5 | 59.0 |
| Implied mean GPU power under load (J/token × tokens/s) | ≈ 261 W | ≈ 212 W |

Idle for 300 s before loading any model: 10,040.8 J, **33.5 W**; once-a-second samples 33.2 to 33.9 W
(mean 33.6 W).

- **4-bit used 43% less energy per output token and was 42% faster** at batch size 1. On this GPU,
  decoding one request at a time is limited by reading the weights from memory, and 4-bit weights are
  about a quarter of the size.
- **Short answers cost the same in both** (about 17.5 J each): the smoke questions ask for a single
  letter, so processing the prompt dominates and there are almost no output tokens to save on.
- These are whole-GPU figures and include idle power. Subtracting 33.5 W idle gives about 5.5 J/token
  (full) and 3.0 J/token (4-bit).
- **Limits:** one GPU, one run, batch size 1, greedy decoding, 128-token answers, no repeat runs or
  intervals. This is a feasibility check. RQ4 needs readings at several load levels and repeats.

- Full and 4-bit gave the same letter on 9 of the 10 smoke questions (they differ on
  `arc-challenge.test.1043`). Ten questions say nothing about accuracy; this only shows both versions answer.
- Software: Python 3.12.11, torch 2.8.0+cu128, transformers 4.55.0, bitsandbytes 0.50.2, model revision
  `0e9e39f2`. Load time 47.7 s (bf16, first load after a 39 s download) and 13.6 s (4-bit, from cache).

Report: [`experiments/results/scc-energy-8291245/report.json`](../../../experiments/results/scc-energy-8291245/report.json)
(downloaded from the SCC via OnDemand; checked to contain no token). The job log is not committed: it
only repeats these numbers plus about 250 transformers warnings that are now silenced.
