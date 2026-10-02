"""data/templates.yaml을 DB의 templates 테이블에 적재한다(해당 kind의 틀을 통째로 교체).

사용: cd backend && python -m scripts.load_templates [경로]
"""

import sys
from pathlib import Path

from app.db import SessionLocal
from app.templates_service import DEFAULT_TEMPLATES_PATH, load_templates, parse_templates_file


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TEMPLATES_PATH
    try:
        entries = parse_templates_file(path)
    except ValueError as e:
        print(f"틀 파일 오류:\n{e}", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        n = load_templates(db, entries)
    print(f"틀 {n}개 적재 완료 ({path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
