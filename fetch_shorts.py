"""
YouTube Shorts 트렌드 수집 — 다중 소스 (GitHub Actions 전용)
탭1: YouTube Data API v3
탭2: yt-dlp 트렌딩/해시태그/검색 + playboard.co 크롤링
"""

import json, os, re, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST          = timezone(timedelta(hours=9))
API_KEY      = os.environ.get("YOUTUBE_API_KEY", "")
BASE         = Path(__file__).parent
VIDEOS_API   = BASE / "videos_api.json"
VIDEOS_CRAWL = BASE / "videos_crawl.json"
INDEX_HTML   = BASE / "index.html"
MAX_NEW      = 20

# ── API 검색어 ──────────────────────────────────────────
API_QUERIES = [
    "dance shorts no lyrics background music",
    "dance challenge couple shorts bgm",
    "solo dance shorts trending music",
    "couple moment shorts viral bgm",
    "1 person dance shorts background music only",
]

# ── 크롤링 소스 정의 (이름, 타입, URL/쿼리, 추가 ydl_opts) ──
CRAWL_SOURCES = [
    # YouTube 트렌딩 Shorts — 지역별
    ("트렌딩 글로벌", "ytdlp",
     "https://www.youtube.com/feed/trending?bp=4gIKGgh5dHNhX3Ntaw%3D%3D", {}),
    ("트렌딩 KR", "ytdlp",
     "https://www.youtube.com/feed/trending?bp=4gIKGgh5dHNhX3Ntaw%3D%3D",
     {"geo_bypass_country": "KR"}),
    ("트렌딩 US", "ytdlp",
     "https://www.youtube.com/feed/trending?bp=4gIKGgh5dHNhX3Ntaw%3D%3D",
     {"geo_bypass_country": "US"}),
    ("트렌딩 JP", "ytdlp",
     "https://www.youtube.com/feed/trending?bp=4gIKGgh5dHNhX3Ntaw%3D%3D",
     {"geo_bypass_country": "JP"}),
    # YouTube 해시태그 페이지
    ("#shorts",          "ytdlp", "https://www.youtube.com/hashtag/shorts",         {}),
    ("#dancechallenge",  "ytdlp", "https://www.youtube.com/hashtag/dancechallenge",  {}),
    ("#댄스",            "ytdlp", "https://www.youtube.com/hashtag/댄스",            {}),
    ("#bgm댄스",         "ytdlp", "https://www.youtube.com/hashtag/bgm댄스",         {}),
    # YouTube 검색 (yt-dlp)
    ("댄스 검색",   "search", "ytsearchdate50:dance shorts viral bgm #shorts 2025",  {}),
    ("K-POP 검색",  "search", "ytsearchdate30:kpop dance bgm shorts #shorts",        {}),
    ("커플 댄스",   "search", "ytsearchdate30:couple dance #shorts music bgm",        {}),
    ("솔로 댄스",   "search", "ytsearchdate30:solo dance #shorts background music",   {}),
    ("한국 검색",   "search", "ytsearchdate30:#shorts 댄스 챌린지",                   {}),
    ("일본 검색",   "search", "ytsearchdate30:ショートダンス #shorts",                {}),
    # 외부 사이트 크롤링
    ("playboard.co",  "playboard", "https://playboard.co/chart/youtube-shorts-trending-chart", {}),
    ("kworb 차트",    "kworb",     "https://kworb.net/youtube/videos.html", {}),
]

EXCLUDE_KW = {
    "tutorial", "recipe", "cooking", "요리", "vlog", "브이로그",
    "자막", "subtitle", "caption", "lyrics", "가사", "review", "리뷰",
    "unboxing", "언박싱", "news", "뉴스", "asmr", "mukbang", "먹방",
    "gaming", "게임", "prank", "compilation", "모음", "how to", "howto",
}

YT_ID_RE = re.compile(r'["\'/](?:shorts/|watch\?v=)([A-Za-z0-9_-]{11})')
DUR_RE   = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')


# ── 유틸 ────────────────────────────────────────────────
def iso_to_sec(iso: str) -> int:
    m = DUR_RE.match(iso or "")
    if not m:
        return 9999
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s

