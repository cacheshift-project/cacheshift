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

*Not run yet.*
