"""서울 열린데이터광장에서 신규·변경된 음식점 인허가 건을 수집한다.

데이터 소스 (2026-08-07 실제 호출로 검증됨):
  LOCALDATA_072405 = 휴게음식점 (서울 전역 약 14.7만건)
  LOCALDATA_072404 = 일반음식점 (서울 전역 약 53.6만건)

두 갈래로 나눠 담는다.
  신규 오픈 : 최근 WINDOW_DAYS 안에 새로 인허가가 난 곳
  간판 교체 : 인허가는 그 전이지만 최근 WINDOW_DAYS 안에 기록이 수정된 곳
              (기존 허가를 넘겨받아 상호만 바뀌는 경우가 여기 들어온다)

인증키 없이 돌려보려면 SEOUL_API_KEY=sample — 단, 요청당 5건까지만 응답한다.
"""

import json
import os
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naver  # noqa: E402  (같은 폴더의 공통 모듈)

API_KEY = os.environ.get("SEOUL_API_KEY", "sample")
BASE = "http://openapi.seoul.go.kr:8088"
PAGE = 5 if API_KEY == "sample" else 1000

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# 최근 며칠치를 보여줄 것인지. 스캔량은 이 값과 무관하므로 늘려도 느려지지 않는다.
WINDOW_DAYS = int(os.environ.get("WINDOW_DAYS", "90"))

# 어느 자치구를 볼 것인지. 비우면 서울 전역.
DISTRICTS = [d.strip() for d in os.environ.get("DISTRICTS", "").split(",") if d.strip()]

SERVICES = {
    "휴게음식점": "LOCALDATA_072405",
    "일반음식점": "LOCALDATA_072404",
}

# 기본값은 '전 업종 수집'이다. 업태를 좁히고 싶으면 환경변수로 지정한다.
#   예) UPTAE="커피숍,다방,까페"  → 카페류만
# 실제 업태값 목록은 docs/data-source-findings.md 참고 (전량 스캔으로 확인함).
UPTAE_FILTER = {u.strip() for u in os.environ.get("UPTAE", "").split(",") if u.strip()}

# 목록에서 빼고 싶은 체인. EXCLUDE 환경변수로 통째로 갈아끼울 수 있다.
DEFAULT_EXCLUDE = [
    "씨유", "CU ", "지에스25", "GS25", "세븐일레븐", "이마트24", "미니스톱",
    "스타벅스", "투썸플레이스", "이디야", "메가엠지씨", "메가커피", "컴포즈커피",
    "빽다방", "더벤티", "커피빈", "탐앤탐스", "할리스", "파스쿠찌", "엔제리너스",
    "파리바게뜨", "뚜레쥬르", "던킨", "배스킨라빈스",
    "롯데리아", "맥도날드", "버거킹", "KFC", "맘스터치", "써브웨이",
]
_exclude_env = os.environ.get("EXCLUDE")
EXCLUDE = [
    e.strip()
    for e in (_exclude_env.split(",") if _exclude_env is not None else DEFAULT_EXCLUDE)
    if e.strip()
]

TRDSTATE_OPEN = "01"  # 영업/정상 (03 = 폐업)

# 한 페이지가 끝내 실패해도 이만큼까지는 넘어간다. 700번 가까운 요청 중
# 한두 번의 일시적 실패로 30분짜리 작업을 통째로 버리지 않기 위한 여유다.
MAX_SKIPPED_PAGES = int(os.environ.get("MAX_SKIPPED_PAGES", "5"))


def fetch_once(service, start, end):
    url = f"{BASE}/{API_KEY}/json/{service}/{start}/{end}/"
    with urllib.request.urlopen(url, timeout=60) as resp:
        body = resp.read().decode("utf-8")
    if body.lstrip().startswith("<"):
        raise RuntimeError(f"API가 오류를 반환했습니다: {body[:300]}")
    payload = json.loads(body)[service]
    code = payload["RESULT"]["CODE"]
    if code != "INFO-000":
        raise RuntimeError(f"{code}: {payload['RESULT']['MESSAGE']}")
    return payload["list_total_count"], payload.get("row", [])