def fmt_views(n: int) -> str:
    if n >= 100_000_000:
        return f"{n/100_000_000:.1f}억"
    if n >= 10_000:
        return f"{n/10_000:.1f}만"
    return f"{n:,}" if n else "—"

def now_kst_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")

def is_excluded(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in EXCLUDE_KW)

def load_json(path: Path) -> dict:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"last_updated": "", "videos": []}

def save_json(path: Path, data: dict) -> None:
    data["last_updated"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def make_entry(vid_id: str, title: str, view_count: int,
               duration_sec: int, source: str) -> dict:
    return {
        "id":           vid_id,
        "title":        title,
        "thumbnail":    f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg",
        "url":          f"https://www.youtube.com/shorts/{vid_id}",
        "added_date":   now_kst_str(),
        "view_count":   view_count,
        "duration_sec": duration_sec,
        "source":       source,
    }


# ── Tab 1: YouTube Data API ──────────────────────────────
def fetch_api(existing_ids: set) -> list[dict]:
    if not API_KEY:
        print("[API] YOUTUBE_API_KEY 없음 — 스킵")
        return []
    try:
        from googleapiclient.discovery import build
    except ImportError:
        print("[API] google-api-python-client 미설치")
        return []

    youtube = build("youtube", "v3", developerKey=API_KEY)
    since   = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
    new, seen = [], set(existing_ids)

    for q in API_QUERIES:
        print(f"  [API] 검색: {q!r}")
        try:
            resp = youtube.search().list(
                q=q, part="id", type="video", videoDuration="short",
                order="viewCount", publishedAfter=since,
                regionCode="KR", maxResults=25,
            ).execute()
            fresh = [i["id"]["videoId"] for i in resp.get("items", [])
                     if i["id"]["videoId"] not in seen]
            if not fresh:
                continue
            det = youtube.videos().list(
                part="snippet,contentDetails,statistics",
                id=",".join(fresh),
            ).execute()
            for item in det.get("items", []):
                secs = iso_to_sec(item["contentDetails"]["duration"])
                if secs > 90:
                    continue
                vid  = item["id"]
                title = item["snippet"].get("title", "")
                if is_excluded(title):
                    continue
                vc = int(item.get("statistics", {}).get("viewCount", 0))
                seen.add(vid)
                new.append(make_entry(vid, title, vc, secs, "YouTube API"))
        except Exception as e:
            print(f"  [API] 오류: {e}")
        if len(new) >= MAX_NEW:
            break

    new.sort(key=lambda v: v["view_count"], reverse=True)
    print(f"[API] 신규 {len(new[:MAX_NEW])}개")
    return new[:MAX_NEW]


# ── Tab 2: yt-dlp 추출 ──────────────────────────────────
def _ydlp_extract(url: str, extra_opts: dict, source_name: str,
                  seen: set) -> list[dict]:
    try:
        import yt_dlp
    except ImportError:
        return []

    opts = {
        "quiet":        True,
        "no_warnings":  True,
        "extract_flat": True,
        "playlistend":  40,
        "ignoreerrors": True,
        **extra_opts,
    }
    results = []
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False) or {}
            for e in info.get("entries", []):
                if not e:
                    continue
                vid_id = e.get("id", "")
                if not vid_id or vid_id in seen:
                    continue
                dur = e.get("duration") or 0
                if dur and dur > 90:
                    continue
                title = e.get("title", "")
                if is_excluded(title):
                    continue
                seen.add(vid_id)
                results.append(make_entry(
                    vid_id, title,
                    e.get("view_count", 0) or 0,
                    int(dur), source_name,
                ))
    except Exception as ex:
        print(f"  [yt-dlp] {source_name} 오류: {ex}")
    return results


