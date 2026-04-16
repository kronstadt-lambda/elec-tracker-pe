#!/bin/bash

# Navegar a la carpeta del proyecto
cd /home/klambda/My_Projects/elec-tracker-pe/

# Crear carpeta de logs si no existe
mkdir -p logs

# Ejecutar el empaquetador de datos usando Poetry
# Asumimos que stream_builder.py está en src/elec_tracker_pe/
/home/klambda/.local/bin/poetry run python -m src.elec_tracker_pe.stream_builder >> logs/scheduler_stream.log 2>&1