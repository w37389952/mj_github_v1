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

# 글쓰기 화면의 동네 표(AREA_MAP)와 맞춰 둔다. 여기 없는 동네는 경쟁도가
# 비어 보이고, 옆 동네의 큰 검색어만 잡혀 '어려움'만 뜬다. 실제로
# 2026-09-09에 동교동이 빠져 있어 그런 일이 있었다.
AREAS = [
    "연남동", "연희동", "동교동", "서교동", "성수동", "서울숲", "망원동",
    "합정동", "상수동", "성산동", "익선동", "삼청동", "북촌", "서촌",
    "을지로", "한남동", "이태원", "해방촌", "후암동", "남영동", "청파동",
    "가로수길", "압구정", "청담동", "신사동", "논현동", "역삼동",
    "성북동", "삼선동", "문래동", "영등포", "당산동", "송파", "잠실",
    "방이동", "여의도", "공덕", "아현동", "신촌", "홍대", "종로", "명동",
    "충무로", "신당동", "용산", "강남", "삼각지", "구산", "응암동",
    "불광동", "연신내", "가산동", "독산동", "효창공원", "효창동",
    "봉천동", "신림동", "화곡동", "등촌동", "제기동",
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
    # 화면에 두 줄로 갈라 보여 주므로 후보를 넉넉히 둔다.
    "티라미수", "휘낭시에", "에그타르트", "스콘", "카눌레", "도넛",
    "샌드위치", "파스타", "리조또", "라멘", "우동", "돈까스",
    "와인바", "위스키바", "칵테일바", "하이볼", "막걸리", "전집",
    "노키즈", "혼자 가기 좋은", "작업하기 좋은", "조용한", "통창", "야외 좌석",
    # 태그로 자주 쓰는 말. 실제 검색량을 재어 두어야 붙일지 말지 판단할 수 있다.
    "모임장소", "단체석", "회식장소", "기념일", "분위기 좋은", "주차 가능",
]


# 관심도는 요청 안에서의 상대값이라, 매번 같이 넣는 기준이 있어야 여러 번
# 나눠 부른 결과를 견줄 수 있다. 검색량이 큰 편이고 오르내림이 적은 말로 고른다.
ANCHOR = "성수동 카페"


def month_window(months=6):
    """이번 달은 아직 안 끝났으므로 뺀다.

    지난달까지 끝난 달만 본다. 안 그러면 5일치와 한 달치를 견주게 되어
    모든 검색어가 줄어드는 것처럼 보인다. 2026-09-05 첫 수집에서
    주제어 42개가 전부 하락으로 나온 것이 그 탓이었다.
    """
    first_this_month = date.today().replace(day=1)
    end = first_this_month - timedelta(days=1)          # 지난달 말일
    start = end.replace(day=1)
    for _ in range(months - 1):
        start = (start - timedelta(days=1)).replace(day=1)
    return start, end


def week_window(weeks=8):
    """이번 주도 아직 안 끝났으므로 뺀다. 지난 일요일까지만 본다."""
    end = date.today() - timedelta(days=date.today().weekday() + 1)
    start = end - timedelta(days=7 * weeks - 1)
    return start, end


def collect_weekly(queries):
    """주 단위로 재서 '지난주에 갑자기 뛴 말'을 잡는다.

    달 단위는 굼떠서 이번 주에 불붙은 것을 놓친다. 대신 주 단위는
    들쭉날쭉해서 한 주 값만으로는 못 믿는다. 그래서 지난주를 그 앞
    두 주의 평균과 견준다.
    """
    start, end = week_window(8)
    out = {}
    for i in range(0, len(queries), 5):
        batch = queries[i:i + 5]
        got = naver.search_trend(
            batch, start.isoformat(), end.isoformat(), time_unit="week")
        for query in batch:
            series = [v for v in (got.get(query) or []) if v is not None]
            if len(series) < 3:
                continue
            before = (series[-2] + series[-3]) / 2
            if before:
                out[query] = round(series[-1] / before, 2)
        time.sleep(0.1)
    return out


