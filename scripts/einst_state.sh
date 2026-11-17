#!/usr/bin/env bash
#SBATCH --job-name=vlasim-state
#SBATCH --partition=dev
#SBATCH --nodelist=einstein
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --output=slurm-%j.log
set -euo pipefail
: "${SLURM_JOB_ID:?Submit in the isolated node-local project}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
.venv/bin/python -m pytest -q
.venv/bin/python vlasim/ramulator_bridge/state_campaign.py --training results/balance_phase4 --backend .native/backend --config configs/hbm2_8ch.json --out results/state_phase5
