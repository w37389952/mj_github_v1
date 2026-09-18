"""가게 하나가 서울시 인허가 자료에 있는지 이름이나 주소로 찾는다.

'분명 새로 생긴 집인데 왜 레이더에 안 떴나'를 가릴 때 쓴다. 답은 셋 중 하나다.

  1. 자료에 아예 없다      → 아직 식품접객업 인허가가 안 났거나, 우리가 안 보는
                            영업 종류다. 사업자등록(세무)은 인허가보다 먼저 나므로
                            사업자번호 조회 사이트에는 우리보다 몇 달 먼저 뜬다.
  2. 있는데 인허가일이 오래됐다 → 기존 허가를 넘겨받았다. '신규 오픈'이 아니라
                            '간판 교체'로 들어간다.
  3. 있는데 날짜가 창 밖이다   → WINDOW_DAYS를 늘리면 보인다.

쓰는 법 (깃허브 Actions에서 돌린다 — 키가 거기 있다):
    QUERY="어니언" python scripts/find_shop.py
    QUERY="명동10길 35" python scripts/find_shop.py

이름과 주소 둘 다에서 찾는다. 띄어쓰기는 무시한다.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect  # noqa: E402  (수집기의 내려받기·정리 코드를 그대로 쓴다)

QUERY = os.environ.get("QUERY", "").strip()


def squash(text):
    """띄어쓰기를 없애 견준다. '어니언 컴퍼니'와 '어니언컴퍼니'를 같게 본다."""
    return (text or "").replace(" ", "")


def main():
    if not QUERY:
        print("QUERY 환경변수에 찾을 이름이나 주소를 넣어 주세요.", file=sys.stderr)
        return 1

    needle = squash(QUERY)
    print(f"'{QUERY}'을(를) 서울시 인허가 자료에서 찾습니다.")
    print("두 종류를 다 훑습니다 — 휴게음식점, 일반음식점.\n")

    hits = []
    for category, service in collect.SERVICES.items():
        print(f"[{category}]", file=sys.stderr)
        scanned = 0
        for row in collect.fetch_all(service):
            scanned += 1
            name = collect.clean(row.get("BPLCNM"))
            addr = (collect.clean(row.get("RDNWHLADDR"))
                    or collect.clean(row.get("SITEWHLADDR")))
            if needle in squash(name) or needle in squash(addr):
                hits.append(collect.normalize(row, category))
        print(f"  {scanned:,}건을 봤습니다.", file=sys.stderr)

    if not hits:
        print("찾지 못했습니다.\n")
        print("인허가 자료에 아직 없다는 뜻입니다. 사업자등록은 인허가보다 먼저")
        print("나므로, 사업자번호 조회 사이트에 뜨는 것과 인허가가 나는 것 사이에는")
        print("몇 달이 빕니다. 그 사이에는 이 레이더로 알 수 있는 길이 없습니다.")
        return 0

    # 영업중인 것을 먼저, 그 다음 최근 허가 순으로.
    hits.sort(key=lambda p: p["licenseDate"], reverse=True)
    print(f"{len(hits)}곳을 찾았습니다.\n")
    for p in hits:
        window = collect.WINDOW_DAYS
        print(f"  {p['name']}")
        print(f"    주소      {p['address']}")
        print(f"    업태      {p['category']} · {p['bizType']}")
        print(f"    인허가일  {p['licenseDate']}")
        print(f"    수정일    {p['modifiedDate']}")
        print(f"    (신규 오픈 목록은 최근 {window}일 안에 인허가가 난 것만 담습니다.)")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
