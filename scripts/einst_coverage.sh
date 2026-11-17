#!/usr/bin/env bash
#SBATCH --job-name=vlasim-coverage
#SBATCH --partition=dev
#SBATCH --nodelist=einstein
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:10:00
#SBATCH --output=slurm-%j.log
set -euo pipefail
: "${SLURM_JOB_ID:?Submit with --chdir pointing to the isolated project}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
.venv/bin/python -m pytest -q
.venv/bin/python vlasim/robustness.py vlasim/calib/dram_v0_prior.json --hardware configs/dse_hbm2_8ch.json --points 3 --procs "${SLURM_CPUS_PER_TASK}" --out results/matched_prior
.venv/bin/python vlasim/ramulator_bridge/validate_coverage.py results/phase2_retry1/dram_v1_hbm2_8ch.json --backend .native/backend --config configs/hbm2_8ch.json --out results/coverage
