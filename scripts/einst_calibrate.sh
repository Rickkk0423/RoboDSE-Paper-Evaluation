#!/usr/bin/env bash
#SBATCH --job-name=vlasim-calibrate
#SBATCH --partition=dev
#SBATCH --nodelist=einstein
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:20:00
#SBATCH --output=slurm-%j.log
set -euo pipefail
: "${SLURM_JOB_ID:?Run through sbatch with --chdir set to the isolated project directory}"
test -f pyproject.toml
export UV_CACHE_DIR="${PWD}/.uv-cache"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
"$HOME/.local/bin/uv" sync --python 3.12 --extra test --extra native --locked
if [[ ! -f .native/backend/build/libneusim_ramulator_bridge.so ]]; then
    .venv/bin/python vlasim/ramulator_bridge/build_backend.py backend_source --out .native/backend --jobs "${SLURM_CPUS_PER_TASK}"
fi
.venv/bin/python -m pytest -q
.venv/bin/python vlasim/tests_check.py
.venv/bin/python vlasim/ramulator_bridge/campaign.py --backend .native/backend --out "${CAMPAIGN_OUTPUT:-results/phase2}" --procs "${SLURM_CPUS_PER_TASK}"
