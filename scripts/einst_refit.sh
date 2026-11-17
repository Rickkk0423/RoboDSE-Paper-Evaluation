#!/usr/bin/env bash
#SBATCH --job-name=vlasim-refit
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
.venv/bin/python vlasim/ramulator_bridge/fit_dram.py results/phase2_retry1/measurements.csv results/phase2_retry1/dram_v1_hbm2_8ch.json results/dram_v2_hbm2_8ch.json
.venv/bin/python vlasim/run_sweep.py results/dram_v2_hbm2_8ch.json --hardware configs/dse_hbm2_8ch.json --procs "${SLURM_CPUS_PER_TASK}" --out results/v2/nominal
.venv/bin/python vlasim/robustness.py results/dram_v2_hbm2_8ch.json --hardware configs/dse_hbm2_8ch.json --points 3 --procs "${SLURM_CPUS_PER_TASK}" --out results/v2/robust
.venv/bin/python vlasim/ramulator_bridge/validate_coverage.py results/dram_v2_hbm2_8ch.json --backend .native/backend --config configs/hbm2_8ch.json --out results/v2/coverage
.venv/bin/python vlasim/ramulator_bridge/validate_capacity.py results/dram_v2_hbm2_8ch.json --backend .native/backend --config configs/hbm2_8ch.json --out results/v2/capacity
