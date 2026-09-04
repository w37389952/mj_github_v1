"""네이버 검색 API(NAVER API HUB)를 부르는 공통 부분.

2026-09-04 실제 호출로 확인한 사양이다.
  주소   https://naverapihub.apigw.ntruss.com/search/v1/{blog|local}
  헤더   X-NCP-APIGW-API-KEY-ID / X-NCP-APIGW-API-KEY
  예전 방식(openapi.naver.com + X-Naver-Client-*)은 401로 막힌다.
"""

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://naverapihub.apigw.ntruss.com/search/v1"
KEY_ID = os.environ.get("NAVER_API_KEY_ID", "")
KEY = os.environ.get("NAVER_API_KEY", "")

HEADERS = {
    "X-NCP-APIGW-API-KEY-ID": KEY_ID,
    "X-NCP-APIGW-API-KEY": KEY,
}

# 제목과 설명에는 검색어가 <b>태그로 감싸여 온다.
TAG = re.compile(r"<[^>]+>")
ENTITIES = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'"}


def enabled():
    return bool(KEY_ID and KEY)


def clean_text(text):
    text = TAG.sub("", text or "")
    for entity, ch in ENTITIES.items():
        text = text.replace(entity, ch)
    return text.strip()


def search(kind, query, display=10, sort=None, attempts=3):
    """kind는 'blog' 또는 'local'. 실패하면 재시도하고, 끝내 안 되면 빈 목록."""
    params = {"query": query, "display": display, "format": "json"}
    if sort:
        params["sort"] = sort
    url = f"{BASE}/{kind}?" + urllib.parse.urlencode(params)

    delay = 2
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8")).get("items", [])
        except urllib.error.HTTPError as exc:
            # 잘못된 검색어나 결과 없음은 재시도해도 달라지지 않는다.
            if exc.code in (400, 404):
                return []
            if attempt == attempts - 1:
                return []
        except Exception:
            if attempt == attempts - 1:
                return []
        time.sleep(delay)
        delay *= 2
    return []


def road_key(address):
    """주소를 견주기 좋게 다듬는다. 층·호수와 괄호 안은 떼어낸다.

    '서울특별시 마포구 동교로38길 33-10 2층' → '마포구동교로38길33-10'
    """
    text = (address or "").split(",")[0]
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\s*(지하\s*)?\d+\s*층.*$", " ", text)
    text = re.sub(r"^\s*서울(특별시)?\s*", "", text)
    return re.sub(r"\s+", "", text)


def find_place(name, address):
    """가게 하나를 지역 검색에서 찾아 공식 링크를 얻는다.

    지역 검색은 한 번에 다섯 건까지만 준다. 그래서 이름으로 좁혀 찾고,
    도로명주소가 맞는 것만 받아들인다. 이름이 비슷한 다른 가게를 잘못
    집어오지 않기 위해서다.
    """
    want = road_key(address)
    if not want:
        return None

    for query in (f"{name} {address.split()[1] if len(address.split()) > 1 else ''}".strip(), name):
        for item in search("local", query, display=5):
            got = road_key(item.get("roadAddress") or item.get("address"))
            if got and got == want:
                return {
                    "link": item.get("link") or "",
                    "category": item.get("category") or "",
                    "naverName": clean_text(item.get("title")),
                }
        time.sleep(0.1)
    return None
