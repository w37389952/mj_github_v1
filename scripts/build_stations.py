"""역과 동네의 좌표를 한 번 받아 두고 캐시한다.

지금까지 '가장 가까운 역'과 '인접 지역'은 동네 이름으로만 찍었다. 그래서
합정동 안에서 상수역 쪽에 있는 가게도 '망원동'으로 채워졌다. 좌표로 재면
그런 일이 없다.

두 가지를 만든다.
  역   — 네이버 지역 검색으로 위경도를 받는다. 예순 곳 남짓이라 한 번이면 되고,
         받은 값은 파일에 남겨 다음부터는 안 부른다.
  동네 — 따로 받을 필요가 없다. 우리가 가진 가게 수천 곳의 좌표를 동네별로
         평균 내면 그 동네가 어디쯤인지 나온다. 부를 일도, 틀릴 일도 없다.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naver  # noqa: E402
import geo  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "places.json"

# write.html의 AREA_MAP에 적힌 역들과 맞춰 둔다. 여기 없는 역은 좌표가 없어
# 이름으로 찍던 예전 방식으로 돌아간다.
STATIONS = [
    "숙대입구역", "남영역", "녹사평역", "이태원역", "한강진역", "삼각지역",
    "홍대입구역", "상수역", "합정역", "망원역", "마포구청역", "공덕역",
    "종로3가역", "안국역", "경복궁역", "을지로3가역", "충무로역", "명동역",
    "동대입구역", "서울역", "시청역", "광화문역", "신촌역", "이대역",
    "가로수길역", "신사역", "압구정로데오역", "청담역", "학동역", "역삼역",
    "강남역", "한성대입구역", "성신여대입구역", "혜화역", "문래역", "영등포역",
    "당산역", "여의도역", "잠실역", "송파나루역", "방이역", "성수역",
    "뚝섬역", "서울숲역", "건대입구역", "구산역", "응암역", "불광역",
    "연신내역", "가산디지털단지역", "독산역", "효창공원앞역", "서울대입구역",
    "봉천역", "신림역", "화곡역", "등촌역", "제기동역", "동묘앞역",
    "신당역", "약수역", "용산역", "노량진역", "대흥역", "광흥창역",
]


def load_out():
    if not OUT.exists():
        return {"stations": {}, "areas": {}}
    try:
        got = json.loads(OUT.read_text(encoding="utf-8")) or {}
        return {"stations": got.get("stations") or {}, "areas": got.get("areas") or {}}
    except Exception:
        return {"stations": {}, "areas": {}}


def area_centres():
    """가게 좌표를 동네별로 평균 내어 그 동네의 자리를 구한다.

    주소 끝의 '(합정동)'을 동네 이름으로 본다. 도로명주소는 그 꼴로 온다.
    가게가 다섯 곳도 안 되는 동네는 평균이 못 미더워 버린다.
    """
    import re

    buckets = {}
    for name in ("latest.json", "changed.json"):
        path = DATA / name
        if not path.exists():
            continue
        try:
            places = (json.loads(path.read_text(encoding="utf-8")) or {}).get("places") or []
        except Exception:
            continue
        for place in places:
            lat, lon = place.get("lat"), place.get("lon")
            if not lat or not lon:
                continue
            found = re.search(r"\(([^)]+)\)\s*$", place.get("address") or "")
            if not found:
                continue
            for part in found.group(1).split(","):
                dong = part.strip()
                # '합정동', '문래동2가', '한강로3가', '종로1가' 같은 법정동만 쓴다.
                # 층수나 건물명이 섞이지 않게 꼴을 못 박는다.
                if not re.fullmatch(r"[가-힣]{2,5}동\d*가?|[가-힣]{2,5}\d*(가|리)", dong):
                    continue
                buckets.setdefault(dong, []).append((lat, lon))

    out = {}
    for dong, spots in buckets.items():
        if len(spots) < 5:
            continue
        out[dong] = [
            round(sum(s[0] for s in spots) / len(spots), 6),
            round(sum(s[1] for s in spots) / len(spots), 6),
        ]
    return out


def main():
    got = load_out()
    stations = got["stations"]

    missing = [s for s in STATIONS if s not in stations]
    if missing and not naver.enabled():
        print("네이버 인증키가 없어 역 좌표를 못 받습니다. 있는 것만 씁니다.",
              file=sys.stderr)
    elif missing:
        print(f"역 {len(missing)}곳의 좌표를 받습니다 (이미 있는 {len(stations)}곳은 건너뜁니다)")
        for name in missing:
            spot, title = naver.geocode(f"{name} 지하철")
            if not spot:
                spot, title = naver.geocode(name)
            if spot:
                stations[name] = [spot[0], spot[1]]
                print(f"  {name} → {spot[0]}, {spot[1]}  ({title})")
            else:
                print(f"  {name} 못 찾음", file=sys.stderr)
            time.sleep(0.1)
    else:
        print(f"역 좌표 {len(stations)}곳이 이미 있습니다. 새로 부르지 않습니다.")

    areas = area_centres()
    print(f"동네 {len(areas)}곳의 자리를 가게 좌표로 구했습니다.")

    # 역과 동네가 서로 얼마나 떨어져 있는지 몇 개만 찍어 눈으로 확인한다.
    for dong in ("합정동", "상수동", "망원동", "서교동"):
        if dong not in areas:
            continue
        near = sorted(
            ((geo.metres_between(areas[dong], spot), name)
             for name, spot in stations.items()),
            key=lambda x: x[0],
        )[:3]
        pretty = " · ".join(f"{n} {d:,.0f}m" for d, n in near)
        print(f"  {dong} 에서 가까운 역: {pretty}")

    DATA.mkdir(exist_ok=True)
    OUT.write_text(
        json.dumps({
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "note": ("역은 네이버 지역 검색에서 한 번 받아 캐시한 값. "
                     "동네는 그 동네 가게들의 좌표를 평균 낸 값."),
            "stations": stations,
            "areas": areas,
        }, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    size = OUT.stat().st_size / 1024
    print(f"역 {len(stations)}곳 · 동네 {len(areas)}곳을 담았습니다 ({size:,.0f} KB)")


if __name__ == "__main__":
    main()
