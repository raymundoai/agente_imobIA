#!/bin/sh
# Runs in a separate Compose service with credentials limited to the backup bucket.
set -eu

: "${AWS_S3_BUCKET:?AWS_S3_BUCKET is required}"
: "${AWS_DEFAULT_REGION:?AWS_DEFAULT_REGION is required}"
prefix="${AWS_S3_PREFIX:-}"

upload() {
  latest=""
  for file in /backups/db-*.dump; do
    [ -f "$file" ] || continue
    latest="$file"
  done
  [ -n "$latest" ] || { echo "[backup-upload] no database dump found"; return 1; }

  aws s3 sync /backups "s3://${AWS_S3_BUCKET}/${prefix}database/" \
    --exclude '*' --include 'db-*.dump' --no-progress --only-show-errors
  aws s3 sync /data/property-images "s3://${AWS_S3_BUCKET}/${prefix}media/property-images/" \
    --no-follow-symlinks --no-progress --only-show-errors
  aws s3 sync /data/conversation-media "s3://${AWS_S3_BUCKET}/${prefix}media/conversation-media/" \
    --no-follow-symlinks --no-progress --only-show-errors
  aws s3api head-object --bucket "$AWS_S3_BUCKET" \
    --key "${prefix}database/${latest##*/}" >/dev/null
  echo "[backup-upload] database and media synchronized"
}

while :; do
  upload || echo "[backup-upload] failed; retrying in one hour"
  sleep 3600
done
