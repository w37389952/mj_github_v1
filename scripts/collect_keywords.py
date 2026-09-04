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
from datetime import date, datetime, timedelta
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

# 지역과 무관한 '요즘 무엇이 뜨나'를 보는 말들. 글감과 제목을 정할 때 쓴다.
# 지역×업종 격자와 달리 주제 자체의 유행을 본다.
THEMES = [
    "오마카세", "야장", "노포", "루프탑", "빵지순례", "웨이팅 맛집",
    "혼밥", "혼술", "브런치", "디저트 맛집", "베이글", "소금빵",
    "크로플", "약과", "말차", "핸드드립", "스페셜티 커피", "로스터리",
    "무인카페", "북카페", "LP카페", "감성카페", "대형카페", "루프탑 카페",
    "반려동물 동반", "노키즈존", "포토존", "뷰맛집", "한강뷰", "야경",
    "데이트 코스", "가볼만한곳", "팝업스토어", "성수동", "연남동", "익선동",
    "을지로", "한남동", "서촌", "망원동", "신상카페", "가오픈",
]


# 관심도는 요청 안에서의 상대값이라, 매번 같이 넣는 기준이 있어야 여러 번
# 나눠 부른 결과를 견줄 수 있다. 검색량이 큰 편이고 오르내림이 적은 말로 고른다.
ANCHOR = "성수동 카페"


def collect_demand(queries):
    """검색어별 관심도와 그 흐름을 잰다.

    한 번에 다섯 개까지 되므로 기준 하나 + 실제 네 개씩 나눠 부른다.
    돌려주는 값은 기준 대비 몇 %인지(demand)와, 석 달 사이 몇 배가
    되었는지(trend)다. trend가 1보다 크면 찾는 사람이 늘고 있다는 뜻이다.
    """
    end = date.today()
    start = end - timedelta(days=90)
    demand = {}
    trend = {}

    for i in range(0, len(queries), 4):
        batch = queries[i:i + 4]
        got = naver.search_trend(
            [ANCHOR] + batch, start.isoformat(), end.isoformat())
        anchor_series = got.get(ANCHOR) or []
        base = anchor_series[-1] if anchor_series else None
        if not base:
            continue
        for query in batch:
            series = got.get(query)
            if not series:
                continue
            demand[query] = round(series[-1] / base * 100, 1)
            # 첫 달이 0이면 배수를 낼 수 없다. 그런 말은 흐름을 비워 둔다.
            if len(series) >= 2 and series[0]:
                trend[query] = round(series[-1] / series[0], 2)
        time.sleep(0.1)
    return demand, trend


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

    if not entries:
        print("문서 수를 하나도 받지 못했습니다.", file=sys.stderr)
        sys.exit(1)

    demand, trend = collect_demand(sorted(entries))
    print(f"관심도를 잰 검색어 {len(demand)}개 (기준: {ANCHOR} = 100)")

    # 주제어는 지역과 무관하게 '요즘 무엇이 뜨나'를 본다.
    theme_demand, theme_trend = collect_demand(THEMES)
    themes = sorted(
        ({"word": w, "demand": theme_demand[w], "trend": theme_trend.get(w)}
         for w in theme_demand),
        key=lambda x: -(x["trend"] or 0),
    )
    print(f"주제어 {len(themes)}개를 쟀습니다")

    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "keywords.json").write_text(
        json.dumps({
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "note": ("counts는 그 검색어로 이미 쓰인 블로그 글 수(공급). "
                     "demand는 검색 관심도(수요)로, "
                     f"'{ANCHOR}'를 100으로 놓은 상대값이다. "
                     "trend는 석 달 사이 몇 배가 되었는지로, 1보다 크면 느는 중이다."),
            "anchor": ANCHOR,
            "buckets": {"easy": "3천 미만", "medium": "3천~2만", "hard": "2만 이상"},
            "counts": entries,
            "demand": demand,
            "trend": trend,
            "themes": themes,
        }, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"검색어 {len(entries)}개를 쟀습니다 (문서수 호출 {asked}회)")

    # 수요는 있는데 공급이 적은 것이 노릴 자리다.
    scored = [
        (q, entries[q], demand[q], demand[q] / max(entries[q], 1) * 1000)
        for q in entries if q in demand
    ]
    if scored:
        scored.sort(key=lambda x: -x[3])
        print("  노려볼 만한 쪽 12개 (수요는 있는데 글이 적은 순):")
        print(f"    {'문서수':>9}  {'관심도':>6}  {'흐름':>5}  검색어")
        for query, total, want, _ in scored[:12]:
            flow = trend.get(query)
            mark = f"{flow:>5.2f}" if flow else "    –"
            print(f"    {total:>9,}  {want:>6.1f}  {mark}  {query}")

    # 수요가 오르는 중인데 아직 글이 적은 자리. 가장 값진 목록이다.
    rising = [
        (q, entries[q], demand[q], trend[q])
        for q in entries
        if q in demand and q in trend and trend[q] >= 1.2 and entries[q] < 20000
    ]
    if rising:
        rising.sort(key=lambda x: -x[3])
        print()
        print("  ⭐ 뜨는 중인데 아직 글이 적은 검색어:")
        print(f"    {'문서수':>9}  {'관심도':>6}  {'흐름':>5}  검색어")
        for query, total, want, flow in rising[:12]:
            print(f"    {total:>9,}  {want:>6.1f}  {flow:>5.2f}배  {query}")
    else:
        print()
        print("  뜨는 중인 검색어는 이번엔 없습니다.")

    if themes:
        print()
        print("  요즘 뜨는 주제어 (석 달 흐름 순):")
        for t in themes[:10]:
            flow = f"{t['trend']:.2f}배" if t["trend"] else "–"
            print(f"    {flow:>7}  관심도 {t['demand']:>6.1f}  {t['word']}")
        print("  가라앉는 쪽:")
        for t in themes[-5:]:
            flow = f"{t['trend']:.2f}배" if t["trend"] else "–"
            print(f"    {flow:>7}  관심도 {t['demand']:>6.1f}  {t['word']}")


if __name__ == "__main__":
    main()