def fetch(service, start, end, attempts=6):
    """전량 스캔은 요청이 700회에 가까워 한 번쯤은 실패한다.

    지수 백오프로 재시도하되, 마지막에도 실패하면 예외를 그대로 올린다.
    호출하는 쪽에서 건너뛸지 중단할지 결정한다.
    """
    delay = 3
    for attempt in range(1, attempts + 1):
        try:
            return fetch_once(service, start, end)
        except Exception as exc:
            if attempt == attempts:
                raise
            print(
                f"    재시도 {attempt}/{attempts - 1} ({start}~{end}): {exc}",
                file=sys.stderr,
            )
            time.sleep(delay)
            delay = min(delay * 2, 60)


def fetch_all(service):
    """전체 행을 페이지 단위로 흘려보낸다.

    일반음식점은 53만 행이라 한꺼번에 메모리에 올리지 않는다.
    """
    total, rows = fetch(service, 1, PAGE)
    print(f"  {service}: 전체 {total:,}건", file=sys.stderr)
    yield from rows
    if API_KEY == "sample":
        print("  (샘플키 — 5건만 수집합니다)", file=sys.stderr)
        return

    skipped = 0
    start = PAGE + 1
    while start <= total:
        end = min(start + PAGE - 1, total)
        try:
            _, page = fetch(service, start, end)
        except Exception as exc:
            skipped += 1
            print(f"    !! {start}~{end} 건너뜀 ({skipped}/{MAX_SKIPPED_PAGES}): {exc}",
                  file=sys.stderr)
            if skipped > MAX_SKIPPED_PAGES:
                raise RuntimeError(
                    f"건너뛴 페이지가 {MAX_SKIPPED_PAGES}개를 넘었습니다. "
                    "일시적 장애가 아닐 수 있으니 중단합니다."
                ) from exc
            start = end + 1
            continue
        if not page:
            break
        yield from page
        start = end + 1
        if start % 50000 < PAGE:
            print(f"    ... {start:,}/{total:,}", file=sys.stderr)
        time.sleep(0.05)

    if skipped:
        print(f"  {service}: {skipped}개 페이지를 건너뛰었습니다.", file=sys.stderr)


def clean(value):
    return (value or "").strip()


def parse_date(value):
    value = clean(value)
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            continue
    return None


def district_of(row):
    """도로명주소 우선, 없으면 지번주소에서 자치구를 뽑는다."""
    for field in ("RDNWHLADDR", "SITEWHLADDR"):
        parts = clean(row.get(field)).split()
        for part in parts:
            if part.endswith("구"):
                return part
    return ""


def is_excluded(name):
    """체인 지점인지 판단한다.

    단순 포함 검사는 쓰지 않는다. '씨유'를 넣었다고 '메이 씨유' 같은
    개인 가게까지 걸러지면 안 되기 때문이다. 체인 지점은 거의 예외 없이
    브랜드명으로 시작하므로 앞부분만 본다. 뒤에 붙는 형태는 '…점'으로
    끝나는 경우만 함께 처리한다.
    """
    for keyword in EXCLUDE:
        if name.startswith(keyword):
            return True
        if name.endswith("점") and keyword in name:
            return True
    return False


def normalize(row, category):
    return {
        "id": clean(row.get("MGTNO")),
        "name": clean(row.get("BPLCNM")),
        "address": clean(row.get("RDNWHLADDR")) or clean(row.get("SITEWHLADDR")),
        "district": district_of(row),
        "licenseDate": clean(row.get("APVPERMYMD"))[:10],
        "modifiedDate": clean(row.get("LASTMODTS"))[:10],
        "category": category,
        "bizType": clean(row.get("UPTAENM")),
        "phone": clean(row.get("SITETEL")),
        "area": clean(row.get("SITEAREA")),
    }


def audit():
    """UPTAENM(업태구분명)에 실제로 어떤 값이 오는지 세어본다."""
    from collections import Counter

    for category, service in SERVICES.items():
        counter = Counter()
        newest = None
        for row in fetch_all(service):
            if clean(row.get("TRDSTATEGBN")) == TRDSTATE_OPEN:
                counter[clean(row.get("UPTAENM"))] += 1
            approved = parse_date(row.get("APVPERMYMD"))
            if approved and (newest is None or approved > newest):
                newest = approved

        print(f"\n[{category}] {service}")

        # 이 데이터가 아직 갱신되고 있는지 확인한다. 최신 인허가일자가
        # 몇 달 전에서 멈춰 있다면 소스가 죽은 것이므로 파이프라인을 갈아타야 한다.
        if newest:
            age = (date.today() - newest).days
            flag = "정상" if age <= 14 else "⚠️ 갱신이 멈춘 것으로 보임"
            print(f"  최신 인허가일자: {newest} ({age}일 전) — {flag}")

        print("  영업중 업태별 건수:")
        for name, count in counter.most_common():
            mark = "←" if (not UPTAE_FILTER or name in UPTAE_FILTER) else " "
            print(f"  {mark} {name or '(빈값)'}: {count:,}")


