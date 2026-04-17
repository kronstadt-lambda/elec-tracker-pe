#!/bin/bash
PROJECT_DIR="/home/klambda/My_Projects/elec-tracker-pe"
cd $PROJECT_DIR || exit

echo "Iniciando pipeline..."
#./run_scraper_todos.sh && \
./run_projector.sh && \
./run_stream_builder.sh && \
./git_sync.sh