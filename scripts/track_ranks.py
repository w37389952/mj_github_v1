"""내 글이 목표 검색어에서 몇 위인지 날마다 재서 쌓는다.

제목·글자수를 바꾼 것이 효과가 있었는지 알려면 순위를 시간에 걸쳐
봐야 한다. 하루치 순위는 아무것도 말해 주지 않는다.

등록은 받지 않는다. RSS에서 최근 글을 집어 제목에서 목표 검색어를
뽑아낸다. 사람이 손댈 것이 없어야 빠뜨리지 않는다.

검색 결과는 로그인 없이 긁는다. 인증키가 필요 없다.
"""

import json
import random
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

# 업종어를 고르는 차례. 앞자리일수록 먼저 고른다.
#
# 맨 앞의 것을 집던 때는 '빙수 맛집 카페 틸데'에서 '맛집'을 골라
# '후암동 맛집'을 쟀다. 카페 글인데 맛집으로 잰 셈이다. 자리가 아니라
# 구체성으로 고른다 — 무엇을 파는지가 가장 또렷한 말이 먼저다.
TYPE_TIERS = [
    # 1. 무엇을 파는지
    ["빙수", "파르페", "젤라또", "바베큐", "야장", "곱창", "막창", "삼겹살",
     "국수", "칼국수", "쌀국수", "냉면", "파스타", "라멘", "우동", "초밥",
     "돈까스", "치킨", "피자", "김밥", "떡볶이", "덮밥", "약과", "소금빵"],
    # 2. 어떤 집인지 · 무엇으로 내리는지
    #    '핸드드립 맛집'이라 적었더니 '맛집'을 집어 '상수동 맛집'을 쟀다.
    #    카페 글을 맛집으로 잰 셈이다. 커피 말들도 업종 노릇을 한다.
    ["북카페", "LP카페", "감성카페", "대형카페", "베이커리", "브런치",
     "디저트", "찻집", "와인바", "위스키바", "이자카야", "고기집", "빵집",
     "포차", "호프",
     "핸드드립", "드립커피", "스페셜티", "로스터리", "에스프레소", "무인카페"],
    # 3. 뭉뚱그린 말. 위에 아무것도 없을 때만 쓴다.
    ["카페", "맛집", "술집", "바", "레스토랑"],
]
TYPE_WORDS_ALL = [w for tier in TYPE_TIERS for w in tier]

# 제목 끝에 붙는 일반 낱말. 가게 이름이 아니다.
GENERIC_TAIL = {"본점", "지점", "점", "커피", "집", "식당", "펍",
                "가게", "공간", "방문", "위치",
                # 의도어. '내돈내산 솔직후기'로 끝나는 제목에서 '솔직후기'를
                # 가게 이름으로 집어 순위를 재고 있었다.
                "후기", "솔직후기", "내돈내산", "추천", "강추", "리뷰",
                "데이트", "코스", "신상", "오픈", "가오픈"} | set(TYPE_WORDS_ALL)

# 가게 이름 자리에 오면 안 되는 꼴. 꾸밈말과 풀이말이다.
# '감각적인 카페 바'에서 '감각적인'을 가게 이름으로 집은 일이 있었다.
NOT_A_NAME = re.compile(r"(적인|스러운|다운|같은|좋은|는|은|던|한|인|의|게|서|고|며|기|듯)$")

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
    "동대문역사문화공원", "동대문", "후암시장", "광장시장", "경리단길",
}


# 역 이름도 동네 노릇을 한다. '구산역 카페'로 찾는 사람이 있다.
STATION_RE = re.compile(r"[가-힣]{2,5}역")


# 동네 뒤에도 조사가 붙는다. '후암동에 2호점을'의 '후암동에'가 안 걸려
# 목표 검색어가 통째로 비던 일이 있었다.
AREA_JOSA = re.compile(r"(에서|으로|에|은|는|이|가|의|도|와|과|까지|부터|쪽)$")


def looks_area(w):
    return (bool(AREA_RE.fullmatch(w))
            or w in AREA_WORDS
            or bool(STATION_RE.fullmatch(w)))


