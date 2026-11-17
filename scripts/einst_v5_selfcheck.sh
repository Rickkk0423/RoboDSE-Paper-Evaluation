#!/usr/bin/env bash
#SBATCH --job-name=vlasim-v5-selfcheck
#SBATCH --partition=dev
#SBATCH --nodelist=einstein
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --array=0-3%4
#SBATCH --output=slurm-%A_%a.log
set -euo pipefail
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
.venv/bin/python vlasim/ramulator_bridge/v5_selfcheck.py --input results/v5_selfcheck_input_v2 --backend .native/backend --out results/v5_selfcheck_native_v2/shard_${SLURM_ARRAY_TASK_ID} --shard "${SLURM_ARRAY_TASK_ID}" --shards 4
