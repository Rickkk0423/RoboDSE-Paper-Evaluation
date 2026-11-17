#!/usr/bin/env bash
#SBATCH --job-name=vlasim-case-v3-followup
#SBATCH --partition=dev
#SBATCH --nodelist=einstein
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:10:00
#SBATCH --output=slurm-%j.log
set -euo pipefail
: "${SLURM_JOB_ID:?Submit in isolated node-local project}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
.venv/bin/python vlasim/ramulator_bridge/case_v3_followup.py --backend .native/backend --p0 results/case_v3_p0 --out results/case_v3_followup
