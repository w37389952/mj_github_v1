"""네이버 블로그에서 신상 가게 이야기를 모은다.

인허가 데이터는 신고가 처리되어야 보이므로 실제 오픈보다 며칠 늦다. 블로그는
다녀온 날 바로 올라오므로 그 빈틈을 메운다. 대신 광고 글이 섞이고 주소가
정확하지 않아, 인허가 목록과는 따로 둔다.
"""

import json
import os
import re
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naver  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

WINDOW_DAYS = int(os.environ.get("BLOG_WINDOW_DAYS", "14"))

# 내가 쓴 글은 이미 아는 곳이므로 뺀다. 쉼표로 여러 개 넣을 수 있다.
MY_BLOGS = [b.strip().lower() for b in
            os.environ.get("MY_BLOG_IDS", "haranalice").split(",") if b.strip()]

# 이름값 하는 동네를 앞에 붙여 좁힌다. 그냥 '신상카페'만 치면 전국이 섞인다.
AREAS = [
    "연남동", "연희동", "성수동", "서울숲", "망원동", "합정동", "상수동",
    "익선동", "삼청동", "북촌", "서촌", "을지로", "한남동", "이태원",
    "해방촌", "후암동", "가로수길", "압구정", "청담동", "성북동", "문래동",
    "송파", "잠실", "여의도", "공덕", "신촌", "홍대", "종로", "명동",
]
# 사람들이 실제로 쓰는 말을 넓게 잡는다. '신상카페'만 치면 블로그를 업으로
# 하는 사람 글만 걸리고, 지인 가게 소식을 알리는 일상글은 빠진다.
TOPICS = [
    "신상카페", "가오픈", "새로 생긴 카페", "오픈했어요", "프리오픈",
]
# 지역을 안 붙이고 서울 전체로 한 번 더 훑을 말들.
WIDE_TOPICS = [
    "서울 신상카페", "서울 가오픈 카페", "카페 오픈 소식", "정식오픈 카페",
    "새로 생긴 맛집", "카페 오픈 준비",
]

# 협찬 글을 버리지 않는다. 초대받아 가오픈 전에 다녀온 글일 수 있고,
# 그런 글이 오히려 가장 빠른 소식이다. 대신 표시해 두어 사람이 가려 보게 한다.
PROMO =["체험단", "협찬", "원고료", "소정의", "제공받", "무료로 제공", "서포터즈"]

# 이건 가게 소식이 아니라 장사 글이다. 이쪽은 뺀다.
SPAM = ["공동구매", "쿠폰", "할인코드", "적립금", "부업", "재테크", "대출"]


# 제목 끝에 붙는 일반 낱말. 이건 가게 이름이 아니다.
GENERIC_TAIL = {
    "본점", "지점", "점", "카페", "북카페", "커피", "맛집", "바", "집", "식당",
    "베이커리", "디저트", "브런치", "술집", "펍", "가게", "공간", "후기", "방문",
}


# 가게 이름이지만 일상어로도 흔히 쓰이는 말. 홀로 쓰면 오탐이 난다.
TOO_COMMON = {
    "비가", "종묘", "운치", "프로젝트", "익스프레스", "하우스", "가든",
    "스튜디오", "로스터리", "공장", "클럽", "라운지", "테라스", "정원",
    "다방", "골목", "시장", "광장", "공원", "거리", "역시", "그날", "오늘",
    # 음식·메뉴 이름. 홀로 쓰면 남의 글까지 지운다.
    "바베큐", "오마카세", "파스타", "피자", "케이크", "빙수", "젤라또",
    "와인", "위스키", "칵테일", "브런치", "샐러드", "스테이크", "라멘",
    "국수", "냉면", "김밥", "떡볶이", "치킨", "삼겹살", "곱창", "회",
    "커피", "라떼", "에스프레소", "핸드드립", "원두", "디저트", "빵",
}


