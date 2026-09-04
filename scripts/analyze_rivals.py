"""상위 노출 글과 내 글이 각각 어떤 난이도의 키워드를 노리는지 견준다.

묻는 것은 하나다. 잘 나오는 사람들은 '경쟁이 센 말'로 이기는가,
아니면 '경쟁이 얕은 말'을 골라서 이기는가.

- 경쟁이 센 말로 이긴다면 그건 블로그 지수의 힘이고, 키워드를 아무리
  잘 골라도 따라잡기 어렵다.
- 경쟁이 얕은 말을 골라 이긴다면 그건 고를 줄 아는 실력이고, 우리도 할 수 있다.

검색 결과는 로그인 없이 긁고(문서 수와 관심도는 API로 잰다), 내 글은 RSS로 받는다.
"""

import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naver  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

QUERIES = [
    "성수동 카페", "연남동 카페", "한남동 카페", "익선동 카페", "을지로 카페",
    "서촌 카페", "망원동 카페", "연희동 카페", "압구정 카페", "해방촌 카페",
    "합정 맛집", "을지로 맛집", "용산 맛집", "홍대 맛집", "이태원 맛집",
    "신촌 맛집", "여의도 맛집", "망원동 맛집", "한남동 맛집", "종로 맛집",
]

MY_BLOG = "haranalice"

# 제목에서 검색어처럼 생긴 조각을 뽑을 때 쓰는 사전.
TYPE_WORDS = [
    "카페", "맛집", "베이커리", "브런치", "디저트", "술집", "이자카야",
    "파스타", "고기집", "국수", "빵집", "커피", "레스토랑", "바",
]
TITLE_RE = re.compile(
    r'href="https://blog\.naver\.com/([A-Za-z0-9_\-]+)/(\d{6,})"[^>]*>\s*'
    r'<span class="sds-comps-text sds-comps-text-ellipsis[^"]*'
    r'sds-comps-text-type-headline1[^"]*">(.*?)</span>',
    re.S,
)
TAG_RE = re.compile(r"<[^>]+>")


def fetch(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=25) as resp:
        return resp.read().decode("utf-8", "replace")


def top_titles(query, want=3):
    """블로그 탭 상위 글 제목을 순서대로 뽑는다."""
    url = ("https://search.naver.com/search.naver?ssc=tab.blog.all&sm=tab_jum"
           f"&query={urllib.parse.quote(query)}")
    try:
        html = fetch(url)
    except Exception as exc:
        print(f"  {query}: 검색 실패 {exc}", file=sys.stderr)
        return []
    out, seen = [], set()
    for match in TITLE_RE.finditer(html):
        key = f"{match.group(1)}/{match.group(2)}"
        if key in seen:
            continue
        seen.add(key)
        title = TAG_RE.sub("", match.group(3)).strip()
        if len(title) >= 12:
            out.append(title)
        if len(out) >= want:
            break
    return out


def my_titles(limit=20):
    try:
        xml = fetch(f"https://rss.blog.naver.com/{MY_BLOG}.xml")
    except Exception as exc:
        print(f"내 RSS를 읽지 못했습니다: {exc}", file=sys.stderr)
        return []
    titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", xml, re.S)
    return [t.strip() for t in titles[1:limit + 1]]


def keywords_in(title):
    """제목에서 '지역 + 업종' 꼴의 검색어 후보를 뽑는다.

    사람들이 실제로 치는 말은 대개 이 꼴이다. 가게 고유명은 경쟁이 없어
    난이도를 견주는 데 쓸모가 없으므로 여기서는 뺀다.
    """
    text = re.sub(r"[^\w가-힣A-Za-z0-9 ]", " ", title)
    words = [w for w in text.split() if w]
    found = set()
    for i, word in enumerate(words):
        for kind in TYPE_WORDS:
            if not word.endswith(kind):
                continue
            head = word[:-len(kind)]
            if len(head) >= 2:              # '성수동카페'처럼 붙여 쓴 경우
                found.add(f"{head} {kind}")
            elif i > 0 and len(words[i - 1]) >= 2:   # '성수동 카페'
                found.add(f"{words[i - 1]} {kind}")
    return found


def main():
    if not naver.enabled():
        print("네이버 인증키가 없습니다.", file=sys.stderr)
        sys.exit(1)

    print(f"상위 글 수집 ({len(QUERIES)}개 검색어 × 3위까지)")
    rival_titles = []
    for query in QUERIES:
        rival_titles += top_titles(query)
        time.sleep(0.7)
    print(f"  상위 글 {len(rival_titles)}편")

    mine = my_titles()
    print(f"  내 글 {len(mine)}편")

    groups = {"상위 노출": rival_titles, "내 글": mine}
    all_kw = set()
    per_title = {}
    for name, titles in groups.items():
        per_title[name] = [(t, keywords_in(t)) for t in titles]
        for _, kws in per_title[name]:
            all_kw |= kws

    print(f"\n검색어 후보 {len(all_kw)}개의 문서 수를 잽니다…")
    counts = {}
    for kw in sorted(all_kw):
        total = naver.total_count("blog", kw)
        if total is not None:
            counts[kw] = total
        time.sleep(0.05)
    print(f"  {len(counts)}개 측정 완료")

    print("\n=== 제목이 노리는 검색어의 난이도 ===")
    for name, rows in per_title.items():
        with_kw = [(t, [counts[k] for k in kws if k in counts])
                   for t, kws in rows]
        with_kw = [(t, c) for t, c in with_kw if c]
        if not with_kw:
            print(f"\n[{name}] 잰 검색어가 없습니다.")
            continue
        easiest = sorted(min(c) for _, c in with_kw)
        nkw = sorted(len(c) for _, c in with_kw)
        mid = easiest[len(easiest) // 2]
        print(f"\n[{name}]  제목 {len(with_kw)}편")
        print(f"  제목당 검색어 개수 중앙값 : {nkw[len(nkw) // 2]}")
        print(f"  가장 쉬운 검색어의 문서 수 중앙값 : {mid:,}")
        print(f"    3천 미만(쉬움) 비율 : "
              f"{sum(1 for e in easiest if e < 3000) / len(easiest) * 100:.0f}%")
        print(f"    2만 이상(어려움)만 있는 비율 : "
              f"{sum(1 for e in easiest if e >= 20000) / len(easiest) * 100:.0f}%")

    print("\n=== 상위 글이 노린 검색어 중 쉬운 쪽 15개 ===")
    rival_kw = set()
    for _, kws in per_title["상위 노출"]:
        rival_kw |= kws
    ranked = sorted(((counts[k], k) for k in rival_kw if k in counts))
    for total, kw in ranked[:15]:
        print(f"  {total:>9,}  {kw}")

    end = date.today()
    start = end - timedelta(days=90)
    print("\n=== 그중 수요까지 확인 (기준: 성수동 카페 = 100) ===")
    picks = [k for _, k in ranked[:12]]
    for i in range(0, len(picks), 4):
        batch = picks[i:i + 4]
        got = naver.search_trend(["성수동 카페"] + batch,
                                 start.isoformat(), end.isoformat())
        base = (got.get("성수동 카페") or [None])[-1]
        if not base:
            continue
        for kw in batch:
            series = got.get(kw)
            if not series:
                continue
            share = series[-1] / base * 100
            flow = series[-1] / series[0] if series[0] else None
            flow_txt = f"{flow:.2f}배" if flow else "–"
            print(f"  {counts[kw]:>9,}  관심도 {share:>6.1f}  흐름 {flow_txt:>7}  {kw}")
        time.sleep(0.1)


if __name__ == "__main__":
    main()
