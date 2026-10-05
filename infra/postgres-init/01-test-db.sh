#!/bin/sh
# Отдельная БД для pytest. Выполняется только при первой инициализации тома.
set -e
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE ${POSTGRES_DB}_test OWNER $POSTGRES_USER;"