# ── Tab 2: 웹 사이트 크롤링 ──────────────────────────────
def _scrape_site(url: str, source_name: str, seen: set) -> list[dict]:
    """requests + regex 로 YouTube 영상 ID 추출"""
    try:
        import requests as req
    except ImportError:
        print(f"  [{source_name}] requests 미설치")
        return []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    }
    try:
        r = req.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        ids_found = dict.fromkeys(YT_ID_RE.findall(r.text))  # 순서 보존 dedup
    except Exception as ex:
        print(f"  [{source_name}] 접속 오류: {ex}")
        return []

    results = []
    for vid_id in ids_found:
        if vid_id in seen or len(vid_id) != 11:
            continue
        # noembed 로 제목 조회 (간단, API 키 불필요)
        title, vc = _noembed(vid_id)
        if title and is_excluded(title):
            continue
        seen.add(vid_id)
        results.append(make_entry(vid_id, title, vc, 0, source_name))
        if len(results) >= 15:
            break

    return results


def _noembed(vid_id: str) -> tuple[str, int]:
    """noembed.com 으로 제목 조회 (API 키 불필요)"""
    try:
        import requests as req
        r = req.get(
            f"https://noembed.com/embed?url=https://www.youtube.com/watch?v={vid_id}",
            timeout=6,
        )
        if r.ok:
            d = r.json()
            return d.get("title", ""), 0
    except Exception:
        pass
    return "", 0


# ── Tab 2: 전체 크롤링 ───────────────────────────────────
def fetch_crawl(existing_ids: set) -> list[dict]:
    seen   = set(existing_ids)
    all_new: list[dict] = []

    for name, src_type, url_or_q, extra in CRAWL_SOURCES:
        print(f"  [크롤] {name} ({src_type})")
        before = len(all_new)

        if src_type in ("ytdlp", "search"):
            chunk = _ydlp_extract(url_or_q, extra, name, seen)
        elif src_type in ("playboard", "kworb"):
            chunk = _scrape_site(url_or_q, name, seen)
        else:
            chunk = []

        all_new.extend(chunk)
        print(f"         → {len(all_new) - before}개 수집")

    # 조회수 정렬 → 상위 MAX_NEW
    all_new.sort(key=lambda v: v["view_count"], reverse=True)
    print(f"[크롤] 총 신규 {len(all_new[:MAX_NEW])}개")
    return all_new[:MAX_NEW]


# ── HTML 생성 ────────────────────────────────────────────
SOURCE_COLORS = {
    "YouTube API":      "#e63946",
    "트렌딩 글로벌":    "#457b9d",
    "트렌딩 KR":        "#e07a5f",
    "트렌딩 US":        "#3d405b",
    "트렌딩 JP":        "#81b29a",
    "#shorts":          "#f2cc8f",
    "#dancechallenge":  "#f4a261",
    "#댄스":            "#e76f51",
    "#bgm댄스":         "#2a9d8f",
    "댄스 검색":        "#264653",
    "K-POP 검색":       "#8338ec",
    "커플 댄스":        "#fb5607",
    "솔로 댄스":        "#ff006e",
    "한국 검색":        "#ffbe0b",
    "일본 검색":        "#3a86ff",
    "playboard.co":     "#06d6a0",
    "kworb 차트":       "#118ab2",
}

def _badge(source: str) -> str:
    color = SOURCE_COLORS.get(source, "#555")
    return (f'<span class="badge" style="background:{color}">'
            f'{source}</span>')

def _card(v: dict, show_source: bool = False) -> str:
    views = fmt_views(v.get("view_count", 0))
    date  = v.get("added_date", "")
    title = (v.get("title", "") or v["id"]).replace("<", "&lt;").replace(">", "&gt;")
    badge = _badge(v.get("source", "")) if show_source else ""
    return f"""<a class="card" href="{v['url']}" target="_blank" rel="noopener">
      <div class="thumb-wrap">
        <img loading="lazy" src="{v['thumbnail']}" alt="{title}">
        <span class="play-icon">&#9654;</span>
        {badge}
      </div>
      <div class="info">
        <p class="title">{title or '(제목 없음)'}</p>
        <p class="meta"><span>&#128065; {views}</span><span>&#128197; {date}</span></p>
      </div>
    </a>"""

