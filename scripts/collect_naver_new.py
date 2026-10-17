"""네이버 검색의 '새로 오픈했어요' 칸을 동네마다 읽어 모은다.

네이버 지도에 가게를 등록하면 네이버가 '새로 오픈' 표시를 붙이고, 통합검색에
'○○동 카페'를 치면 그 동네의 새 가게를 '새로 오픈했어요' 칸에 대여섯 곳씩
보여 준다. 로컬플레이스(bizw.kr) 같은 신상 사이트가 쓰는 신호가 이것이다.
서울시 영업신고 자료(이틀 늦고 업종마다 목록이 따로 있음)나 카카오맵 비교로는
늦거나 놓치는 가게를 여기서 먼저 볼 수 있다.

순위 추적(track_ranks.py)처럼 검색 결과 화면을 읽는다. 하루 한 번, 동네마다 몇 번만
묻고, 사진은 가져오지 않으며 이름·업종·동네와 네이버 지도 링크만 남긴다.
네이버가 깃허브 서버를 가끔 막으므로, 거의 다 못 읽은 날은 파일을 건드리지 않는다.

2026-10-16 실제 화면에서 확인한 구조
  <h2 class="title">새로 오픈했어요</h2> 아래 <li data-nop_res-doc-id="플레이스번호">마다
  지도 링크(lng·lat), 이름(class="LGJdP"), 업종과 동네(class="NOJeK" 두 개)가 있다.
  '연희동 카페'를 치면 인천 서구 연희동으로 알아들어서 검색어 앞에 '서울'을 붙인다.

남기는 파일: data/naver-new.json (최근 60일 안에 본 새 가게)
"""

import html
import json
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "naver-new.json"

try:
    from collect_keywords import AREAS  # noqa: E402  (밤마다 재는 서울 동네 목록을 같이 쓴다)
except Exception:
    AREAS = ["연남동", "연희동", "성수동", "망원동", "합정동", "익선동", "서촌", "을지로",
             "한남동", "해방촌", "문래동", "송파", "잠실", "용산", "명동", "홍대"]

KINDS = [k.strip() for k in os.environ.get("NAVER_NEW_KINDS", "카페,맛집,베이커리").split(",") if k.strip()]
PREFIX = os.environ.get("NAVER_NEW_PREFIX", "서울 ")
KEEP_DAYS = 60
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

TITLE = 'class="title">새로 오픈했어요</h2>'
LI_RE = re.compile(r'<li [^>]*data-nop_res-doc-id=.*?</li>', re.S)
ITEM_RE = re.compile(
    r'data-nop_res-doc-id="(\d+)".*?place/\d+\?lng=([\d.]+)&amp;lat=([\d.]+)'
    r'.*?class="LGJdP"><span>(.*?)</span>.*?class="qI_q5">(.*?)</div>', re.S)
SPAN_RE = re.compile(r'<span class="NOJeK">(.*?)</span>')


def fetch(query):
    url = "https://search.naver.com/search.naver?query=" + urllib.parse.quote(query)
    request = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    with urllib.request.urlopen(request, timeout=25) as resp:
        return resp.read().decode("utf-8", "replace")


def read_block(page):
    """'새로 오픈했어요' 칸의 가게들. 칸이 없으면 빈 목록."""
    start = page.find(TITLE)
    if start < 0:
        return []
    end = page.find("</section>", start)
    section = page[start:end if end > 0 else len(page)]
    out = []
    for li in LI_RE.findall(section):
        if "광고" in li or "ader.naver.com" in li:
            continue                      # 광고 칸은 새 가게가 아니라 돈 낸 가게다
        m = ITEM_RE.search(li)
        if not m:
            continue
        spans = [html.unescape(s).strip() for s in SPAN_RE.findall(m.group(5))]
        place_id, lng, lat, name = m.group(1), m.group(2), m.group(3), html.unescape(m.group(4)).strip()
        out.append({
            "id": place_id,
            "name": name,
            "category": spans[0] if spans else "",
            "area": spans[1] if len(spans) > 1 else "",
            "lat": float(lat),
            "lng": float(lng),
            "url": f"https://map.naver.com/p/entry/place/{place_id}",
        })
    return out


def looks_blocked(page):
    """네이버가 막으면 짧은 빈 화면이 온다. 정상 검색 결과는 수십만 자다."""
    return len(page) < 50_000


def load_store():
    if not STORE.exists():
        return {}
    try:
        body = json.loads(STORE.read_text(encoding="utf-8"))
        return {p["id"]: p for p in body.get("places") or []}
    except Exception as exc:
        print(f"naver-new.json을 읽지 못했습니다: {exc}", file=sys.stderr)
        return {}


def main():
    today = date.today().isoformat()
    places = load_store()
    queries = [f"{PREFIX}{area} {kind}".strip() for area in AREAS for kind in KINDS]
    asked = blind = 0
    seen_today = {}

    for query in queries:
        asked += 1
        try:
            page = fetch(query)
        except Exception as exc:
            blind += 1
            print(f"  {query}: 못 읽음 ({exc})", file=sys.stderr)
            time.sleep(random.uniform(4, 8))
            continue
        if looks_blocked(page):
            blind += 1
            time.sleep(random.uniform(4, 8))
            continue
        for item in read_block(page):
            # 검색어의 동네가 다른 지역으로 읽히는 일이 있어 서울 가게만 남긴다.
            if not item["area"].startswith("서울"):
                continue
            got = seen_today.setdefault(item["id"], dict(item, queries=[]))
            got["queries"].append(query)
        # 사람이 검색하는 속도에 가깝게 쉬어 간다. 규칙적으로 두드리면 막힌다.
        time.sleep(random.uniform(2.0, 5.0))

    print(f"검색 {asked}번 중 {blind}번 못 읽음 · 오늘 '새로 오픈' 칸에서 본 서울 가게 {len(seen_today)}곳")
    if asked and blind > asked * 0.8:
        print("거의 다 못 읽어 이번 결과는 남기지 않습니다(네이버가 막은 것으로 보임).", file=sys.stderr)
        return 0

    new_count = 0
    for pid, item in seen_today.items():
        before = places.get(pid)
        if before is None:
            new_count += 1
            places[pid] = dict(item, firstSeen=today, lastSeen=today)
        else:
            before.update({k: item[k] for k in ("name", "category", "area", "lat", "lng", "url")})
            before["lastSeen"] = today
            before["queries"] = sorted(set(before.get("queries", [])) | set(item["queries"]))

    cutoff = (date.fromisoformat(today) - timedelta(days=KEEP_DAYS)).isoformat()
    kept = [p for p in places.values() if (p.get("lastSeen") or "") >= cutoff]
    kept.sort(key=lambda p: (p.get("firstSeen") or "", p.get("name") or ""), reverse=True)

    STORE.parent.mkdir(exist_ok=True)
    STORE.write_text(json.dumps({
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "note": "네이버 통합검색 '새로 오픈했어요' 칸에서 본 서울 가게. firstSeen은 우리가 처음 본 날이다.",
        "places": kept,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"처음 본 가게 {new_count}곳 · 지금 남긴 가게 {len(kept)}곳")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