def bare_area(word):
    """조사를 떼고 동네 이름만 남긴다.

    떼기 전에 먼저 그대로 맞는지 본다. '여의도'의 '도'를 조사로 보고 떼면
    '여의'가 되어 동네가 사라진다. 실제로 '여의도 찻집'을 통째로 놓쳤다.
    """
    if looks_area(word):
        return word
    cut = AREA_JOSA.sub("", word)
    return cut if len(cut) >= 2 and looks_area(cut) else word


def is_area(word):
    return looks_area(word) or looks_area(bare_area(word))

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
    areas = [bare_area(w) for w in words if is_area(w)]

    # 업종어는 자리가 아니라 구체성으로 고른다. 둘까지 재서 결과로 판단한다 —
    # 어느 쪽이 걸릴지는 미리 알 수 없고 재보면 알 수 있는 일이다.
    kinds = []
    for tier in TYPE_TIERS:
        for w in words:
            if w in tier and w not in kinds:
                kinds.append(w)
    # 카페 글에 '맛집'을 같이 달지 않는다. 찾는 사람이 다르다 —
    # '상수동 맛집'을 치는 사람은 밥집을 찾는 것이지 카페를 찾는 것이 아니다.
    if "카페" in kinds:
        for weak in ("맛집", "바"):
            if weak in kinds:
                kinds.remove(weak)

    # 동네를 하나도 못 찾았으면 첫 낱말을 동네로 본다. 내 제목은 늘
    # 동네로 시작한다. '까치산 카페 맥파이마운틴'의 까치산이 표에 없어
    # 목표 검색어가 가게 이름 하나뿐이던 일이 있었다.
    if not areas and words and kinds:
        head = words[0]
        if (re.fullmatch(r"[가-힣]{2,5}", head) and head not in TYPE_WORDS_ALL
                and head not in TOO_COMMON and not NOT_A_NAME.search(head)):
            areas = [head]

    for kind in kinds[:2]:
        if areas:
            out.append(f"{areas[0]} {kind}")

    name = shop_name(title, words)
    if name and name not in out:
        out.append(name)

    return out[:4]     # 동네+업종 둘 + 가게 이름


def shop_name(title, words):
    """제목에서 가게 이름을 집는다.

    내 제목은 두 가지 꼴이다.
      예전 : 후암동에 2호점을 오픈한 빙수 맛집 카페⛅ 틸데   (이모지 뒤가 이름)
      요즘 : 상수동 카페 에드로스트웍스ㅣ⛅ 햇살이…          (ㅣ 앞이 이름)
    그래서 ㅣ가 있으면 그 앞 토막에서, 없으면 이모지 뒤에서 찾는다.
    둘 다 없으면 예전처럼 뒤에서 일반 낱말을 걷어내며 찾는다.
    """
    def pick(chunk):
        chunk = re.sub(r"\([^)]*\)", " ", chunk)      # (캐치테이블 팁) 같은 것은 뺀다
        bits = [w for w in re.sub(r"[^\w가-힣A-Za-z0-9 ]", " ", chunk).split() if w]
        # 뒤에서부터 걷어낸다. 동네 이름도 가게 이름이 아니다 —
        # '육즙관리소 더룸 을지로 내돈내산 솔직후기'에서 '을지로'를 집은 일이 있었다.
        while bits and (bits[-1] in GENERIC_TAIL
                        or NOT_A_NAME.search(bits[-1])
                        or is_area(bits[-1])):
            bits.pop()
        if not bits:
            return ""
        last = bits[-1]
        if last in TOO_COMMON:
            if len(bits) >= 2 and bits[-2] not in GENERIC_TAIL:
                return f"{bits[-2]} {last}"
            return ""
        # 두 글자 이름이 많다 — 틸데·소로·뚜뚜·미유·퍼슨·라하. 앞 낱말이
        # 이름의 일부로 보이면 붙이고(한강 토오베), 아니면 그대로 쓴다.
        if len(last) < MIN_NAME_LEN and len(bits) >= 2:
            prev = bits[-2]
            if prev not in GENERIC_TAIL and not is_area(prev) \
                    and not NOT_A_NAME.search(prev) and len(prev) >= 2:
                return f"{prev} {last}"
        return last

    # 1) ㅣ 나 | 로 나뉘면 앞 토막 끝이 가게 이름이다.
    for sep in ("ㅣ", "|", "｜"):
        if sep in title:
            got = pick(title.split(sep)[0])
            if got:
                return got

    # 2) 이모지가 있으면 그 뒤가 통째로 가게 이름이다. 내 제목 120편이 그 꼴이다.
    #    여기서는 뒤가 아니라 앞에서 집는다. '카르마커피 더 블랙 청담'에서
    #    뒤부터 걷어내면 '블랙'만 남아, 아무 글이나 걸리는 검색어가 된다.
    marks = list(re.finditer(r"[\U0001F300-\U0001FAFF☀-➿️]", title))
    if marks:
        after = re.sub(r"\([^)]*\)", " ", title[marks[-1].end():])
        bits = [w for w in re.sub(r"[^\w가-힣A-Za-z0-9 ]", " ", after).split() if w]
        bits = [w for w in bits if w not in GENERIC_TAIL]
        if bits:
            head = bits[0]
            if len(head) >= MIN_NAME_LEN:
                return head
            if len(bits) >= 2:
                return f"{head} {bits[1]}"
            return head

    # 3) 그 밖에는 뒤에서부터 걷어낸다.
    return pick(title)


