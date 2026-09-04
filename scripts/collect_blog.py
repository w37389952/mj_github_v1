"""네이버 블로그에서 신상 가게 이야기를 모은다.

인허가 데이터는 신고가 처리되어야 보이므로 실제 오픈보다 며칠 늦다. 블로그는
다녀온 날 바로 올라오므로 그 빈틈을 메운다. 대신 광고 글이 섞이고 주소가
정확하지 않아, 인허가 목록과는 따로 둔다.
"""

import json
import os
import sys
import time
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
TOPICS = ["신상카페", "가오픈", "오픈 카페", "신상 맛집"]

# 광고·홍보 글에 흔한 말. 걸리면 뺀다.
SPAM = ["체험단", "협찬", "원고료", "소정의", "제공받", "광고", "공동구매", "쿠폰"]


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
    posts = {}
    dropped_mine = dropped_spam = dropped_old = 0

    queries = [f"{area} {topic}" for area in AREAS for topic in TOPICS[:2]]
    queries += [f"서울 {topic}" for topic in TOPICS]

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

            posts[link] = {
                "title": title,
                "description": desc,
                "link": link,
                "blogger": naver.clean_text(item.get("bloggername")),
                "bloggerLink": item.get("bloggerlink") or "",
                "date": posted.isoformat(),
                "area": query.split()[0],
            }
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

    print(f"검색어 {len(queries)}개 → 글 {len(items)}건")
    print(f"  내 글 제외 {dropped_mine} / 광고 의심 {dropped_spam} / 기간 밖 {dropped_old}")


if __name__ == "__main__":
    main()
