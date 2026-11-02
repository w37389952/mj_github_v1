#!/usr/bin/env python3
"""밥상 치트키: 오늘(KST) 날짜에 해당하는 글을 쓰레드에 올린다.
사용: python3 post_today.py [--day N] [--dry-run]
토큰은 환경 변수 THREADS_ACCESS_TOKEN 에서만 읽고, 절대 출력하지 않는다."""
import json, os, sys, time, datetime, urllib.request, urllib.parse
BASE = "https://graph.threads.net/v1.0"
RAW = "https://raw.githubusercontent.com/w37389952/mj_github_v1/claude/project-thread-7hozbj/threads-food/"
TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "")

def api(method, path, **params):
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    url = f"{BASE}/{path}"
    if method == "GET":
        req = urllib.request.Request(url + "?" + data.decode())
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace").replace(TOKEN, "***")
        raise SystemExit(f"API 오류 {e.code} {path}: {body}")

def wait_ready(cid):
    for _ in range(30):
        s = api("GET", cid, fields="status,error_message")
        if s.get("status") == "FINISHED":
            return
        if s.get("status") in ("ERROR", "EXPIRED"):
            raise SystemExit(f"컨테이너 실패: {s}")
        time.sleep(5)
    raise SystemExit("컨테이너 준비 시간 초과")

def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    week = "week1"
    posts = json.load(open(os.path.join(os.path.dirname(__file__), week, "posts.json")))
    if "--day" in args:
        day = int(args[args.index("--day") + 1])
        post = next(p for p in posts if p["day"] == day)
    else:
        today = (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).date().isoformat()
        post = next((p for p in posts if p["date"] == today), None)
        if not post:
            print(f"오늘({today}) 올릴 글 없음"); return
    if not TOKEN:
        raise SystemExit("THREADS_ACCESS_TOKEN 없음")
    me = api("GET", "me", fields="id,username")
    # 중복 방지: 최근 글 중 첫 줄이 같은 글이 있으면 건너뜀
    first = post["text"].splitlines()[0]
    recent = api("GET", "me/threads", fields="id,text,permalink", limit=10).get("data", [])
    for r in recent:
        if (r.get("text") or "").splitlines()[:1] == [first]:
            print(f"이미 올라간 글이라 건너뜀: {r.get('permalink')}"); return
    urls = [RAW + f"{week}/{n}" for n in post["images"]]
    print(f"계정 @{me['username']} / {post['day']}일차 / 이미지 {len(urls)}장")
    if dry:
        print("dry-run: 업로드 안 함"); return
    if len(urls) == 1:
        c = api("POST", "me/threads", media_type="IMAGE", image_url=urls[0], text=post["text"])["id"]
    else:
        kids = []
        for u in urls:
            k = api("POST", "me/threads", media_type="IMAGE", image_url=u, is_carousel_item="true")["id"]
            wait_ready(k); kids.append(k)
        c = api("POST", "me/threads", media_type="CAROUSEL", children=",".join(kids), text=post["text"])["id"]
    wait_ready(c)
    pub = api("POST", "me/threads_publish", creation_id=c)
    info = api("GET", pub["id"], fields="permalink")
    print(f"게시 완료: {info.get('permalink')}")

if __name__ == "__main__":
    main()