def breath():
    """검색 사이에 쉬는 시간(초).

    0.8초로 규칙적으로 두드리면 기계로 보인다. 사람이 검색하는 속도에 가깝게
    2~5초로 늘리고 들쭉날쭉하게 둔다. 마흔 번이면 2분 남짓 더 걸리지만,
    한 회차를 통째로 날리는 것보다 낫다.
    """
    return random.uniform(2.0, 5.0)


def rank_of(query, blog_id=BLOG_ID, attempts=3):
    """블로그 탭에서 몇 번째로 나오는지. 안 보이면 None.

    두 번째 값은 결과에서 찾은 블로그 수다. 0이면 '30위 밖'이 아니라
    '못 읽었다'는 뜻이므로 부르는 쪽에서 갈라 써야 한다.

    네이버는 한 IP에서 검색이 잦으면 빈 화면을 준다. 2026-09-12에 마흔 번을
    내리 그렇게 받아 순위가 다 무너진 것처럼 찍혔다. 같은 시각에 집 인터넷에서는
    멀쩡히 됐으니 IP를 보고 막은 것이다. 그래서 빈 화면이면 좀 쉬었다 다시 묻는다.
    """
    url = ("https://search.naver.com/search.naver?ssc=tab.blog.all&sm=tab_jum"
           f"&query={urllib.parse.quote(query)}")
    for attempt in range(1, attempts + 1):
        try:
            html = fetch(url).replace("\\u002F", "/").replace("\\u002f", "/")
        except Exception:
            html = ""

        seen = []
        for match in BLOG_LINK_RE.finditer(html):
            found = match.group(1)
            if found not in seen:
                seen.append(found)

        if seen:
            if blog_id in seen:
                return seen.index(blog_id) + 1, len(seen)
            return None, len(seen)

        if attempt < attempts:
            time.sleep(5 * attempt)          # 5초, 10초 쉬었다 다시
    return None, 0


def load_store():
    if not STORE.exists():
        return {"posts": {}}
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        return {"posts": {}}


def drop_blind_days(posts):
    """이미 남아 있는 '통째로 못 잰 날'을 지운다.

    막히기 전에 쌓인 기록에는 하루치가 전부 '없음'인 날이 섞여 있다.
    그날을 그대로 두면 화면에서 순위가 무너진 것처럼 보인다. 한 글의
    검색어가 하나도 안 잡힌 날은 잰 것이 아니므로 지운다. 다만 정말로
    다 밀린 날과 구별할 수 없으므로, 같은 날 모든 글이 그랬을 때만 지운다.
    """
    days = {}
    for entry in posts.values():
        for day, row in (entry.get("history") or {}).items():
            got = sum(1 for v in row.values() if v is not None)
            hit, total = days.get(day, (0, 0))
            days[day] = (hit + got, total + len(row))

    bad = [day for day, (hit, total) in days.items() if total and hit == 0]
    for day in bad:
        for entry in posts.values():
            (entry.get("history") or {}).pop(day, None)
    if bad:
        print(f"  통째로 못 잰 날을 지웠습니다: {', '.join(sorted(bad))}")
    return posts


