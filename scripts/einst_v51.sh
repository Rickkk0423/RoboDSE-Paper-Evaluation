#!/usr/bin/env bash
#SBATCH --job-name=vlasim-v51
#SBATCH --partition=cpu-scavenger
#SBATCH --qos=cpu-scavenger
#SBATCH --nodelist=einstein
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:10:00
#SBATCH --array=0-9%4
#SBATCH --output=slurm-v51-%A_%a.log
set -euo pipefail
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
mode="${V51_MODE:-selfcheck}"
input="${V51_INPUT:-results/v51_stage1_input}"
output="${V51_OUTPUT:-results/v51_selfcheck_native}"
.venv/bin/python vlasim/ramulator_bridge/v51_native.py --mode "$mode" --backend .native/backend --out "${output}/shard_${SLURM_ARRAY_TASK_ID}" --input "$input" --index "${SLURM_ARRAY_TASK_ID}"
