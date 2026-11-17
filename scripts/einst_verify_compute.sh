#!/usr/bin/env bash
#SBATCH --job-name=vlasim-compute-provenance
#SBATCH --partition=dev
#SBATCH --nodelist=einstein
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:10:00
#SBATCH --output=slurm-%j.log
set -euo pipefail
: "${SLURM_JOB_ID:?Submit in the isolated node-local project}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
.venv_complete/bin/python -m pytest -q
.venv_complete/bin/python vlasim/tests_check.py
.venv_complete/bin/python vlasim/compute_campaign.py --snapshot .compute --calib vlasim/calib/dram_v2_hbm2_8ch.json --out results/compute_sa_checked_linux
