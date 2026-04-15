#!/bin/bash

# Navegar a la carpeta del proyecto
cd /home/klambda/My_Projects/elec-tracker-pe/

# Crear carpeta de logs si no existe
mkdir -p logs

# Ejecutar el scraper usando Poetry
# Usamos la ruta completa de poetry para evitar errores de entorno
/home/klambda/.local/bin/poetry run python -m src.elec_tracker_pe.core >> logs/scheduler.log 2>&1