def main():
    today = date.today().isoformat()
    store = load_store()
    posts = drop_blind_days(store.get("posts") or {})

    fresh = recent_posts()
    if not fresh:
        print("최근 글을 읽지 못해 이번 회차는 건너뜁니다.", file=sys.stderr)
        return

    print(f"글 {len(fresh)}편의 순위를 잽니다")
    measured = 0
    blind = 0                 # 검색 결과를 아예 못 읽은 횟수

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
        # 한 번 뽑고 그대로 두었더니, 뽑는 규칙을 고쳐도 예전 글에는 안 먹혔다.
        # '커피가 카페', '감각적인', '솔직후기' 같은 것이 계속 남아 있었다.
        # 규칙은 정해진 대로 도는 것이니 회차마다 다시 뽑는다.
        fresh_kw = target_keywords(post["title"])
        if fresh_kw and fresh_kw != entry["keywords"]:
            gone = [k for k in entry["keywords"] if k not in fresh_kw]
            entry["keywords"] = fresh_kw
            # 더 안 재는 검색어의 지난 기록은 지운다. 표에 남아 헷갈린다.
            for row_day in entry["history"].values():
                for k in gone:
                    row_day.pop(k, None)
        if not entry["keywords"]:
            continue

        row = {}
        marks = []
        for query in entry["keywords"]:
            place, pool = rank_of(query)
            measured += 1
            if pool == 0:
                # 검색 결과에 블로그가 한 건도 없다는 것은 '내 글이 30위 밖'이
                # 아니라 '못 읽었다'는 뜻이다. 네이버가 막았거나 화면이 바뀐 것이다.
                # 그것을 '없음'으로 적으면 순위가 무너진 것처럼 보인다.
                blind += 1
                marks.append(f"{query} 못 쟀음")
                time.sleep(breath())
                continue
            row[query] = place
            marks.append(f"{query} {('%d위' % place) if place else '없음'}")
            time.sleep(0.8)

        # 한 글의 검색어를 하나도 못 쟀으면 그 날짜를 아예 남기지 않는다.
        if row:
            entry["history"][today] = row
        print(f"  {post['title'][:34]:<34} {', '.join(marks)}")

    # 한 번도 못 읽었으면 파일을 건드리지 않는다.
    #
    # 2026-09-12에 마흔 번을 다 못 읽고 전부 '없음'으로 적혀, 7일 연속 1위였던
    # 글까지 30위 밖으로 찍혔다. 그것을 막으려고 '절반 넘게 못 읽으면 통째로
    # 버린다'고 했더니 이번엔 반대로 지나쳤다. 2026-09-14에 절반쯤 읽었는데도
    # 회차를 통째로 버려, 검색어를 고친 것조차 반영되지 않았다.
    #
    # 못 읽은 검색어는 이미 위에서 안 적고 넘어간다. 그러니 하나라도 읽었으면
    # 읽은 만큼 남기는 것이 맞다. 잘못된 값이 섞일 일은 없다.
    # 못 읽은 검색어는 위에서 이미 안 적고 넘어갔다. 그러니 잘못된 값이 섞일
    # 일이 없고, 파일을 안 쓸 이유도 없다. 검색어를 고친 것·글 목록이 바뀐 것은
    # 네이버를 못 읽어도 남겨야 한다.
    if blind:
        print(f"  검색 {measured}번 중 {blind}번은 못 읽어 그 검색어만 건너뜁니다.",
              file=sys.stderr)
    if blind == measured and measured:
        print("  이번엔 하나도 못 읽었습니다. 순위는 안 쌓이고 검색어만 고쳐 둡니다.",
              file=sys.stderr)

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
