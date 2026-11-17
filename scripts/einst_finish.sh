#!/usr/bin/env bash
#SBATCH --job-name=vlasim-final-checks
#SBATCH --partition=dev
#SBATCH --nodelist=einstein
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --output=slurm-%j.log
set -euo pipefail
: "${SLURM_JOB_ID:?Submit in the isolated node-local project}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export UV_PROJECT_ENVIRONMENT="${PWD}/.venv_complete"
export UV_CACHE_DIR="${PWD}/.uv-cache-complete"
"$HOME/.local/bin/uv" sync --python 3.12 --extra test --extra analysis --extra compute --locked
.venv_complete/bin/python -m pytest -q
.venv_complete/bin/python vlasim/tests_check.py
.venv_complete/bin/python vlasim/compute_campaign.py --snapshot .compute --calib vlasim/calib/dram_v2_hbm2_8ch.json --out results/compute_sa_linux
.venv_complete/bin/python vlasim/interval_convergence.py inputs/shortlist.csv vlasim/calib/dram_v2_hbm2_8ch.json --out results/convergence_interval_linux
.venv_complete/bin/python vlasim/analysis/task_report.py vlasim/data/libero_dynamic_L_S.csv inputs/shortlist.csv --samples inputs/robust_LS.csv --out results/task_verified_linux
