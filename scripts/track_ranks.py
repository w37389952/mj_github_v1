"""내 글이 목표 검색어에서 몇 위인지 날마다 재서 쌓는다.

제목·글자수를 바꾼 것이 효과가 있었는지 알려면 순위를 시간에 걸쳐
봐야 한다. 하루치 순위는 아무것도 말해 주지 않는다.

등록은 받지 않는다. RSS에서 최근 글을 집어 제목에서 목표 검색어를
뽑아낸다. 사람이 손댈 것이 없어야 빠뜨리지 않는다.

검색 결과는 로그인 없이 긁는다. 인증키가 필요 없다.
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STORE = DATA / "ranks.json"

BLOG_ID = "haranalice"
KEEP_POSTS = 24          # 최근 글 몇 편까지 좇을지
KEEP_DAYS = 90           # 기록을 며칠치 남길지
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

TYPE_WORDS = ["카페", "맛집", "베이커리", "브런치", "디저트", "술집",
              "이자카야", "레스토랑", "빵집", "바",
              # 이런 합성어를 안 넣어 두면 '봉천동 북카페 소로'에서 업종을
              # 못 찾아 목표 검색어가 통째로 비었다.
              "북카페", "LP카페", "감성카페", "대형카페", "찻집", "고기집"]

# 제목 끝에 붙는 일반 낱말. 가게 이름이 아니다.
GENERIC_TAIL = {"본점", "지점", "점", "카페", "북카페", "커피", "맛집", "바",
                "집", "식당", "베이커리", "디저트", "브런치", "술집", "펍",
                "가게", "공간", "후기", "방문", "추천"}

# 가게 이름처럼 보이지만 일상어로도 흔한 말. 이걸로 순위를 재면 남의 글이
# 잔뜩 잡혀 아무 뜻이 없다. 2026-09-05 첫 수집에서 '종묘', '프로젝트',
# '위사'가 목표 검색어로 잡혔다.
TOO_COMMON = {
    "종묘", "프로젝트", "익스프레스", "하우스", "가든", "스튜디오", "로스터리",
    "공장", "클럽", "라운지", "테라스", "정원", "다방", "골목", "시장", "광장",
    "공원", "거리", "비가", "운치", "오늘", "그날", "역시", "사람", "이야기",
    "시간", "하루", "우리", "여기", "그곳", "동네", "서울", "주말", "산책",
}
MIN_NAME_LEN = 3          # 두 글자 이름은 우연히 겹치기 쉬워 뺀다

# 동네 이름 판별.
#
# 처음에는 [가-힣]{2,4}(동|가) 하나로 봤는데, '커피가 맛있는'의 '커피가'가
# 걸렸다. 앞 두 글자 '커피' + 조사 '가'를 '종로1가' 같은 법정동으로 본 것이다.
# 그래서 2026-09-10 로그에 '커피가 카페 없음'이 찍혔다.
# '가'로 끝나는 법정동은 앞에 숫자가 붙으므로(종로1가·한강로3가) 숫자를 요구한다.
AREA_RE = re.compile(r"[가-힣]{2,4}동\d*가?|[가-힣]{2,5}\d+가")

# '동'으로 끝나지 않는 동네도 제목에 자주 쓴다. 이것들이 안 잡혀
# '여의도 맛집', '해방촌 카페' 같은 목표 검색어를 놓치고 있었다.
AREA_WORDS = {
    "합정", "여의도", "해방촌", "서촌", "북촌", "성수", "서울숲", "뚝섬",
    "연남", "홍대", "을지로", "명동", "종로", "신촌", "이대", "압구정",
    "청담", "삼청", "익선", "후암", "한남", "이태원", "강남", "역삼",
    "마포", "문래", "망원", "상수", "서교", "구산", "응암", "불광",
    "연신내", "가산", "독산", "효창공원", "봉천", "신림", "화곡", "등촌",
    "제기", "성북", "삼선", "당산", "송파", "잠실", "방이", "공덕",
    "아현", "충무로", "신당", "용산", "삼각지", "가로수길", "성수동",
    "노원", "수유", "왕십리", "건대", "청파", "남영", "영등포",
}


# 역 이름도 동네 노릇을 한다. '구산역 카페'로 찾는 사람이 있다.
STATION_RE = re.compile(r"[가-힣]{2,5}역")


def is_area(word):
    return (bool(AREA_RE.fullmatch(word))
            or word in AREA_WORDS
            or bool(STATION_RE.fullmatch(word)))

POST_RE = re.compile(r"(?s)<item>(.*?)</item>")
TITLE_RE = re.compile(r"(?s)<title><!\[CDATA\[(.*?)\]\]></title>")
LINK_RE = re.compile(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>")
DATE_RE = re.compile(r"<pubDate>(.*?)</pubDate>")

# 검색 결과에서 블로그 아이디를 순서대로 뽑는다. 주소가 /로 이스케이프
# 되어 오므로 먼저 풀어야 한다. 안 풀면 아이디를 'u002F…'로 잘못 읽는다.
BLOG_LINK_RE = re.compile(r"blog\.naver\.com/([A-Za-z0-9_\-]+)/(\d{6,})")


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=25) as resp:
        return resp.read().decode("utf-8", "replace")


def recent_posts():
    """RSS에서 최근 글의 제목·번호·날짜를 뽑는다."""
    try:
        xml = fetch(f"https://rss.blog.naver.com/{BLOG_ID}.xml")
    except Exception as exc:
        print(f"RSS를 읽지 못했습니다: {exc}", file=sys.stderr)
        return []

    posts = []
    for block in POST_RE.findall(xml)[:KEEP_POSTS]:
        match = TITLE_RE.search(block)
        title = match.group(1).strip() if match else ""
        link = LINK_RE.search(block)
        log_no = ""
        if link:
            found = re.search(rf"{BLOG_ID}/(\d+)", link.group(1))
            log_no = found.group(1) if found else ""
        when = ""
        stamp = DATE_RE.search(block)
        if stamp:
            try:
                when = datetime.strptime(
                    stamp.group(1)[5:16], "%d %b %Y").date().isoformat()
            except ValueError:
                when = ""
        if title and log_no:
            posts.append({"logNo": log_no, "title": title, "date": when})
    return posts


def target_keywords(title):
    """제목에서 이 글이 노렸을 검색어를 뽑는다.

    사람들이 실제로 치는 말은 '동네 + 업종'과 가게 이름이다.
    낱말 단위로만 본다. '유진막국수'를 '유진막 국수'로 쪼개던 실수를
    되풀이하지 않기 위해서다.
    """
    text = re.sub(r"\([^)]*\)", " ", title)
    text = re.sub(r"[^\w가-힣A-Za-z0-9 ]", " ", text)
    words = [w for w in text.split() if w]
    if not words:
        return []

    out = []
    # 동네(OO동/OO가) 뒤나 앞에 업종어가 낱말로 있으면 그 짝을 쓴다.
    areas = [w for w in words if is_area(w)]
    kinds = [w for w in words if w in TYPE_WORDS]
    if areas and kinds:
        out.append(f"{areas[0]} {kinds[0]}")

    # 가게 이름. 뒤에서부터 일반 낱말을 걷어낸 마지막 낱말로 본다.
    tail = list(words)
    while tail and tail[-1] in GENERIC_TAIL:
        tail.pop()
    if tail:
        last = tail[-1]
        # 흔한 말이거나 너무 짧으면 앞 낱말을 붙여 구체화한다.
        # '프랙티스 프로젝트'처럼 두 낱말이면 우연히 겹칠 일이 없다.
        if last in TOO_COMMON or len(last) < MIN_NAME_LEN:
            if len(tail) >= 2 and tail[-2] not in GENERIC_TAIL:
                name = f"{tail[-2]} {last}"
            else:
                name = ""
        else:
            name = last
        if name and name not in out:
            out.append(name)

    return out[:3]


def rank_of(query, blog_id=BLOG_ID):
    """블로그 탭에서 몇 번째로 나오는지. 안 보이면 None."""
    url = ("https://search.naver.com/search.naver?ssc=tab.blog.all&sm=tab_jum"
           f"&query={urllib.parse.quote(query)}")
    try:
        html = fetch(url).replace("\\u002F", "/").replace("\\u002f", "/")
    except Exception:
        return None, 0

    seen = []
    for match in BLOG_LINK_RE.finditer(html):
        found = match.group(1)
        if found not in seen:
            seen.append(found)
    if blog_id in seen:
        return seen.index(blog_id) + 1, len(seen)
    return None, len(seen)


def load_store():
    if not STORE.exists():
        return {"posts": {}}
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        return {"posts": {}}


def main():
    today = date.today().isoformat()
    store = load_store()
    posts = store.get("posts") or {}

    fresh = recent_posts()
    if not fresh:
        print("최근 글을 읽지 못해 이번 회차는 건너뜁니다.", file=sys.stderr)
        return

    print(f"글 {len(fresh)}편의 순위를 잽니다")
    measured = 0

    for post in fresh:
        entry = posts.setdefault(post["logNo"], {
            "title": post["title"],
            "date": post["date"],
            "keywords": [],
            "history": {},
        })
        entry["title"] = post["title"]
        if post["date"]:
            entry["date"] = post["date"]
        if not entry["keywords"]:
            entry["keywords"] = target_keywords(post["title"])
        if not entry["keywords"]:
            continue

        row = {}
        for query in entry["keywords"]:
            place, pool = rank_of(query)
            row[query] = place
            measured += 1
            time.sleep(0.8)
        entry["history"][today] = row

        marks = ", ".join(
            f"{q} {('%d위' % p) if p else '없음'}" for q, p in row.items())
        print(f"  {post['title'][:34]:<34} {marks}")

    # 오래된 기록은 버린다. 파일이 계속 부풀면 화면이 무거워진다.
    cutoff = (date.today().toordinal() - KEEP_DAYS)
    for entry in posts.values():
        entry["history"] = {
            day: row for day, row in entry["history"].items()
            if date.fromisoformat(day).toordinal() >= cutoff
        }

    # 좇는 글도 최근 것만 남긴다.
    keep = {p["logNo"] for p in fresh}
    posts = {k: v for k, v in posts.items() if k in keep}

    DATA.mkdir(exist_ok=True)
    STORE.write_text(
        json.dumps({
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "blogId": BLOG_ID,
            "note": "순위는 네이버 블로그 탭 기준이며 30위 밖은 '없음'으로 적는다.",
            "posts": posts,
        }, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"검색 {measured}회, 글 {len(posts)}편을 기록했습니다.")


if __name__ == "__main__":
    main()
