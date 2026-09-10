"""글쓰기 화면에서 이름만 치면 주소가 채워지도록 목록을 만든다.

브라우저는 네이버를 직접 부를 수 없다(CORS). 그런데 우리는 이미 서울시
인허가 자료로 신상 가게 목록을 갖고 있다. 신상 가게를 쓰는 블로그이므로
대개 그 안에 있다. 그러니 밖에 물어볼 것 없이 우리 것으로 채우면 된다.

파일이 커지면 화면이 느려지므로 최대한 줄인다.
  - 칸 이름을 반복하지 않고 값만 늘어놓는다: [이름, 주소, 업종]
  - 주소에서 '서울특별시 '는 뗀다. 어차피 전부 서울이다.
  - 자치구와 구분은 주소에서 뽑을 수 있으므로 담지 않는다.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SOURCES = ["latest.json", "changed.json"]


def load(name):
    path = DATA / name
    if not path.exists():
        return []
    try:
        return (json.loads(path.read_text(encoding="utf-8")) or {}).get("places") or []
    except Exception as exc:
        print(f"{name}을 읽지 못했습니다: {exc}", file=sys.stderr)
        return []


def main():
    rows = []
    seen = set()
    for source in SOURCES:
        for place in load(source):
            name = (place.get("name") or "").strip()
            address = (place.get("address") or "").strip()
            if not name or not address:
                continue
            key = (name, address)
            if key in seen:
                continue
            seen.add(key)
            # 좌표는 소수점 다섯 자리면 1m 남짓이라 그 아래는 버린다.
            # 한 줄에 열 글자쯤 늘어나는 대신 가장 가까운 역을 이름이 아니라
            # 거리로 고를 수 있다.
            lat, lon = place.get("lat"), place.get("lon")
            row = [
                name,
                address.replace("서울특별시 ", "").replace("서울시 ", ""),
                place.get("bizType") or "",
            ]
            if lat and lon:
                row += [round(lat, 5), round(lon, 5)]
            rows.append(row)

    if not rows:
        print("담을 가게가 없습니다. 목록을 만들지 않습니다.", file=sys.stderr)
        return

    rows.sort(key=lambda r: r[0])
    DATA.mkdir(exist_ok=True)
    out = DATA / "shops.json"
    out.write_text(
        json.dumps({
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            # 좌표가 없는 가게도 있어 줄 길이가 셋일 수도 다섯일 수도 있다.
            "fields": ["name", "address", "bizType", "lat", "lon"],
            "rows": rows,
        }, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    size = out.stat().st_size / 1024
    withxy = sum(1 for r in rows if len(r) >= 5)
    print(f"가게 {len(rows)}곳을 담았습니다 ({size:,.0f} KB) · 좌표 있는 곳 {withxy}곳")


if __name__ == "__main__":
    main()