def shop_names_from_rss(blog_ids):
    """내 블로그 RSS에서 이미 다녀온 가게 이름을 뽑는다.

    제목이 '[동네] [수식어] 카페 [가게이름]' 꼴이라 맨 뒤가 가게 이름이다.
    한 낱말짜리와 두 낱말짜리를 모두 후보로 둔다. '프랙티스 프로젝트'처럼
    두 낱말인 이름도 있기 때문이다.
    """
    names = set()
    for blog_id in blog_ids:
        url = f"https://rss.blog.naver.com/{blog_id}.xml"
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                xml = resp.read().decode("utf-8", "replace")
        except Exception as exc:
            print(f"  RSS를 읽지 못했습니다({blog_id}): {exc}", file=sys.stderr)
            continue

        titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", xml, re.S)
        if not titles:
            continue
        # 맨 앞은 블로그 이름이고, 그 이름이 채널과 이미지에 두 번 실려 온다.
        # 개수를 세어 자르면 판이 바뀔 때 또 새므로, 이름과 같은 제목을 지운다.
        channel = titles[0].strip()
        for title in titles[1:]:
            if title.strip() == channel:
                continue
            text = re.sub(r"\([^)]*\)", " ", title)
            text = re.sub(r"[^\w가-힣A-Za-z0-9 ]", " ", text)
            words = [w for w in text.split() if w]
            if not words:
                continue
            # 끝에서부터 일반 낱말을 걷어낸다
            while words:
                # '경동시장점'처럼 지점 표시가 낱말에 붙어 오는 경우가 있다.
                words[-1] = re.sub(r"(\d*호)?점$", "", words[-1]) or words[-1]
                if words[-1] in GENERIC_TAIL:
                    words.pop()
                else:
                    break
            if not words:
                continue
            two = f"{words[-2]} {words[-1]}" if len(words) >= 2 else ""
            if two and words[-2] not in GENERIC_TAIL:
                names.add(two)
            # 흔한 낱말은 홀로 쓰면 엉뚱한 글까지 지운다. '비가'가 '비가 온다'에
            # 걸리는 식이다. 그런 이름은 두 낱말 꼴로만 쓴다.
            if len(words[-1]) >= 2 and words[-1] not in TOO_COMMON:
                names.add(words[-1])
    return names


def is_promo(text):
    return any(word in text for word in PROMO)


def is_spam(text):
    return any(word in text for word in SPAM)


def parse_postdate(value):
    """'20260904' 형식으로 온다."""
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except (ValueError, TypeError):
        return None


def main():
    if not naver.enabled():
        print("네이버 인증키가 없습니다. NAVER_API_KEY_ID / NAVER_API_KEY 확인.",
              file=sys.stderr)
        sys.exit(1)

    cutoff = date.today() - timedelta(days=WINDOW_DAYS)

    # 내가 이미 글로 쓴 가게는 아는 곳이다. 다른 사람이 쓴 글이라도 뺀다.
    known = shop_names_from_rss(MY_BLOGS)
    print(f"내 블로그에서 가게 이름 {len(known)}개를 읽었습니다.")

    posts = {}
    dropped_mine = dropped_spam = dropped_old = 0
    dropped_known = {}

    queries = [f"{area} {topic}" for area in AREAS for topic in TOPICS]
    queries += WIDE_TOPICS

    for query in queries:
        for item in naver.search("blog", query, display=20, sort="date"):
            link = item.get("link") or ""
            if not link or link in posts:
                continue

            blogger_link = (item.get("bloggerlink") or "").lower()
            if any(mine in blogger_link or mine in link.lower() for mine in MY_BLOGS):
                dropped_mine += 1
                continue

            posted = parse_postdate(item.get("postdate"))
            if posted is None or posted < cutoff:
                dropped_old += 1
                continue

            title = naver.clean_text(item.get("title"))
            desc = naver.clean_text(item.get("description"))
            if is_spam(title + desc):
                dropped_spam += 1
                continue

            # 내가 이미 다녀온 가게 이야기면 뺀다.
            #
            # 짧은 이름은 제목에서만 찾는다. 본문은 긴 산문이라 '소로'나 '미유'
            # 같은 두세 글자가 우연히 스치기 쉽다. 반대로 '소리사람물'처럼 긴
            # 이름은 우연히 겹칠 일이 없으므로 본문까지 본다.
            hit = next(
                (n for n in known
                 if n in title or (len(n) >= 5 and n in desc)),
                None,
            )
            if hit:
                dropped_known[hit] = dropped_known.get(hit, 0) + 1
                continue

            post = {
                "title": title,
                "description": desc,
                "link": link,
                "blogger": naver.clean_text(item.get("bloggername")),
                "bloggerLink": item.get("bloggerlink") or "",
                "date": posted.isoformat(),
                "area": query.split()[0],
            }
            if is_promo(title + desc):
                post["promo"] = True
            posts[link] = post
        time.sleep(0.1)

    items = sorted(posts.values(), key=lambda p: p["date"], reverse=True)

    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "blog.json").write_text(
        json.dumps({
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "period": {"from": cutoff.isoformat(), "to": date.today().isoformat()},
            "posts": items,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    promo = sum(1 for p in items if p.get("promo"))
    print(f"검색어 {len(queries)}개 → 글 {len(items)}건 (그중 협찬 표시 {promo}건)")
    print(f"  내 글 제외 {dropped_mine} / 장사글 제외 {dropped_spam} / 기간 밖 {dropped_old}")

    # 어떤 이름으로 얼마나 빠졌는지 남긴다. 흔한 낱말이 섞여 엉뚱한 글까지
    # 지우고 있지 않은지 여기서 알아볼 수 있다.
    if dropped_known:
        total = sum(dropped_known.values())
        print(f"  이미 다녀온 곳 제외 {total}건")
        for name, count in sorted(dropped_known.items(), key=lambda x: -x[1])[:15]:
            print(f"    {name}: {count}")


if __name__ == "__main__":
    main()
