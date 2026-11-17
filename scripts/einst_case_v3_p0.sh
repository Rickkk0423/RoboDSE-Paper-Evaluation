#!/usr/bin/env bash
#SBATCH --job-name=vlasim-case-v3-p0
#SBATCH --partition=dev
#SBATCH --nodelist=einstein
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:20:00
#SBATCH --output=slurm-%j.log
set -euo pipefail
: "${SLURM_JOB_ID:?Submit in isolated node-local project}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
.venv_complete/bin/python -m pytest -q
.venv/bin/python vlasim/ramulator_bridge/case_v3_p0.py --backend .native/backend --spec CASE_V3_SPEC.md --out results/case_v3_p0
