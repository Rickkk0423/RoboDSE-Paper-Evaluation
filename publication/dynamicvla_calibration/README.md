# DynamicVLA Native Calibration

This directory contains the compact, reviewable DynamicVLA calibration evidence.
The raw 64 MiB-per-stream CSV traces remain in the local `results/` evidence
workspace because they are large generated inputs. The source profile and
trace-generation code are retained in the repository.

The calibration is Ramulator simulator evidence for DynamicVLA traffic on the
pinned HBM2 eight-channel geometry. It is not silicon measurement and must not
be substituted into Pi0.5 results.
