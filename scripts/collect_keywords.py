"""키워드별 경쟁도를 재둔다.

글쓰기 화면은 정적 페이지라 브라우저에서 네이버를 직접 부를 수 없다(CORS).
그래서 자주 쓰는 동네 × 업종 조합을 미리 재서 data/keywords.json에 넣어두고,
화면은 그 파일만 읽는다.

경쟁도는 '그 검색어에 걸리는 블로그 글이 몇 건인가'로 본다. 많을수록
이미 쓴 사람이 많다는 뜻이고, 새 글이 위로 올라가기 어렵다.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naver  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

AREAS = [
    "연남동", "연희동", "성수동", "서울숲", "망원동", "합정동", "상수동",
    "익선동", "삼청동", "북촌", "서촌", "을지로", "한남동", "이태원",
    "해방촌", "후암동", "가로수길", "압구정", "청담동", "성북동", "문래동",
    "송파", "잠실", "여의도", "공덕", "신촌", "홍대", "종로", "명동",
    "용산", "강남", "삼각지", "구산", "가산동", "효창공원", "봉천동",
]

TYPES = ["카페", "맛집", "베이커리", "브런치", "디저트", "술집"]

# 뒤에 붙이면 경쟁이 훅 줄어드는 말들. 이걸로 틈새를 찾는다.
MODIFIERS = ["", "추천", "신상"]


def bucket(total):
    """문서 수를 사람이 읽을 수 있는 난이도로 바꾼다."""
    if total is None:
        return "unknown"
    if total < 3000:
        return "easy"
    if total < 20000:
        return "medium"
    return "hard"


def main():
    if not naver.enabled():
        print("네이버 인증키가 없습니다. NAVER_API_KEY_ID / NAVER_API_KEY 확인.",
              file=sys.stderr)
        sys.exit(1)

    limit = int(os.environ.get("KEYWORD_LIMIT", "900"))
    entries = {}
    asked = 0

    for area in AREAS:
        for kind in TYPES:
            for mod in MODIFIERS:
                if asked >= limit:
                    break
                query = f"{area} {kind} {mod}".strip()
                total = naver.total_count("blog", query)
                asked += 1
                if total is None:
                    continue
                entries[query] = total
                time.sleep(0.05)

    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "keywords.json").write_text(
        json.dumps({
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "note": "블로그 검색에 걸리는 문서 수. 적을수록 상위에 오르기 쉽다.",
            "buckets": {"easy": "3천 미만", "medium": "3천~2만", "hard": "2만 이상"},
            "counts": entries,
        }, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if not entries:
        print("문서 수를 하나도 받지 못했습니다.", file=sys.stderr)
        sys.exit(1)

    ranked = sorted(entries.items(), key=lambda kv: kv[1])
    print(f"검색어 {len(entries)}개를 쟀습니다 (호출 {asked}회)")
    print("  경쟁이 얕은 쪽 10개:")
    for query, total in ranked[:10]:
        print(f"    {total:>9,}  {query}")
    print("  경쟁이 깊은 쪽 5개:")
    for query, total in ranked[-5:]:
        print(f"    {total:>9,}  {query}")


if __name__ == "__main__":
    main()
