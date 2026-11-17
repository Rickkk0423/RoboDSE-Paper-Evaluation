#!/usr/bin/env bash
#SBATCH --job-name=vlasim-order
#SBATCH --partition=dev
#SBATCH --nodelist=einstein
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:05:00
#SBATCH --output=slurm-%j.log
set -euo pipefail
: "${SLURM_JOB_ID:?Submit with --chdir pointing to the isolated project}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
.venv/bin/python -m pytest -q
.venv/bin/python vlasim/ramulator_bridge/probe_issue_order.py --backend .native/backend --config configs/hbm2_8ch.json --out results/issue_order_phase3