def collect_demand(queries):
    """검색어별 관심도와 흐름 두 가지를 잰다.

    한 번에 다섯 개까지 되므로 기준 하나 + 실제 네 개씩 나눠 부른다.

    demand — 기준 검색어 대비 몇 %인지. 얼마나 많이 찾는가.
    hot    — 지난달이 그 앞달의 몇 배인가. 지금 뜨는 중인가.
    trend  — 지난달이 석 달 전의 몇 배인가. 꾸준히 오르는가.
    """
    start, end = month_window(6)
    demand, hot, trend = {}, {}, {}

    for i in range(0, len(queries), 4):
        batch = queries[i:i + 4]
        got = naver.search_trend(
            [ANCHOR] + batch, start.isoformat(), end.isoformat())
        anchor_series = got.get(ANCHOR) or []
        base = anchor_series[-1] if anchor_series else None
        if not base:
            # 2026-09-07 첫 수집에서 648개 중 352개만 값을 받았다. 기준이 빠지면
            # 그 묶음 전체를 버리게 되므로 한 번은 다시 물어본다.
            time.sleep(1.5)
            got = naver.search_trend(
                [ANCHOR] + batch, start.isoformat(), end.isoformat())
            anchor_series = got.get(ANCHOR) or []
            base = anchor_series[-1] if anchor_series else None
        if not base:
            continue
        for query in batch:
            series = [v for v in (got.get(query) or []) if v is not None]
            if not series:
                continue
            demand[query] = round(series[-1] / base * 100, 1)
            if len(series) >= 2 and series[-2]:
                hot[query] = round(series[-1] / series[-2], 2)
            if len(series) >= 4 and series[-4]:
                trend[query] = round(series[-1] / series[-4], 2)
        time.sleep(0.1)
    return demand, hot, trend


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

    demand, hot, trend = collect_demand(sorted(entries))
    print(f"관심도를 잰 검색어 {len(demand)}개 (기준: {ANCHOR} = 100)")

    # 주제어는 지역과 무관하게 '요즘 무엇이 뜨나'를 본다.
    theme_demand, theme_hot, theme_trend = collect_demand(THEMES)
    theme_week = collect_weekly(THEMES)
    themes = sorted(
        ({"word": w,
          "demand": theme_demand[w],
          "hot": theme_hot.get(w),
          "week": theme_week.get(w),
          "trend": theme_trend.get(w)}
         for w in theme_demand),
        key=lambda x: -max(x["hot"] or 0, x["week"] or 0),
    )
    print(f"주제어 {len(themes)}개를 쟀습니다 (주 단위 {len(theme_week)}개 포함)")

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
            "hot": hot,
            "trend": trend,
            "themes": themes,
        }, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"검색어 {len(entries)}개를 쟀습니다 (문서수 호출 {asked}회)")

    # 수요는 있는데 공급이 적은 것이 노릴 자리다.
    #
    # 수요만 크면 위로 올리면 안 된다. 2026-09-05 첫 수집에서 '해방촌 맛집'
    # (글 15만 건)이 '노려볼 만한 쪽'에 올라왔다. 지수가 낮은 블로그가
    # 15만 건짜리 자리를 먹을 수는 없다. 그래서 경쟁도에 상한을 둔다.
    MAX_DOCS = int(os.environ.get("MAX_DOCS", "20000"))
    # 2026-09-07 첫 결과에서 이 값이 3.0이면 여섯 개만 남고 전부 '브런치'였다.
    # 지역+업종 조합은 관심도가 대체로 낮게 나오므로 문턱을 내린다.
    MIN_DEMAND = float(os.environ.get("MIN_DEMAND", "1.0"))

    scored = [
        (q, entries[q], demand[q], demand[q] / max(entries[q], 1) * 1000)
        for q in entries
        if q in demand and entries[q] <= MAX_DOCS and demand[q] >= MIN_DEMAND
    ]
    if scored:
        scored.sort(key=lambda x: -x[3])
        print(f"  노려볼 만한 쪽 12개 (글 {MAX_DOCS:,}건 이하 중 수요 대비 공급이 적은 순):")
        print(f"    {'문서수':>9}  {'관심도':>6}  {'최근':>5}  검색어")
        for query, total, want, _ in scored[:12]:
            flow = hot.get(query)
            mark = f"{flow:>5.2f}" if flow else "    –"
            print(f"    {total:>9,}  {want:>6.1f}  {mark}  {query}")
    else:
        print(f"  글 {MAX_DOCS:,}건 이하이면서 수요가 있는 검색어가 없습니다.")

    # 수요가 오르는 중인데 아직 글이 적은 자리. 가장 값진 목록이다.
    rising = [
        (q, entries[q], demand[q], hot[q])
        for q in entries
        if q in demand and q in hot
        and hot[q] >= 1.15 and entries[q] <= MAX_DOCS and demand[q] >= MIN_DEMAND
    ]
    if rising:
        rising.sort(key=lambda x: -x[3])
        print()
        print("  ⭐ 뜨는 중인데 아직 글이 적은 검색어:")
        print(f"    {'문서수':>9}  {'관심도':>6}  {'최근':>5}  검색어")
        for query, total, want, flow in rising[:12]:
            print(f"    {total:>9,}  {want:>6.1f}  {flow:>5.2f}배  {query}")
    else:
        print()
        print("  뜨는 중인 검색어는 이번엔 없습니다.")

    if themes:
        print()
        print("  ⚡ 지난주에 뛴 주제어 (그 앞 두 주 평균 대비):")
        weekly = sorted((t for t in themes if t["week"]),
                        key=lambda x: -x["week"])[:8]
        for t in weekly:
            print(f"    {t['week']:>5.2f}배  관심도 {t['demand']:>7.1f}  {t['word']}")
        print()
        print("  🔥 지난달에 뛴 주제어 (그 앞달 대비):")
        monthly = sorted((t for t in themes if t["hot"]),
                         key=lambda x: -x["hot"])[:8]
        for t in monthly:
            print(f"    {t['hot']:>5.2f}배  관심도 {t['demand']:>7.1f}  {t['word']}")
        print()
        print("  가라앉는 쪽:")
        for t in sorted((t for t in themes if t["hot"]), key=lambda x: x["hot"])[:5]:
            print(f"    {t['hot']:>5.2f}배  관심도 {t['demand']:>7.1f}  {t['word']}")
        print()
        print("  꾸준히 인기 있는 주제어 (관심도 순):")
        for t in sorted(themes, key=lambda x: -x["demand"])[:10]:
            flow = f"{t['trend']:.2f}배" if t["trend"] else "–"
            print(f"    관심도 {t['demand']:>7.1f}  석달흐름 {flow:>7}  {t['word']}")


if __name__ == "__main__":
    main()
