// 단톡 정리함 링크 미리보기 서버 (Cloudflare Workers, 무료)
//
// 브라우저는 남의 사이트 페이지를 직접 읽을 수 없다(CORS). 그래서 인스타·네이버·뉴스 같은
// 링크의 제목과 대표 사진을 가져오려면 중간에서 대신 읽어 줄 곳이 필요하다.
// 이 서버는 ?url= 로 받은 주소를 열어 제목·설명·대표 사진·사이트 이름만 골라 돌려준다.
// 페이지 본문은 돌려주지 않는다. 대화 내용은 여기로 오지 않는다 — 링크 주소만 온다.
//
// 만드는 법은 talk/README.md 의 '링크 미리보기 서버' 절에 있다.

// 이 주소에서 부를 때만 응답한다. 남이 공짜 프록시로 쓰지 못하게 막는다.
const ALLOWED = [
  "https://w37389952.github.io",
  /^http:\/\/localhost(:\d+)?$/,
];

export default {
  async fetch(request) {
    const origin = request.headers.get("Origin") || "";
    const ok = ALLOWED.some(a => (typeof a === "string" ? a === origin : a.test(origin)));
    const cors = ok ? { "Access-Control-Allow-Origin": origin, "Vary": "Origin" } : {};
    if (!ok) return json({ error: "origin" }, cors, 403);

    const target = new URL(request.url).searchParams.get("url") || "";
    if (!/^https?:\/\//i.test(target)) return json({ error: "url" }, cors, 400);

    try {
      const res = await fetch(target, {
        redirect: "follow",
        headers: {
          // 일부 사이트는 브라우저처럼 보여야 미리보기 태그를 내준다
          "User-Agent": "Mozilla/5.0 (compatible; TalkPreview/1.0; +link preview)",
          "Accept": "text/html,application/xhtml+xml",
          "Accept-Language": "ko,en;q=0.8",
        },
        cf: { cacheTtl: 86400, cacheEverything: true },
      });
      const type = res.headers.get("content-type") || "";
      if (!type.includes("html")) return json({}, cors, 200, 86400);
      // 머리말만 있으면 된다. 큰 페이지를 통째로 읽지 않는다.
      const html = (await res.text()).slice(0, 400000);
      return json(parse(html, res.url || target), cors, 200, 86400);
    } catch (_) {
      return json({}, cors, 200, 3600);
    }
  },
};

function meta(html, key) {
  // property="og:title" content="…" 와 content="…" property="og:title" 두 순서를 다 받는다
  const k = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const a = new RegExp(`<meta[^>]+(?:property|name)\\s*=\\s*["']${k}["'][^>]*content\\s*=\\s*["']([^"']*)["']`, "i");
  const b = new RegExp(`<meta[^>]+content\\s*=\\s*["']([^"']*)["'][^>]*(?:property|name)\\s*=\\s*["']${k}["']`, "i");
  const m = html.match(a) || html.match(b);
  return m ? decode(m[1]).trim() : "";
}

function parse(html, base) {
  const titleTag = (html.match(/<title[^>]*>([^<]*)<\/title>/i) || [])[1] || "";
  const title = meta(html, "og:title") || meta(html, "twitter:title") || decode(titleTag).trim();
  const description = meta(html, "og:description") || meta(html, "twitter:description") || meta(html, "description");
  let image = meta(html, "og:image") || meta(html, "og:image:url") || meta(html, "twitter:image");
  try { image = image ? new URL(image, base).href : ""; } catch (_) { image = ""; }
  if (image && !image.startsWith("https://")) image = "";   // http 사진은 화면에서 막힌다
  let site = meta(html, "og:site_name");
  if (!site) { try { site = new URL(base).hostname.replace(/^www\./, ""); } catch (_) {} }
  return {
    title: title.slice(0, 200),
    description: description.slice(0, 300),
    image,
    site: (site || "").slice(0, 60),
  };
}

function decode(s) {
  return s
    .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)))
    .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(Number(d)))
    .replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'")
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
}

function json(obj, cors, status = 200, maxAge = 0) {
  const headers = { ...cors, "Content-Type": "application/json; charset=utf-8" };
  if (maxAge) headers["Cache-Control"] = `public, max-age=${maxAge}`;
  return new Response(JSON.stringify(obj), { status, headers });
}
