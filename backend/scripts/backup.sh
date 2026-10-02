#!/usr/bin/env bash
# DB 백업. 주 1회 로컬에서 실행한다. 덤프 파일은 레포에 올리지 않는다(.gitignore의 backups/).
# 사용: DATABASE_URL='postgresql://...?sslmode=require' ./backend/scripts/backup.sh
# 필요: pg_dump (서버 버전과 같거나 높은 메이저 버전)
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL 환경변수가 필요합니다}"

out_dir="${BACKUP_DIR:-$(cd "$(dirname "$0")/../.." && pwd)/backups}"
mkdir -p "$out_dir"
file="$out_dir/grammar-$(date +%Y%m%d-%H%M%S).dump"

pg_dump --format=custom --no-owner --no-privileges --file="$file" "$DATABASE_URL"
echo "백업 완료: $file"
echo "복원: pg_restore --clean --if-exists --no-owner -d \"\$DATABASE_URL\" \"$file\""
