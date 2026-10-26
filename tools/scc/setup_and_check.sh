#!/bin/bash -l
# One-time SCC setup plus a 1-minute NVML energy check (#35).
# Run from the repository root on an SCC login node:  bash tools/scc/setup_and_check.sh
# Safe to rerun: the venv and HF_HOME line are only created once.
set -eo pipefail  # no -u: conda activation scripts read unset variables
PROJECT=${CACHESHIFT_SCC_PROJECT:-ece601}
VENV=${CACHESHIFT_VENV:-$HOME/.venvs/cacheshift-energy}
HF_DIR=/projectnb/$PROJECT/$USER/hf

# Model weights (~16 GB) go to project space, not the 10 GB home directory.
grep -q "export HF_HOME=" ~/.bashrc 2>/dev/null || echo "export HF_HOME=$HF_DIR" >> ~/.bashrc
export HF_HOME=${HF_HOME:-$HF_DIR}
mkdir -p "$HF_HOME"

echo "== Loading BU's PyTorch module and the venv =="
module load miniconda
module load academic-ml/fall-2025
conda activate fall-2025-pyt
[ -x "$VENV/bin/python" ] || python -m venv --system-site-packages "$VENV"
source "$VENV/bin/activate"
pip install -q "transformers>=4.45" accelerate bitsandbytes nvidia-ml-py
python -c "import torch, transformers, pynvml; print('torch', torch.__version__, '| transformers', transformers.__version__)"

echo "== Submitting a 1-minute GPU energy check and waiting for it (the queue can take a few minutes) =="
qsub -P "$PROJECT" -sync y -l h_rt=00:20:00 \
  -v HF_HOME="$HF_HOME",CACHESHIFT_ENERGY_ARGS="--skip-model --idle-seconds 60" \
  tools/scc/energy_check.qsub
log=$(ls -t cacheshift-energy.o* | head -1)
echo "== $log =="
cat "$log"
