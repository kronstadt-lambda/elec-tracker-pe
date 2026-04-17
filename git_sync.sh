#!/bin/bash

PROJECT_DIR="/home/klambda/My_Projects/elec-tracker-pe"
echo "🕒 [$(date)] Iniciando sincronización de datos..."

cd $PROJECT_DIR || exit

git checkout deploy

# 1. Agregar y commitear si hay cambios
git add -f data_stream/

if ! git diff --cached --quiet; then
    git commit -m "Auto-update data: $(date +'%Y-%m-%d %H:%M:%S')"
    echo "✅ Nuevos datos commiteados."
else
    echo "ℹ️ No hay cambios nuevos en data_stream para commitear."
fi

# 2. Empujar los cambios (sean los de hoy o los que se quedaron atascados)
# Comparamos si nuestra rama local está adelantada respecto al origen
AHEAD=$(git rev-list HEAD...origin/deploy --count)

if [ "$AHEAD" -gt 0 ]; then
    echo "🚀 Subiendo $AHEAD commits pendientes a GitHub..."

    # Aquí está la corrección: id_ed25519 en lugar de id_rsa
    if GIT_SSH_COMMAND="ssh -i /home/klambda/.ssh/id_cron_github -o StrictHostKeyChecking=no" git push origin deploy; then
        echo "✅ Push exitoso."
    else
        echo "❌ Error: Falló el push a GitHub. Revisa los permisos o la conexión."
    fi
else
    echo "✅ El repositorio ya está completamente sincronizado."
fi