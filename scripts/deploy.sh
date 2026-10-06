#!/bin/sh
# Run on the hosting VM from ~/analyq after downloading the tested Compose file.
set -eu
cd "$(dirname "$0")/.."
: "${1:?Pass the lowercase GitHub owner/repository}"
: "${2:?Pass the tested commit SHA}"
case "$1" in *[!a-z0-9_./-]*|'') echo 'Invalid repository' >&2; exit 1;; esac
case "$2" in *[!a-f0-9]*|'') echo 'Invalid commit SHA' >&2; exit 1;; esac
[ "${#2}" -eq 40 ] || { echo 'Expected a full commit SHA' >&2; exit 1; }
[ -f .env.deploy ] || { echo 'Configure ~/analyq/.env.deploy first' >&2; exit 1; }
export API_IMAGE="ghcr.io/$1-api:$2"
export WEB_IMAGE="ghcr.io/$1-web:$2"
compose() { docker compose --env-file .env.deploy -f compose.deploy.yml -f compose.https.yml "$@"; }

compose pull
compose up -d --wait db
umask 077
mkdir -p backups
# This is a pre-release backup, not a substitute for scheduled off-host backups.
compose exec -T db pg_dump -U analyq -d analyq -Fc > "backups/$(date -u +%Y%m%dT%H%M%SZ)-$2.dump"
# Only one migration process runs. A failed migration never starts the new API.
compose run --rm --no-deps migrate
compose up -d --no-build --no-deps --force-recreate --wait --wait-timeout 180 api web gateway
compose exec -T web \
    wget -q -O /dev/null http://127.0.0.1:8080/api/health
printf '%s\n' "$2" > .last-deployed-sha
echo "Deployed $2"