def load_seen(path):
    """관리번호 → 지난 회차의 기록.

    예전에는 처음 등장한 날짜만 문자열로 담았다. 그 형식도 읽어준다.
    """
    if not path.exists():
        return {}
    stored = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(stored, dict):
        return {}
    return {
        key: (value if isinstance(value, dict) else {"first": value})
        for key, value in stored.items()
    }


# 무엇이 바뀌었는지 알려주는 필드는 원본에 없다. UPDATEGBN이 신규/수정만
# 구분할 뿐이다. 그래서 지난 회차 값과 직접 견주어 알아낸다.
#
# 전화번호는 행정상의 정정인 경우가 대부분이라 보지 않는다.
# 가게가 바뀌었는지를 말해 주는 것은 상호와 주소다.
TRACKED = {
    "name": "상호",
    "address": "주소",
    "bizType": "업종",
    "area": "면적",
}


def stamp_history(items, seen, today):
    """처음 등장한 날짜, 마지막으로 달라진 날짜, 바뀐 항목을 표시한다.

    상호가 바뀌었다는 것은 대개 그 자리에 다른 가게가 들어왔다는 뜻이라
    가장 눈여겨볼 신호다.

    NEW 표시는 firstSeen이 아니라 updatedSeen으로 판단한다. 목록은 원본이
    바뀐 날짜순으로 늘어놓는데, 이미 목록에 있던 건이 다시 수정되면 위로
    올라오면서도 firstSeen은 예전 그대로다. 그러면 위쪽에 NEW 아닌 것이
    섞여 순서와 어긋나 보인다.
    """
    for item in items:
        before = seen.get(item["id"])
        fallback = item["modifiedDate"] or item["licenseDate"]
        item["firstSeen"] = (before or {}).get("first") or (today if seen else fallback)

        changes = []
        if before:
            for field, label in TRACKED.items():
                old = before.get(field)
                if old is not None and old != item.get(field):
                    changes.append({"field": field, "label": label, "before": old})
        if changes:
            item["changes"] = changes

        prev_mod = (before or {}).get("modifiedDate")
        if before is None:
            item["updatedSeen"] = item["firstSeen"]
        elif prev_mod is None:
            # 이 값을 남기기 전부터 목록에 있던 건. 견줄 대상이 없으므로
            # 원본 수정일을 그대로 쓴다. 목록을 그 날짜순으로 늘어놓으므로
            # 이렇게 해야 첫 회차부터 순서와 어긋나지 않는다.
            # 여기서 today를 넣으면 다음 방문 때 전부 NEW가 되어버린다.
            item["updatedSeen"] = item.get("modifiedDate") or item["firstSeen"]
        elif changes or prev_mod != item.get("modifiedDate"):
            item["updatedSeen"] = today
        else:
            item["updatedSeen"] = before.get("updated") or item["firstSeen"]


def attach_naver_links(items, seen, budget):
    """네이버 지역 검색에서 그 가게의 공식 링크를 찾아 붙인다.

    인스타 아이디를 철자로 추측하던 것을 대신한다. 네이버 플레이스에 등록된
    가게는 대개 인스타 주소를 link로 달아 두기 때문이다.

    한 번에 다 부르면 오래 걸리므로 아직 안 찾아본 건만 budget만큼 본다.
    한 번 찾은 결과는 seen에 남겨 다음 회차에 다시 부르지 않는다.
    """
    if not naver.enabled():
        return 0

    looked = 0
    for item in items:
        cached = (seen.get(item["id"]) or {}).get("naver")
        if cached is not None:
            # 빈 dict는 '찾아봤지만 없었다'는 뜻이다. 다시 부르지 않는다.
            if cached:
                item["naver"] = cached
            continue
        if looked >= budget:
            continue
        looked += 1
        found = naver.find_place(item["name"], item["address"])
        item["naver"] = found or {}
        time.sleep(0.05)
    return looked


def dedupe(items):
    """관리번호가 같은 건은 한 번만 남긴다."""
    seen_ids = set()
    out = []
    for item in items:
        if item["id"] in seen_ids:
            continue
        seen_ids.add(item["id"])
        out.append(item)
    return out


