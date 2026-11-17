#!/usr/bin/env bash
#SBATCH --job-name=vlasim-v6
#SBATCH --partition=cpu-scavenger
#SBATCH --qos=cpu-scavenger
#SBATCH --nodelist=einstein
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:10:00
#SBATCH --output=slurm-v6-%A_%a.log
set -euo pipefail
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
.venv/bin/python vlasim/ramulator_bridge/v6_native.py --source "$V6_INPUT" --output "$V6_OUTPUT/shard_$SLURM_ARRAY_TASK_ID" --backend .native/backend --index "$SLURM_ARRAY_TASK_ID"
