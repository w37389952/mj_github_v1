"""서울 열린데이터광장에서 신규 음식점 인허가 건을 수집한다.

데이터 소스 (2026-08-07 실제 호출로 검증됨):
  LOCALDATA_072405 = 휴게음식점 (서울 전역 146,710건)
  LOCALDATA_072404 = 일반음식점 (서울 전역 536,045건)

인증키 없이 돌려보려면 SEOUL_API_KEY=sample — 단, 요청당 5건까지만 응답한다.
"""

import json
import os
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

API_KEY = os.environ.get("SEOUL_API_KEY", "sample")
BASE = "http://openapi.seoul.go.kr:8088"
PAGE = 5 if API_KEY == "sample" else 1000

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# 최근 며칠 내 인허가 건을 신규로 볼 것인지
WINDOW_DAYS = int(os.environ.get("WINDOW_DAYS", "7"))

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

TRDSTATE_OPEN = "01"  # 영업/정상 (03 = 폐업)


def fetch(service, start, end):
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
    start = PAGE + 1
    while start <= total:
        _, page = fetch(service, start, min(start + PAGE - 1, total))
        if not page:
            break
        yield from page
        start += PAGE
        if start % 50000 < PAGE:
            print(f"    ... {start:,}/{total:,}", file=sys.stderr)
        time.sleep(0.05)


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


def normalize(row, category):
    return {
        "id": clean(row.get("MGTNO")),
        "name": clean(row.get("BPLCNM")),
        "address": clean(row.get("RDNWHLADDR")) or clean(row.get("SITEWHLADDR")),
        "district": district_of(row),
        "licenseDate": clean(row.get("APVPERMYMD"))[:10],
        "category": category,
        "bizType": clean(row.get("UPTAENM")),
        "phone": clean(row.get("SITETEL")),
        "area": clean(row.get("SITEAREA")),
    }


def audit():
    """UPTAENM(업태구분명)에 실제로 어떤 값이 오는지 세어본다.

    CAFE_UPTAE를 확정하기 전에 AUDIT=1 로 한 번 돌려서 눈으로 확인할 것.
    """
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


def main():
    if os.environ.get("AUDIT") == "1":
        audit()
        return

    cutoff = date.today() - timedelta(days=WINDOW_DAYS)
    collected = []

    for category, service in SERVICES.items():
        print(f"수집 중: {category}", file=sys.stderr)
        for row in fetch_all(service):
            if clean(row.get("TRDSTATEGBN")) != TRDSTATE_OPEN:
                continue
            if UPTAE_FILTER and clean(row.get("UPTAENM")) not in UPTAE_FILTER:
                continue
            approved = parse_date(row.get("APVPERMYMD"))
            if approved is None or approved < cutoff:
                continue
            item = normalize(row, category)
            if DISTRICTS and item["district"] not in DISTRICTS:
                continue
            collected.append(item)

    collected.sort(key=lambda c: (c["licenseDate"], c["name"]), reverse=True)

    # 이전 회차에 없던 건에 표시를 달아 대시보드에서 'NEW'로 강조한다.
    seen_path = DATA_DIR / "seen.json"
    seen = set()
    if seen_path.exists():
        seen = set(json.loads(seen_path.read_text(encoding="utf-8")))
    first_run = not seen
    for place in collected:
        # 첫 실행에서는 전부 처음 보는 것이므로 NEW 표시가 의미가 없다.
        place["isNew"] = (not first_run) and place["id"] not in seen
    fresh_count = sum(1 for p in collected if p["isNew"])

    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "latest.json").write_text(
        json.dumps(
            {
                "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
                "period": {"from": cutoff.isoformat(), "to": date.today().isoformat()},
                "source": "sample" if API_KEY == "sample" else "seoul-opendata",
                "newCount": fresh_count,
                "places": collected,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # 조회 기간에서 빠진 건은 다시 나타날 일이 없으므로 기억할 필요도 없다.
    # 이번 회차 목록으로 통째로 갈아끼워 seen 파일이 무한히 커지는 것을 막는다.
    seen_path.write_text(
        json.dumps(sorted(p["id"] for p in collected), ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\n최근 {WINDOW_DAYS}일 신규 {len(collected)}곳 / 이번에 새로 추가 {fresh_count}곳")
    for p in collected:
        if p["isNew"]:
            print(f"  · {p['licenseDate']}  {p['name']}  ({p['district']}, {p['bizType']})")


if __name__ == "__main__":
    main()
