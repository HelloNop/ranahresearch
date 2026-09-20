#!/bin/sh
set -eu
mc alias set local http://minio:9000 "$S3_ACCESS_KEY_ID" "$S3_SECRET_ACCESS_KEY"
object="local/$S3_BUCKET/.foundation-check-$(date +%s)-$$"
trap 'mc rm "$object" >/dev/null' EXIT
printf 'ranahresearch-s3-check' | mc pipe "$object"
test "$(mc cat "$object")" = 'ranahresearch-s3-check'
printf 'PASS S3 put/get\n'
