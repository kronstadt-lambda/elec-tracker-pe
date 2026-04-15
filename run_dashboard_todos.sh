#!/bin/bash

# Navegar al directorio del proyecto
cd /home/klambda/My_Projects/elec-tracker-pe/

# Matar cualquier instancia previa de Streamlit corriendo en el puerto 8501 para evitar conflictos
pkill -f "streamlit run"

# Ejecutar el dashboard en segundo plano (nohup) y silenciar la salida
nohup poetry run streamlit run src/elec_tracker_pe/dashboard.py > logs/dashboard.log 2>&1 &

echo "🚀 Dashboard Retro ONPE iniciado en segundo plano."
echo "🌐 Abre tu navegador en: http://localhost:8501"
echo "🛑 Para detenerlo, ejecuta: pkill -f 'streamlit run'"