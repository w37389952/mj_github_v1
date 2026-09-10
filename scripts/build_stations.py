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
import re
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

# 이름이 실제 역이어야 한다. 좌표는 네이버가 주지만 이름이 틀리면 못 찾는다.
# (처음에 '가로수길역'을 적었는데 그런 역은 없다. 신사역이다.)
#
# 앞쪽은 write.html의 AREA_MAP에 적힌 역들, 뒤쪽은 그 밖에서 자주 걸리는 역들이다.
# 좌표로 고르려면 가까운 역이 이 목록 안에 있어야 하므로 넉넉히 둔다.
# 목록에 없어 못 찾은 역은 로그에 '못 찾음'으로 남을 뿐 해를 끼치지 않는다.
STATIONS = [
    # AREA_MAP에 적힌 역
    "숙대입구역", "남영역", "녹사평역", "이태원역", "한강진역", "삼각지역",
    "홍대입구역", "상수역", "합정역", "망원역", "마포구청역", "공덕역",
    "종로3가역", "안국역", "경복궁역", "충무로역", "명동역", "신촌역", "이대역",
    "신사역", "압구정로데오역", "청담역", "논현역", "역삼역", "삼성역",
    "한성대입구역", "문래역", "영등포역", "당산역", "여의도역", "잠실역",
    "방이역", "성수역", "뚝섬역", "구산역", "응암역", "불광역", "연신내역",
    "가산디지털단지역", "독산역", "효창공원앞역", "서울대입구역", "신림역",
    "화곡역", "등촌역", "제기동역", "애오개역", "신당역",
    # 그 밖에 서울에서 자주 걸리는 역
    "서울역", "시청역", "을지로입구역", "을지로3가역", "동대문역사문화공원역",
    "회현역", "동대문역", "혜화역", "동묘앞역", "신용산역", "용산역", "마포역",
    "대흥역", "광흥창역", "상수역", "망원역", "디지털미디어시티역", "홍제역",
    "무악재역", "독립문역", "안암역", "보문역", "성신여대입구역", "길음역",
    "왕십리역", "건대입구역", "서울숲역", "약수역", "동대입구역",
    "강남역", "선릉역", "학동역", "노량진역", "상도역", "봉천역", "낙성대역",
    "사당역", "이수역", "서초역", "교대역", "송파나루역", "석촌역",
    "천호역", "군자역", "장한평역", "노원역", "수유역", "미아사거리역",
]
# 같은 역을 두 번 적었더라도 한 번만 부른다.
STATIONS = list(dict.fromkeys(STATIONS))


def load_out():
    if not OUT.exists():
        return {"stations": {}, "areas": {}}
    try:
        got = json.loads(OUT.read_text(encoding="utf-8")) or {}
        return {"stations": got.get("stations") or {}, "areas": got.get("areas") or {}}
    except Exception:
        return {"stations": {}, "areas": {}}


# '합정동', '문래동2가', '한강로3가', '종로1가' 같은 법정동만 받는다.
# 층수나 건물명이 섞이지 않게 꼴을 못 박는다.
DONG = re.compile(r"[가-힣]{2,5}동\d*가?|[가-힣]{2,5}\d*(?:가|리)")


def dongs_in(address):
    """주소에서 법정동 이름을 뽑는다.

    도로명주소는 '마포구 토정로 39, 1층 (합정동)'처럼 괄호에 들어 있다.
    그런데 도로명이 없어 지번주소가 대신 오는 건도 있다 —
    '서울특별시 금천구 시흥동 992-47'. 그때는 괄호가 없으므로 본문에서 찾는다.
    괄호만 보다가 그런 건을 통째로 놓치고 있었다.
    """
    if not address:
        return []
    paren = re.search(r"\(([^)]+)\)\s*$", address)
    if paren:
        out = [p.strip() for p in paren.group(1).split(",")]
        out = [d for d in out if DONG.fullmatch(d)]
        if out:
            return out
    # 괄호가 없거나 쓸 만한 것이 없으면 주소를 훑는다. 구 이름은 빼야 한다.
    found = []
    for word in address.replace(",", " ").split():
        if word.endswith("구") or word.endswith("시"):
            continue
        if DONG.fullmatch(word):
            found.append(word)
    return found[:1]


def area_centres():
    """가게 좌표를 동네별로 평균 내어 그 동네의 자리를 구한다.

    서울 법정동은 470곳쯤인데 write.html의 이름 표에는 60곳뿐이다. 그래서
    쌍림동·도화동·저동2가처럼 표에 없는 동네는 역도 인접 지역도 빈칸이었다.
    여기서 구한 자리가 있으면 표에 없어도 거리로 고를 수 있다.
    """
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
            for dong in dongs_in(place.get("address") or ""):
                buckets.setdefault(dong, []).append((lat, lon))

    out = {}
    for dong, spots in buckets.items():
        # 두 곳만 있어도 그 동네가 어디쯤인지는 잡힌다. 다섯을 넘기게 하면
        # 가게가 적은 동네가 통째로 빠져 '표에 없는 동네'가 그대로 남는다.
        if len(spots) < 2:
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
