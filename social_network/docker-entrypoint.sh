#!/bin/sh
set -e

npx prisma migrate deploy

if [ "$SEED_DB" = "true" ]; then
  echo "SEED_DB=true - seeding database..."
  npx prisma db seed
else
  echo "SEED_DB not set to true - starting with an empty database."
fi

exec npm start
