"""카카오맵에 '어제 없던 가게'가 생겼는지 매일 견준다.

서울시 영업신고 자료는 업종마다 목록이 따로 있고(26가지) 신고 이틀 뒤에야 실린다.
그래서 송파 무수이(차 브랜드의 티룸)나 서대문 누도처럼 다른 업종으로 신고했거나
아직 안 실린 가게를 놓쳤다. 카카오맵은 신고 업종과 상관없이 지도에 올라온 가게를
보여 주므로 두 번째 그물로 쓴다.

카카오 로컬 API의 '카테고리로 장소 검색'은 사각형 안의 카페(CE7)·음식점(FD6)을
한 번에 최대 45곳까지 준다(2026-10-16 공식 문서 확인). 그래서 서울을 칸으로 나누고,
한 칸에 45곳이 넘으면 네 칸으로 다시 쪼갠다. 오픈일 같은 필드는 없으므로
'어제까지 한 번도 못 본 가게 ID'를 새 가게로 본다.

하루 무료 한도는 카테고리 검색 10만 번이다. 넘치면 429로 막힐 뿐 돈이 나가지는 않는다.
키(KAKAO_REST_KEY)가 없으면 아무것도 하지 않고 끝낸다.

남기는 파일
  data/kakao-seen.json  처음 본 날별 가게 ID. 무엇이 새것인지 가르는 기준이다.
  data/kakao-new.json   최근 30일 안에 처음 본 가게(화면에 보여 줄 것)
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SEEN = DATA / "kakao-seen.json"
NEW = DATA / "kakao-new.json"

KEY = os.environ.get("KAKAO_REST_KEY", "").strip()
URL = "https://dapi.kakao.com/v2/local/search/category.json"
GROUPS = {"CE7": "카페", "FD6": "음식점"}

# 서울을 넉넉히 덮는 사각형(경도, 위도). 밖으로 삐져나온 곳은 주소로 거른다.
SEOUL = (126.76, 37.41, 127.19, 37.72)
START_SPLIT = 8          # 처음에 8×8칸으로 나눈다
# 칸 너비가 이보다 작으면 더 안 쪼갠다(약 25m). 처음엔 100m였는데, 먹자골목처럼
# 100m 안에 가게가 45곳 넘게 몰린 곳은 일부를 못 봐 새 가게도 놓칠 수 있었다.
MIN_SPAN = 0.0003
PAGE_SIZE = 15
MAX_RESULTS = 45
# 하루 무료 한도(10만 번)보다 넉넉히 아래에서 멈춘다. 서울을 한 번 도는 데 2만 번 안팎이다.
MAX_CALLS = int(os.environ.get("KAKAO_MAX_CALLS", "60000"))
NEW_DAYS = 30            # 화면에 보여 줄 '새 가게' 기간
GRACE_DAYS = 14          # 하루 안 보였다고 바로 잊지 않는다. 다시 보여도 새 가게가 아니다.
MIN_COVERAGE = 0.9       # 아는 가게의 90%도 못 봤으면 카카오 쪽 문제로 보고 그날은 버린다

calls = 0


class Stop(Exception):
    """이번 회차를 더 이어 갈 수 없을 때(한도·인증 문제)."""


def query(group, rect, page, near=None):
    """칸 하나의 한 쪽을 받는다. 일시적 실패는 쉬었다 다시 묻는다.
    near=(x, y, 반경m)를 주면 사각형 대신 그 점에서 가까운 순으로 받는다."""
    global calls
    if calls >= MAX_CALLS:
        raise Stop(f"이번 회차 호출 상한({MAX_CALLS:,}번)에 닿았습니다.")
    where = ({"x": f"{near[0]:.6f}", "y": f"{near[1]:.6f}", "radius": near[2], "sort": "distance"}
             if near else {"rect": ",".join(f"{v:.6f}" for v in rect)})
    params = urllib.parse.urlencode({
        "category_group_code": group,
        **where,
        "page": page,
        "size": PAGE_SIZE,
    })
    request = urllib.request.Request(
        f"{URL}?{params}", headers={"Authorization": f"KakaoAK {KEY}"})
    last_error = None
    for attempt in range(1, 6):
        calls += 1
        try:
            with urllib.request.urlopen(request, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise Stop(f"카카오가 키를 받지 않았습니다(HTTP {exc.code}). "
                           "카카오맵 사용 설정이 ON인지, 키가 맞는지 확인하세요.")
            last_error = exc
            # 429는 초당 제한일 수도 있으니 몇 번 쉬어 본다. 끝내 안 되면 하루 한도다.
            time.sleep(5 * attempt if exc.code == 429 else attempt)
        except Exception as exc:
            last_error = exc
            time.sleep(attempt)
    if isinstance(last_error, urllib.error.HTTPError) and last_error.code == 429:
        raise Stop("카카오가 429(한도 초과)를 계속 돌려줍니다.")
    raise Stop(f"{group} 칸 {rect} {page}쪽을 끝내 못 받았습니다: {last_error}")


def all_pages(group, rect, first, near=None):
    """첫 쪽을 받아 둔 질문의 나머지 쪽(최대 45곳까지)을 마저 받는다."""
    total = int((first.get("meta") or {}).get("total_count") or 0)
    docs = list(first.get("documents") or [])
    pages = (min(total, MAX_RESULTS) + PAGE_SIZE - 1) // PAGE_SIZE
    page, data = 1, first
    while page < pages and not (data.get("meta") or {}).get("is_end"):
        page += 1
        data = query(group, rect, page, near)
        docs.extend(data.get("documents") or [])
    return docs


def sweep_dense(group, rect):
    """25m 칸에도 45곳이 넘는 곳(건물 안 식당가 등). 사각형으로는 45곳까지만 주므로
    가운데와 네 귀퉁이에서 '가까운 순'으로 45곳씩 더 물어 겹치지 않는 곳을 모은다."""
    x1, y1, x2, y2 = rect
    # 경도 1도 ≈ 88km, 위도 1도 ≈ 111km(서울 위도). 귀퉁이에서 칸 전체가 들어오게 대각선만큼.
    diag = (((x2 - x1) * 88_000) ** 2 + ((y2 - y1) * 111_000) ** 2) ** 0.5
    radius = max(30, int(diag) + 5)
    docs = []
    for x, y in (((x1 + x2) / 2, (y1 + y2) / 2), (x1, y1), (x2, y1), (x1, y2), (x2, y2)):
        near = (x, y, radius)
        docs.extend(all_pages(group, None, query(group, None, 1, near), near))
    return docs


def inside(doc, rect):
    try:
        x, y = float(doc.get("x")), float(doc.get("y"))
    except (TypeError, ValueError):
        return False
    return rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]


def crawl_cell(group, rect, found, stats):
    """칸 하나를 훑는다. 45곳이 넘으면 네 칸으로 쪼개 다시 훑는다."""
    data = query(group, rect, 1)
    meta = data.get("meta") or {}
    total = int(meta.get("total_count") or 0)
    x1, y1, x2, y2 = rect
    if total > MAX_RESULTS and (x2 - x1) > MIN_SPAN:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        for sub in ((x1, y1, mx, my), (mx, y1, x2, my),
                    (x1, my, mx, y2), (mx, my, x2, y2)):
            crawl_cell(group, sub, found, stats)
        return

    docs = all_pages(group, rect, data)
    if total > MAX_RESULTS:
        stats["capped"] += 1
        docs.extend(sweep_dense(group, rect))
        # 그래도 못 본 곳이 몇 곳인지 남긴다. 0이면 빽빽한 곳까지 다 본 것이다.
        here = {str(d.get("id")) for d in docs if inside(d, rect)}
        short = max(0, total - len(here))
        stats["short"] += short
        if short:
            stats["shortCells"].append({"group": GROUPS.get(group, group),
                                        "x": round((x1 + x2) / 2, 5), "y": round((y1 + y2) / 2, 5),
                                        "total": total, "seen": len(here)})
    stats["cells"] += 1

    for doc in docs:
        address = doc.get("address_name") or ""
        if not address.startswith("서울"):
            continue
        found[str(doc.get("id"))] = {
            "id": str(doc.get("id")),
            "name": doc.get("place_name") or "",
            "group": GROUPS.get(group, group),
            "category": doc.get("category_name") or "",
            "address": address,
            "road": doc.get("road_address_name") or "",
            "phone": doc.get("phone") or "",
            "x": doc.get("x"),
            "y": doc.get("y"),
            "url": doc.get("place_url") or "",
        }


def crawl():
    """서울 전체를 훑는다. 다 못 돌았으면 None을 돌려준다."""
    found = {}
    stats = {"cells": 0, "capped": 0, "short": 0, "shortCells": []}
    left, bottom, right, top = SEOUL
    dx = (right - left) / START_SPLIT
    dy = (top - bottom) / START_SPLIT
    try:
        for group in GROUPS:
            for i in range(START_SPLIT):
                for j in range(START_SPLIT):
                    rect = (left + dx * i, bottom + dy * j,
                            left + dx * (i + 1), bottom + dy * (j + 1))
                    crawl_cell(group, rect, found, stats)
            print(f"  {GROUPS[group]}까지 훑음 — 지금까지 {len(found):,}곳, 호출 {calls:,}번")
    except Stop as exc:
        print(f"  중단: {exc}", file=sys.stderr)
        return None, stats
    return found, stats


def load_seen():
    if not SEEN.exists():
        return {"first": {}, "missing": {}}
    try:
        body = json.loads(SEEN.read_text(encoding="utf-8"))
        # minSpan이 없던 때는 100m 칸(0.0012)으로 돌았다.
        return {"first": body.get("first") or {}, "missing": body.get("missing") or {},
                "minSpan": body.get("minSpan", 0.0012)}
    except Exception as exc:
        print(f"kakao-seen.json을 읽지 못했습니다: {exc}", file=sys.stderr)
        return {"first": {}, "missing": {}}


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")


def main():
    if not KEY:
        print("KAKAO_REST_KEY가 없습니다 — 카카오맵 수집을 건너뜁니다.")
        return 0

    today = date.today().isoformat()
    seen = load_seen()
    first_of = {pid: day for day, ids in seen["first"].items() for pid in ids}
    known_now = len(first_of) - len(seen["missing"])

    print("카카오맵에서 서울 카페·음식점을 훑습니다.")
    found, stats = crawl()
    print(f"  칸 {stats['cells']:,}개, 호출 {calls:,}번, 25m 칸에도 45곳 넘은 곳 {stats['capped']}개, "
          f"그래도 못 본 곳 {stats['short']}곳")

    # 다 못 돌았거나 평소보다 확 적으면 그날은 버린다. 반쯤 돈 날을 기준으로 삼으면
    # 다음 날 멀쩡한 가게가 무더기로 '새 가게'로 보인다.
    if found is None:
        print("다 못 돌아 이번 결과는 남기지 않습니다.", file=sys.stderr)
        return 0
    if known_now and len(found) < known_now * MIN_COVERAGE:
        print(f"아는 가게 {known_now:,}곳 중 {len(found):,}곳만 보여 이번 결과는 남기지 않습니다.",
              file=sys.stderr)
        return 0

    baseline = not first_of
    new_ids = [pid for pid in found if pid not in first_of]
    # 칸을 더 잘게 나눈 첫날에는, 원래 있었는데 빽빽해서 못 보던 가게가 한꺼번에 보인다.
    # 이것들을 '새 가게'로 띄우면 안 되므로 그날 처음 본 것은 기준일 것으로 친다.
    regrid = bool(first_of) and seen.get("minSpan") != MIN_SPAN
    first_day = min(first_of.values()) if first_of else today
    for pid in new_ids:
        first_of[pid] = first_day if regrid else today
    if regrid:
        print(f"칸 크기가 바뀐 첫날이라 처음 본 {len(new_ids):,}곳은 새 가게가 아닌 기준으로 넣습니다.")

    # 안 보이는 가게는 바로 잊지 않고, GRACE_DAYS 넘게 안 보이면 그때 지운다.
    missing = dict(seen["missing"])
    for pid in first_of:
        if pid in found:
            missing.pop(pid, None)
        elif pid not in missing:
            missing[pid] = today
    cutoff = (date.fromisoformat(today) - timedelta(days=GRACE_DAYS)).isoformat()
    gone = [pid for pid, since in missing.items() if since < cutoff]
    for pid in gone:
        first_of.pop(pid, None)
        missing.pop(pid, None)

    groups = {}
    for pid, day in first_of.items():
        groups.setdefault(day, []).append(pid)
    for ids in groups.values():
        ids.sort()

    DATA.mkdir(exist_ok=True)
    write_json(SEEN, {
        "updated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "note": "카카오맵 장소 ID를 처음 본 날별로 묶었다. 맨 처음 날은 기준일이라 새 가게가 아니다.",
        "baseline": min(groups) if groups else today,
        "first": dict(sorted(groups.items())),
        "missing": dict(sorted(missing.items())),
        "minSpan": MIN_SPAN,
        # 실행 기록은 깃허브 로그인이 있어야 보이므로, 얼마나 빠짐없이 봤는지 여기에도 남긴다.
        "lastRun": {"date": today, "places": len(found), "calls": calls,
                    "cells": stats["cells"], "denseCells": stats["capped"],
                    "missedMaybe": stats["short"], "missedCells": stats["shortCells"][:50]},
    })

    base_day = min(groups) if groups else today
    since = (date.fromisoformat(today) - timedelta(days=NEW_DAYS)).isoformat()
    fresh = [dict(found[pid], firstSeen=first_of[pid]) for pid in found
             if first_of[pid] != base_day and first_of[pid] >= since]
    fresh.sort(key=lambda p: (p["firstSeen"], p["name"]), reverse=True)
    write_json(NEW, {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "baseline": base_day,
        "note": "카카오맵에 처음 보인 날 기준. 신고 업종과 상관없이 지도에 새로 올라온 서울 카페·음식점이다.",
        "places": fresh,
    })

    if baseline:
        print(f"첫날이라 {len(found):,}곳을 기준으로 남깁니다. 내일부터 새 가게가 나옵니다.")
    else:
        print(f"오늘 처음 본 가게 {len(new_ids):,}곳, 최근 {NEW_DAYS}일 새 가게 {len(fresh):,}곳, "
              f"{GRACE_DAYS}일 넘게 안 보여 지운 곳 {len(gone):,}곳")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
