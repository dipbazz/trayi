#!/bin/sh
# Nightly backup: a consistent copy of the database and an archive of the uploads, made inside
# the running container, then copied to S3 under backups/<UTC time>/. The server's IAM role may
# write and read backups/ but not delete, so a compromised server can't wipe them; the bucket's
# lifecycle rule removes them after 30 days. Run nightly by systemd/charity-backup.timer.
set -eu

cd "$(dirname "$0")"
setting() { sed -n "s/^$1=//p" .env | tail -n 1; }
bucket=$(setting BACKUP_BUCKET)
data_dir=$(setting DATA_DIR)
data_dir=${data_dir:-/srv/charity/data}
[ -n "$bucket" ] || { echo "Set BACKUP_BUCKET in $(pwd)/.env" >&2; exit 1; }

docker compose exec -T web python manage.py backup_site /data/backups/latest

stamp=$(date -u +%Y-%m-%dT%H%M%SZ)
aws s3 cp --recursive --only-show-errors "$data_dir/backups/latest" "s3://$bucket/backups/$stamp/"
echo "Backed up to s3://$bucket/backups/$stamp/"

# Then keep each receipt screenshot 30 days at most (they're outside media/, so never backed up),
# and search logs 90 days (WAGTAILSEARCH_HITS_MAX_AGE; promoted terms stay).
# Last, so a failure here can't stop the backup. Each runs even if the other fails, so search
# logs still go on a night receipts fail; any failure still fails the run, which the journal shows.
failed=0
docker compose exec -T web python manage.py delete_old_receipts || failed=1
docker compose exec -T web python manage.py searchpromotions_garbage_collect || failed=1
exit "$failed"
