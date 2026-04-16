#!/bin/bash

# Navegar a la carpeta del proyecto
cd /home/klambda/My_Projects/elec-tracker-pe/

# Crear carpeta de logs si no existe
mkdir -p logs

# Ejecutar el scraper usando Poetry
/home/klambda/.local/bin/poetry run python -m src.elec_tracker_pe.projector >> logs/scheduler_projector.log 2>&1