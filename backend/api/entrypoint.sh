#!/bin/sh

if [ "$RUN_MIGRATIONS" = "true" ]; then
  echo "Running database migrations..."
  alembic upgrade head
fi

exec "$@"