def _grid(videos: list[dict], show_source: bool = False) -> str:
    if not videos:
        return """<div class="empty">
      <div style="font-size:3rem">&#127916;</div>
      <p>첫 업데이트를 기다리는 중입니다.</p>
      <p style="margin-top:.3rem;font-size:.8rem;color:#888">
        GitHub Actions가 매일 17:00 KST에 자동으로 채웁니다.</p>
    </div>"""
    return ("<div class='grid'>"
            + "".join(_card(v, show_source) for v in videos)
            + "</div>")

def regenerate_html(api_data: dict, crawl_data: dict) -> None:
    year       = datetime.now(KST).year
    api_last   = api_data.get("last_updated", "—")
    crawl_last = crawl_data.get("last_updated", "—")
    last       = api_last if api_last != "—" else crawl_last

    api_cnt   = len(api_data["videos"])
    crawl_cnt = len(crawl_data["videos"])

    # 크롤링 소스 목록 (현재 데이터에 있는 것만)
    sources_used = sorted({v.get("source", "") for v in crawl_data["videos"]} - {""})
    src_list_html = "".join(
        f'<span class="src-chip" style="background:{SOURCE_COLORS.get(s,"#555")}">{s}</span>'
        for s in sources_used
    )

    html = f"""<!DOCTYPE html>
<html lang="ko" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>인기 YouTube Shorts</title>
  <style>
    /* ── CSS 변수 (다크/라이트) ─────────────── */
    :root[data-theme="dark"] {{
      --bg:        #0f0f0f;
      --bg2:       #1a1a1a;
      --bg3:       #1e1e2e;
      --border:    #2a2a2a;
      --text:      #e8e8e8;
      --text2:     #aaa;
      --text3:     #888;
      --header-bg: linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);
      --tab-bg:    #1e1e2e;
      --tab-text:  #999;
      --card-hover-shadow: rgba(230,57,70,.25);
      --footer-border: #1e1e1e;
      --toggle-bg: #2a2a3e;
      --toggle-icon: "☀️";
    }}
    :root[data-theme="light"] {{
      --bg:        #f5f5f5;
      --bg2:       #ffffff;
      --bg3:       #e8e8f0;
      --border:    #ddd;
      --text:      #111;
      --text2:     #444;
      --text3:     #666;
      --header-bg: linear-gradient(135deg,#2c3e7a,#3b5fc0,#1a73e8);
      --tab-bg:    #e0e0f0;
      --tab-text:  #444;
      --card-hover-shadow: rgba(230,57,70,.18);
      --footer-border: #ddd;
      --toggle-bg: #d0d8f0;
      --toggle-icon: "🌙";
    }}

    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: 'Segoe UI','Apple SD Gothic Neo',sans-serif;
      min-height: 100vh;
      transition: background .25s, color .25s;
    }}

    /* ── 헤더 ── */
    header {{
      background: var(--header-bg);
      padding: 1.6rem 1rem 1.2rem;
      text-align: center;
      border-bottom: 2px solid #e63946;
      position: relative;
    }}
    header h1 {{
      font-size: clamp(1.3rem,4vw,2rem);
      font-weight: 800;
      color: #fff;
    }}
    header h1 span {{ color: #f4a261; }}
    .subtitle {{ margin-top: .4rem; font-size: .8rem; color: rgba(255,255,255,.7); }}
    .update-badge {{
      display: inline-block;
      margin-top: .7rem;
      padding: .22rem .75rem;
      background: #e63946;
      border-radius: 20px;
      font-size: .73rem;
      color: #fff;
      font-weight: 600;
    }}

    /* ── 다크/라이트 토글 ── */
    .theme-toggle {{
      position: absolute;
      top: 1rem;
      right: 1rem;
      background: var(--toggle-bg);
      border: none;
      border-radius: 24px;
      padding: .35rem .8rem;
      font-size: .85rem;
      cursor: pointer;
      color: #fff;
      display: flex;
      align-items: center;
      gap: .35rem;
      transition: background .25s;
      font-weight: 600;
      box-shadow: 0 2px 8px rgba(0,0,0,.3);
    }}
    .theme-toggle:hover {{ opacity: .85; }}

    /* ── 조건 칩 ── */
    .conditions {{
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: .35rem;
      padding: .75rem 1rem;
      max-width: 960px;
      margin: 0 auto;
    }}
    .conditions span {{
      background: var(--bg3);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: .25rem .7rem;
      font-size: .72rem;
      color: var(--text2);
    }}

    /* ── 탭 바 ── */
    .tab-bar {{
      display: flex;
      gap: .4rem;
      padding: .9rem 1rem 0;
      max-width: 1200px;
      margin: 0 auto;
      border-bottom: 2px solid var(--border);
    }}
    .tab-btn {{
      padding: .5rem 1.3rem;
      border: none;
      border-radius: 8px 8px 0 0;
      cursor: pointer;
      font-size: .86rem;
      font-weight: 600;
      background: var(--tab-bg);
      color: var(--tab-text);
      transition: all .2s;
      position: relative;
      bottom: -2px;
    }}
    .tab-btn:hover {{ color: var(--text); }}
    .tab-btn.active {{
      background: #e63946;
      color: #fff;
      border-bottom: 2px solid #e63946;
    }}
    .cnt-badge {{
      display: inline-block;
      background: rgba(255,255,255,.25);
      border-radius: 10px;
      padding: 0 .4rem;
      font-size: .7rem;
      margin-left: .3rem;
    }}
    .tab-meta {{
      font-size: .7rem;
      color: var(--text3);
      padding: .4rem 1rem .1rem;
      max-width: 1200px;
      margin: 0 auto;
    }}
    .tab-content {{ display: none; }}
    .tab-content.active {{ display: block; }}

    /* ── 소스 칩 목록 ── */
    .src-chips {{
      display: flex;
      flex-wrap: wrap;
      gap: .3rem;
      padding: .4rem 1rem .6rem;
      max-width: 1200px;
      margin: 0 auto;
    }}
    .src-chip {{
      border-radius: 12px;
      padding: .18rem .6rem;
      font-size: .68rem;
      color: #fff;
      font-weight: 600;
    }}

    /* ── 카드 그리드 ── */
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
      gap: .9rem;
      padding: .9rem 1rem;
      max-width: 1200px;
      margin: 0 auto;
    }}
    .card {{
      display: block;
      text-decoration: none;
      background: var(--bg2);
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid var(--border);
      transition: transform .2s, border-color .2s, box-shadow .2s;
    }}
    .card:hover {{
      transform: translateY(-4px);
      border-color: #e63946;
      box-shadow: 0 8px 24px var(--card-hover-shadow);
    }}
    .thumb-wrap {{
      position: relative;
      aspect-ratio: 9/16;
      overflow: hidden;
      background: #111;
    }}
    .thumb-wrap img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}
    .play-icon {{
      position: absolute;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 2.2rem;
      color: rgba(255,255,255,.9);
      opacity: 0;
      background: rgba(0,0,0,.3);
      transition: opacity .2s;
    }}
    .card:hover .play-icon {{ opacity: 1; }}
    .badge {{
      position: absolute;
      bottom: .4rem;
      left: .4rem;
      border-radius: 8px;
      padding: .12rem .45rem;
      font-size: .6rem;
      color: #fff;
      font-weight: 700;
      backdrop-filter: blur(2px);
      opacity: .9;
    }}
    .info {{ padding: .55rem .65rem .7rem; }}
    .title {{
      font-size: .8rem;
      font-weight: 600;
      line-height: 1.35;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
      color: var(--text);
    }}
    .meta {{
      display: flex;
      justify-content: space-between;
      margin-top: .4rem;
      font-size: .68rem;
      color: var(--text3);
    }}
    .empty {{
      text-align: center;
      padding: 4rem 1rem;
      color: var(--text3);
    }}
    .empty p {{ margin-top: .5rem; font-size: .88rem; }}

    footer {{
      text-align: center;
      padding: 1.8rem 1rem;
      font-size: .73rem;
      color: var(--text3);
      border-top: 1px solid var(--footer-border);
      margin-top: 1rem;
    }}

    @media (max-width: 480px) {{
      .grid {{ grid-template-columns: repeat(2,1fr); gap: .55rem; padding: .6rem; }}
      .tab-btn {{ padding: .42rem .8rem; font-size: .78rem; }}
      .theme-toggle {{ top: .6rem; right: .6rem; padding: .28rem .6rem; font-size: .78rem; }}
    }}
  </style>
</head>
<body>

<header>
  <button class="theme-toggle" onclick="toggleTheme()" id="themeBtn">
    <span id="themeIcon">☀️</span> <span id="themeLabel">라이트</span>
  </button>
  <h1>&#127916; 인기 <span>YouTube Shorts</span></h1>
  <div class="subtitle">배경음악 · 자막없음 · 1~2명 · 댄스/상황</div>
  <div class="update-badge">마지막 업데이트: {last}</div>
</header>

<div class="conditions">
  <span>&#127925; 배경음악만</span>
  <span>&#128683; 자막 없음</span>
  <span>&#128100; 인물 1~2명</span>
  <span>&#128131; 댄스 / 상황</span>
  <span>&#128200; 매일 17:00 KST 자동 업데이트</span>
</div>

<div class="tab-bar">
  <button class="tab-btn active" onclick="showTab('tab-api',this)">
    &#128273; YouTube API
    <span class="cnt-badge">{api_cnt}</span>
  </button>
  <button class="tab-btn" onclick="showTab('tab-crawl',this)">
    &#127760; 트렌드 크롤링
    <span class="cnt-badge">{crawl_cnt}</span>
  </button>
</div>

<div id="tab-api" class="tab-content active">
  <p class="tab-meta">YouTube Data API v3 &nbsp;·&nbsp; 업데이트: {api_last}</p>
  {_grid(api_data["videos"], show_source=False)}
</div>

<div id="tab-crawl" class="tab-content">
  <p class="tab-meta">
    수집 소스 {len(sources_used)}개 &nbsp;·&nbsp; 업데이트: {crawl_last}
  </p>
  <div class="src-chips">{src_list_html}</div>
  {_grid(crawl_data["videos"], show_source=True)}
</div>

<footer>
  자동 수집 · 매일 17:00 KST · YouTube Shorts 트렌드 기반<br>
  GitHub Actions 완전 자동화 &copy; {year} yclaude
</footer>

<script>
  /* ── 탭 전환 ── */
  function showTab(id, btn) {{
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(id).classList.add('active');
    btn.classList.add('active');
  }}

  /* ── 다크/라이트 토글 ── */
  (function init() {{
    const saved = localStorage.getItem('theme') || 'dark';
    applyTheme(saved);
  }})();

  function toggleTheme() {{
    const curr = document.documentElement.getAttribute('data-theme');
    applyTheme(curr === 'dark' ? 'light' : 'dark');
  }}

  function applyTheme(t) {{
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('theme', t);
    const isDark = t === 'dark';
    document.getElementById('themeIcon').textContent  = isDark ? '☀️' : '🌙';
    document.getElementById('themeLabel').textContent = isDark ? '라이트' : '다크';
  }}
</script>

</body>
</html>
"""
    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"index.html 완료 (API {api_cnt}개 + 크롤 {crawl_cnt}개)")


# ── 메인 ─────────────────────────────────────────────────
def main():
    print("=== YouTube Shorts 수집 시작 ===")

    api_data   = load_json(VIDEOS_API)
    crawl_data = load_json(VIDEOS_CRAWL)

    # Tab 1: YouTube API
    new_api = fetch_api({v["id"] for v in api_data["videos"]})
    if new_api:
        api_data["videos"] = new_api + api_data["videos"]
    save_json(VIDEOS_API, api_data)

    # Tab 2: 다중 소스 크롤링
    new_crawl = fetch_crawl({v["id"] for v in crawl_data["videos"]})
    if new_crawl:
        crawl_data["videos"] = new_crawl + crawl_data["videos"]
    save_json(VIDEOS_CRAWL, crawl_data)

    # HTML 재생성
    regenerate_html(api_data, crawl_data)
    print("=== 완료 ===")


if __name__ == "__main__":
    main()
