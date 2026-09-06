"""내 글 몇 편을 예시로 담아 둔다. 말투를 흉내 내게 하려는 것이다.

브라우저는 네이버를 직접 읽을 수 없다(CORS). 그래서 밤에 미리 받아 둔다.

담기는 것은 이미 공개된 내 블로그 글이고, 저장소도 공개이므로 새로 드러나는
정보는 없다. 그래도 원치 않으면 저장소 변수 STYLE_SAMPLES 를 0 으로 두면
이 단계가 통째로 건너뛴다.
"""

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

BLOG_ID = os.environ.get("MY_BLOG_IDS", "haranalice").split(",")[0].strip()
HOW_MANY = int(os.environ.get("STYLE_SAMPLE_COUNT", "3"))
MAX_CHARS = int(os.environ.get("STYLE_SAMPLE_CHARS", "1800"))

# 협찬·초대 글은 말투가 평소와 다르다. 흉내 낼 본보기로 삼으면 안 된다.
SPONSORED = [
    "협찬", "체험단", "원고료", "소정의", "제공받", "무료로 제공", "서포터즈",
    "초대받아", "초대를 받아", "초청", "지원받아", "대가를 받", "광고",
]
# 앞쪽에서 넉넉히 받아 협찬 글을 걸러낸 뒤 필요한 개수만 남긴다.
LOOK_BACK = int(os.environ.get("STYLE_LOOK_BACK", "12"))

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://m.search.naver.com/",
}


def fetch(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=25) as resp:
        return resp.read().decode("utf-8", "replace")


def recent(limit):
    xml = fetch(f"https://rss.blog.naver.com/{BLOG_ID}.xml")
    out = []
    for block in re.findall(r"(?s)<item>(.*?)</item>", xml)[:limit]:
        title = re.search(r"(?s)<title><!\[CDATA\[(.*?)\]\]></title>", block)
        link = re.search(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", block)
        if not (title and link):
            continue
        found = re.search(rf"{BLOG_ID}/(\d+)", link.group(1))
        if found:
            out.append((title.group(1).strip(), found.group(1)))
    return out


def body_of(log_no):
    """글 본문을 글자만 남겨 뽑는다."""
    html = fetch(f"https://m.blog.naver.com/{BLOG_ID}/{log_no}", HEADERS)
    body = re.search(r"(?s)se-main-container(.*)", html)
    if not body:
        return ""
    text = re.sub(r"(?s)<(script|style).*?</\1>", " ", body.group(1))
    text = re.sub(r"<[^>]+>", " ", text)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    return re.sub(r"\s+", " ", text).strip()


def main():
    if os.environ.get("STYLE_SAMPLES", "1") == "0":
        print("STYLE_SAMPLES=0 이므로 예시를 담지 않습니다.")
        return

    try:
        posts = recent(LOOK_BACK)
    except Exception as exc:
        print(f"RSS를 읽지 못했습니다: {exc}", file=sys.stderr)
        return

    samples = []
    skipped = 0
    for title, log_no in posts:
        if len(samples) >= HOW_MANY:
            break
        try:
            text = body_of(log_no)
        except Exception as exc:
            print(f"  {log_no} 건너뜀: {exc}", file=sys.stderr)
            continue
        if len(text) < 400:
            continue

        hit = next((w for w in SPONSORED if w in title or w in text), None)
        if hit:
            skipped += 1
            print(f"  건너뜀(협찬/초대 '{hit}'): {title[:36]}")
            time.sleep(0.4)
            continue

        samples.append({"title": title, "body": text[:MAX_CHARS]})
        print(f"  담음: {title[:40]} ({len(text)}자 중 앞 {MAX_CHARS}자)")
        time.sleep(0.6)

    if skipped:
        print(f"  협찬·초대로 보이는 글 {skipped}편을 뺐습니다.")

    if not samples:
        print("담을 글이 없어 파일을 건드리지 않습니다.", file=sys.stderr)
        return

    DATA.mkdir(exist_ok=True)
    (DATA / "style.json").write_text(
        json.dumps({
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "blogId": BLOG_ID,
            "note": "말투를 흉내 내는 데 쓰는 내 글 예시. 이미 공개된 글이다.",
            "samples": samples,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"글 {len(samples)}편을 예시로 담았습니다.")


if __name__ == "__main__":
    main()
