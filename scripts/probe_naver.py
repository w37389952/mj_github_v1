"""네이버 검색 API가 실제로 어떻게 응답하는지 확인한다.

NAVER API HUB로 옮겨가면서 주소와 인증 헤더가 모두 바뀌었다. 문서마다 설명이
갈리므로, 코드를 짜기 전에 실제 응답을 눈으로 본다. 서울시 API에서 '까페'를
'카페'로 잘못 짐작했던 일을 되풀이하지 않기 위한 절차다.

인증키는 화면에 찍지 않는다.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

KEY_ID = os.environ.get("NAVER_API_KEY_ID", "")
KEY = os.environ.get("NAVER_API_KEY", "")

QUERY = os.environ.get("PROBE_QUERY", "연남동 신상카페")

# 어느 쪽이 맞는지 몰라 둘 다 두드려 본다.
ATTEMPTS = [
    {
        "name": "API HUB (블로그)",
        "url": "https://naverapihub.apigw.ntruss.com/search/v1/blog",
        "params": {"query": QUERY, "display": 3, "sort": "date", "format": "json"},
        "headers": {"X-NCP-APIGW-API-KEY-ID": KEY_ID, "X-NCP-APIGW-API-KEY": KEY},
    },
    {
        "name": "API HUB (지역)",
        "url": "https://naverapihub.apigw.ntruss.com/search/v1/local",
        "params": {"query": "연남동 카페", "display": 3, "format": "json"},
        "headers": {"X-NCP-APIGW-API-KEY-ID": KEY_ID, "X-NCP-APIGW-API-KEY": KEY},
    },
    {
        "name": "예전 방식 (혹시 이쪽이면)",
        "url": "https://openapi.naver.com/v1/search/blog.json",
        "params": {"query": QUERY, "display": 3, "sort": "date"},
        "headers": {"X-Naver-Client-Id": KEY_ID, "X-Naver-Client-Secret": KEY},
    },
]


# 검색어트렌드(데이터랩)는 POST에 JSON 본문을 실어 보낸다. 검색 API와 방식이
# 달라 따로 둔다. HUB에서의 주소를 문서마다 다르게 적어 두어, 후보를 모두
# 두드려 보고 어느 것이 되는지 눈으로 확인한다.
TREND_BODY = {
    "startDate": "2026-06-01",
    "endDate": "2026-08-31",
    "timeUnit": "month",
    "keywordGroups": [
        {"groupName": "성수동 카페", "keywords": ["성수동 카페"]},
        {"groupName": "후암동 카페", "keywords": ["후암동 카페"]},
    ],
}

TREND_URLS = [
    "https://naverapihub.apigw.ntruss.com/datalab/v1/search",
    "https://naverapihub.apigw.ntruss.com/datalab/v1/search/trend",
    "https://naverapihub.apigw.ntruss.com/v1/datalab/search",
    "https://openapi.naver.com/v1/datalab/search",
]


def probe_trend():
    """검색어트렌드가 어느 주소로 열리는지 찾는다."""
    print("=" * 60)
    print("검색어트렌드(데이터랩) 주소 찾기")
    print("=" * 60)
    body = json.dumps(TREND_BODY).encode("utf-8")
    found = False
    for url in TREND_URLS:
        headers = {"Content-Type": "application/json"}
        if "openapi.naver.com" in url:
            headers["X-Naver-Client-Id"] = KEY_ID
            headers["X-Naver-Client-Secret"] = KEY
        else:
            headers["X-NCP-APIGW-API-KEY-ID"] = KEY_ID
            headers["X-NCP-APIGW-API-KEY"] = KEY
        print(f"[POST] {url}")
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            print(f"  HTTP {resp.status}  ✅  이 주소가 맞습니다")
            print("    최상위 키:", ", ".join(payload.keys()))
            for result in (payload.get("results") or [])[:2]:
                print(f"    {result.get('title')}: {result.get('data')}")
            found = True
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            print(f"  HTTP {exc.code}  ❌  {detail}")
        except Exception as exc:
            print(f"  실패 ❌  {exc}")
    if not found:
        print("\n  어느 주소도 열리지 않았습니다.")
        print("  콘솔의 Application에 '검색어트렌드'를 추가했는지 확인하세요.")
    print()


def describe(payload):
    """응답이 어떤 모양인지 사람이 읽을 수 있게 풀어 준다."""
    print("    최상위 키:", ", ".join(payload.keys()))
    items = payload.get("items") or []
    print(f"    items 개수: {len(items)}  (total={payload.get('total')})")
    if not items:
        return
    print("    한 건의 필드:", ", ".join(items[0].keys()))
    print("    --- 첫 세 건 ---")
    for item in items[:3]:
        for key, value in item.items():
            text = str(value)
            if len(text) > 110:
                text = text[:110] + "…"
            print(f"      {key}: {text}")
        print("      ·")


def main():
    if not KEY_ID or not KEY:
        print("인증키가 비어 있습니다. GitHub Secrets에 "
              "NAVER_API_KEY_ID 와 NAVER_API_KEY 를 넣었는지 확인하세요.")
        sys.exit(1)

    print(f"검색어: {QUERY}\n")
    ok = False
    for attempt in ATTEMPTS:
        url = attempt["url"] + "?" + urllib.parse.urlencode(attempt["params"])
        print(f"[{attempt['name']}]")
        print(f"  {attempt['url']}")
        request = urllib.request.Request(url, headers=attempt["headers"])
        try:
            with urllib.request.urlopen(request, timeout=30) as resp:
                body = resp.read().decode("utf-8")
            print(f"  HTTP {resp.status}  ✅")
            describe(json.loads(body))
            ok = True
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            print(f"  HTTP {exc.code}  ❌  {detail}")
        except Exception as exc:
            print(f"  실패 ❌  {exc}")
        print()

    probe_trend()

    if not ok:
        print("어느 방식으로도 응답을 받지 못했습니다. 위 오류 내용을 알려주세요.")
        sys.exit(1)


if __name__ == "__main__":
    main()
