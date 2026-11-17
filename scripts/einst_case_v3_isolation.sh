#!/usr/bin/env bash
#SBATCH --job-name=vlasim-v3-isolation
#SBATCH --partition=dev
#SBATCH --nodelist=einstein
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:10:00
#SBATCH --output=slurm-%j.log
set -euo pipefail
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
.venv/bin/python vlasim/ramulator_bridge/case_v3_isolation.py --backend .native/backend --traces results/case_v3_p0/traces --out results/case_v3_mop_isolation
