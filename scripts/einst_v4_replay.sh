#!/usr/bin/env bash
#SBATCH --job-name=vlasim-v4-replay
#SBATCH --partition=dev
#SBATCH --nodelist=einstein
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --array=0-7%4
#SBATCH --output=slurm-%A_%a.log
set -euo pipefail
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
.venv/bin/python vlasim/ramulator_bridge/v4_replay_native.py --input results/v4_p0a_input --backend .native/backend --out results/v4_p0a_native/shard_${SLURM_ARRAY_TASK_ID} --shard "${SLURM_ARRAY_TASK_ID}" --shards 8