def snapshot(items):
    """다음 회차에 견주어 볼 수 있도록 이번 값을 남긴다."""
    return {
        p["id"]: {
            "first": p["firstSeen"],
            "updated": p["updatedSeen"],
            "modifiedDate": p.get("modifiedDate"),
            # 찾아본 결과를 남긴다. 빈 dict는 '없었다'는 뜻이라 다시 안 부른다.
            **({"naver": p["naver"]} if "naver" in p else {}),
            **{f: p.get(f) for f in TRACKED},
        }
        for p in items
    }


def write_json(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main():
    if os.environ.get("AUDIT") == "1":
        audit()
        return

    today = date.today()
    cutoff = today - timedelta(days=WINDOW_DAYS)
    opened, changed = [], []
    excluded = 0

    for category, service in SERVICES.items():
        print(f"수집 중: {category}", file=sys.stderr)
        for row in fetch_all(service):
            if clean(row.get("TRDSTATEGBN")) != TRDSTATE_OPEN:
                continue
            if UPTAE_FILTER and clean(row.get("UPTAENM")) not in UPTAE_FILTER:
                continue

            approved = parse_date(row.get("APVPERMYMD"))
            if approved is None:
                continue
            modified = parse_date(row.get("LASTMODTS"))

            if approved >= cutoff:
                bucket = opened
            elif modified is not None and modified >= cutoff:
                bucket = changed
            else:
                continue

            item = normalize(row, category)
            if DISTRICTS and item["district"] not in DISTRICTS:
                continue
            if is_excluded(item["name"]):
                excluded += 1
                continue
            bucket.append(item)

    # 원본이 같은 관리번호를 두 번 주는 경우가 있다(푸드트럭에서 특히 잦다).
    # 관리번호가 고유키이므로 그것으로 한 번만 남긴다.
    opened = dedupe(opened)
    changed = dedupe(changed)

    opened.sort(key=lambda p: (p["licenseDate"], p["name"]), reverse=True)
    changed.sort(key=lambda p: (p["modifiedDate"], p["name"]), reverse=True)

    DATA_DIR.mkdir(exist_ok=True)
    seen_opened = load_seen(DATA_DIR / "seen.json")
    seen_changed = load_seen(DATA_DIR / "seen-changed.json")
    stamp_history(opened, seen_opened, today.isoformat())
    stamp_history(changed, seen_changed, today.isoformat())

    # 네이버 지역 검색으로 공식 링크를 채운다. 목록이 최신순이라 앞쪽부터
    # 채워지고, 나머지는 다음 회차에 이어서 본다.
    budget = int(os.environ.get("NAVER_LOOKUP_BUDGET", "300"))
    looked = attach_naver_links(opened, seen_opened, budget)
    looked += attach_naver_links(changed, seen_changed, max(0, budget - looked))
    if naver.enabled():
        found = sum(1 for p in opened + changed if p.get("naver"))
        print(f"네이버 지역 조회 {looked}건 / 링크 확보 누적 {found}곳", file=sys.stderr)

    meta = {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "period": {"from": cutoff.isoformat(), "to": today.isoformat()},
        "source": "sample" if API_KEY == "sample" else "seoul-opendata",
    }

    # '간판 교체' 목록은 탭을 눌렀을 때만 받아가도록 파일을 나눈다.
    # 탭에 붙일 뱃지 숫자는 날짜별 집계만 있으면 목록 없이도 셀 수 있다.
    # 화면의 NEW 판정과 같은 기준(마지막으로 달라진 날)을 써야 숫자가 맞는다.
    first_seen_counts = {}
    for item in changed:
        day = item["updatedSeen"]
        first_seen_counts[day] = first_seen_counts.get(day, 0) + 1

    write_json(DATA_DIR / "latest.json", {
        **meta,
        "places": opened,
        "changedCount": len(changed),
        "changedFirstSeen": first_seen_counts,
    })
    write_json(DATA_DIR / "changed.json", {**meta, "places": changed})

    # 조회 기간에서 빠진 건은 다시 나타날 일이 없으므로 기억할 필요도 없다.
    write_json(DATA_DIR / "seen.json", snapshot(opened))
    write_json(DATA_DIR / "seen-changed.json", snapshot(changed))

    print(f"\n최근 {WINDOW_DAYS}일")
    print(f"  신규 오픈: {len(opened):,}곳")
    print(f"  간판 교체: {len(changed):,}곳")
    print(f"  체인 제외: {excluded:,}곳")


if __name__ == "__main__":
    main()
