#!/bin/bash
# NOTE: ray.init(address='auto') gives 22 cores without melting your machine.
cd "/Volumes/Satechi Hub/ZINC-FUSION-V15"
.venv/bin/python scripts/validate_training_tables.py
