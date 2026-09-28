"""내 글 몇 편을 예시로 담아 둔다. 말투를 흉내 내게 하려는 것이다.

브라우저는 네이버를 직접 읽을 수 없다(CORS). 그래서 밤에 미리 받아 둔다.

담기는 것은 이미 공개된 내 블로그 글이고, 저장소도 공개이므로 새로 드러나는
정보는 없다. 그래도 원치 않으면 저장소 변수 STYLE_SAMPLES 를 0 으로 두면
이 단계가 통째로 건너뛴다.
"""

import html as htmllib
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
# 한 편을 통째로 보여 준다. 1800자로 자르던 때는 정보 칸과 도입부만 담기고
# 내부 묘사·메뉴·마무리 추천 문장이 잘려, 정작 본문의 결을 못 보여 줬다.
# 내 글은 2천 자 안팎이다.
MAX_CHARS = int(os.environ.get("STYLE_SAMPLE_CHARS", "4000"))

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
    """글 본문을 줄 모양 그대로 뽑는다.

    전에는 공백을 모두 한 칸으로 뭉쳐 글 한 편이 한 줄이 되었다. 그런데 내 글의
    결은 줄 모양에 있다 — 한 줄에 한 구절, 줄마다 빈 줄, 가운데 정렬. 약수역
    엔프트커피 글이 2,133자에 83줄이다. 그걸 한 덩어리로 보여 주니 모델은
    서너 줄짜리 문단으로 이어 썼고, 사용자가 '여전히 수필 같다'고 했다.
    그래서 문단(<p>) 하나를 한 줄로 살리고, 빈 문단은 빈 줄로 둔다.
    """
    html = fetch(f"https://m.blog.naver.com/{BLOG_ID}/{log_no}", HEADERS)
    body = re.search(r"(?s)se-main-container(.*)", html)
    if not body:
        return ""
    text = re.sub(r"(?s)<(script|style).*?</\1>", " ", body.group(1))
    text = re.sub(r"(?i)</p>|<br\s*/?>", "\n", text)
    text = re.sub(r'(?i)<div class="se-component ', '\n<div class="', text)
    text = re.sub(r"<[^>]+>", "", text)
    text = htmllib.unescape(text).replace("​", "")
    # 'se-main-container">'에서 잘랐으므로 여는 꺾쇠 찌꺼기가 맨 앞에 남는다.
    text = text.lstrip()
    if text.startswith('">'):
        text = text[2:]

    lines = []
    blank = False
    for raw in text.split("\n"):
        line = re.sub(r"[ \t\r\xa0]+", " ", raw).strip()
        # 본문 뒤에 붙는 글 정보(JSON)부터는 글이 아니다.
        if line.startswith('{"title"'):
            break
        # 지도 칸의 버튼 글자와 여는 꺾쇠 찌꺼기는 버린다.
        if not line or line in ('">', "이 블로그의 체크인", "이 장소의 다른 글"):
            blank = True
            continue
        if lines and blank:
            lines.append("")
        blank = False
        lines.append(line)
    return "\n".join(lines).strip()


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

        # 자를 때는 줄 끝에서 자른다. 줄 가운데서 끊으면 그 줄이 말이 안 된다.
        cut = text if len(text) <= MAX_CHARS else text[:MAX_CHARS].rsplit("\n", 1)[0]
        samples.append({"title": title, "body": cut})
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
