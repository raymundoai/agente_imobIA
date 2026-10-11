#!/bin/sh
# Daily backup: a compressed dump of the database and an archive of the uploaded media.
# Runs inside the "backup" service; files land in the "backups" volume.
set -eu

keep_days="${BACKUP_KEEP_DAYS:-14}"
mkdir -p /backups

run_backup() {
  stamp="$(date -u +%Y-%m-%dT%H%M%SZ)"
  echo "[backup] $stamp: database"
  if ! pg_dump --format=custom --compress=9 --file="/backups/db-$stamp.dump.part"; then
    rm -f "/backups/db-$stamp.dump.part"
    return 1
  fi
  mv "/backups/db-$stamp.dump.part" "/backups/db-$stamp.dump"
  if [ "${BACKUP_MEDIA_ARCHIVE:-true}" = "true" ]; then
    echo "[backup] $stamp: media"
    if tar -czf "/backups/media-$stamp.tar.gz.part" -C /data property-images conversation-media 2>/dev/null; then
      mv "/backups/media-$stamp.tar.gz.part" "/backups/media-$stamp.tar.gz"
    else
      rm -f "/backups/media-$stamp.tar.gz.part"
      echo "[backup] media folder empty or unreadable, skipped"
    fi
  fi
  find /backups -type f -mtime "+$keep_days" -delete
  echo "[backup] done; keeping $keep_days days"
}

# One backup right away, then every 24 hours.
until pg_isready -q; do sleep 5; done
while true; do
  run_backup || echo "[backup] failed; will retry in 24h"
  sleep 86400
done
