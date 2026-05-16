"""
YouTube Shorts 트렌드 수집 (API + yt-dlp 크롤링 통합)
탭1: YouTube Data API v3
탭2: yt-dlp 트렌딩/검색 크롤링 (API 키 불필요)
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── 상수 ────────────────────────────────────────────────
API_KEY      = os.environ.get("YOUTUBE_API_KEY", "")
BASE_DIR     = Path(__file__).parent
VIDEOS_API   = BASE_DIR / "videos_api.json"
VIDEOS_CRAWL = BASE_DIR / "videos_crawl.json"
INDEX_HTML   = BASE_DIR / "index.html"

KST = timezone(timedelta(hours=9))
MAX_NEW = 20   # 회당 최대 신규 영상 수

# API 검색어 (배경음악·댄스·인물 1~2명 조건에 맞는 키워드)
API_QUERIES = [
    "dance shorts no lyrics",
    "dance challenge couple shorts",
    "solo dance shorts trending",
    "couple moment shorts viral",
    "background music dance shorts",
    "1 person dance shorts music",
]

# 크롤링 yt-dlp 검색어
CRAWL_QUERIES = [
    "ytsearchdate30:dance shorts #shorts viral",
    "ytsearchdate30:#shorts 댄스 챌린지",
    "ytsearchdate30:couple dance shorts no caption 2025",
    "ytsearchdate30:solo dance challenge #shorts music",
    "ytsearchdate30:dance trend shorts bgm",
]

# 크롤링 제외 키워드 (자막·요리·리뷰 등)
EXCLUDE_KW = {
    "tutorial", "recipe", "cooking", "요리", "vlog", "브이로그",
    "자막", "subtitle", "caption", "lyrics", "가사",
    "review", "리뷰", "unboxing", "언박싱", "news", "뉴스",
    "asmr", "mukbang", "먹방", "gaming", "게임", "prank",
}

# ── 유틸 ────────────────────────────────────────────────
_DUR_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")

def iso_to_sec(iso: str) -> int:
    m = _DUR_RE.match(iso or "")
    if not m:
        return 9999
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s

def fmt_views(n: int) -> str:
    if n >= 100_000_000:
        return f"{n/100_000_000:.1f}억"
    if n >= 10_000:
        return f"{n/10_000:.1f}만"
    return f"{n:,}"

def now_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")

def load_json(path: Path) -> dict:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"last_updated": "", "videos": []}

def save_json(path: Path, data: dict) -> None:
    data["last_updated"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def exclude_by_title(title: str) -> bool:
    tl = title.lower()
    return any(kw in tl for kw in EXCLUDE_KW)


# ── Tab 1: YouTube Data API ──────────────────────────────
def api_search_ids(youtube, query: str, since: str) -> list[str]:
    resp = youtube.search().list(
        q=query,
        part="id",
        type="video",
        videoDuration="short",
        order="viewCount",
        publishedAfter=since,
        regionCode="KR",
        relevanceLanguage="ko",
        maxResults=25,
    ).execute()
    return [item["id"]["videoId"] for item in resp.get("items", [])]

def api_video_details(youtube, ids: list[str]) -> list[dict]:
    if not ids:
        return []
    resp = youtube.videos().list(
        part="snippet,contentDetails,statistics",
        id=",".join(ids),
    ).execute()
    out = []
    for item in resp.get("items", []):
        secs = iso_to_sec(item["contentDetails"]["duration"])
        if secs > 90:
            continue
        vid_id  = item["id"]
        snippet = item["snippet"]
        stats   = item.get("statistics", {})
        out.append({
            "id":           vid_id,
            "title":        snippet.get("title", ""),
            "thumbnail":    f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg",
            "url":          f"https://www.youtube.com/shorts/{vid_id}",
            "added_date":   now_kst(),
            "view_count":   int(stats.get("viewCount", 0)),
            "duration_sec": secs,
        })
    return out

def fetch_api(existing_ids: set) -> list[dict]:
    try:
        from googleapiclient.discovery import build
    except ImportError:
        print("google-api-python-client 미설치")
        return []

    youtube = build("youtube", "v3", developerKey=API_KEY)
    since   = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")

    new: list[dict] = []
    seen = set(existing_ids)

    for query in API_QUERIES:
        print(f"[API] 검색: {query!r}")
        cands = api_search_ids(youtube, query, since)
        fresh = [i for i in cands if i not in seen]
        if not fresh:
            continue
        details = api_video_details(youtube, fresh)
        for v in details:
            if exclude_by_title(v["title"]):
                continue
            seen.add(v["id"])
            new.append(v)
        if len(new) >= MAX_NEW:
            break

    new.sort(key=lambda v: v["view_count"], reverse=True)
    new = new[:MAX_NEW]
    print(f"[API] 신규 {len(new)}개")
    return new


# ── Tab 2: yt-dlp 크롤링 ────────────────────────────────
def fetch_crawl(existing_ids: set) -> list[dict]:
    try:
        import yt_dlp
    except ImportError:
        print("yt-dlp 미설치, 크롤링 스킵")
        return []

    ydl_opts = {
        "quiet":        True,
        "no_warnings":  True,
        "extract_flat": True,
        "playlistend":  40,
        "ignoreerrors": True,
    }

    # YouTube Shorts 트렌딩 페이지 (한국) + 검색어
    urls = [
        "https://www.youtube.com/feed/trending?bp=4gIKGgh5dHNhX3Ntaw%3D%3D",
    ] + CRAWL_QUERIES

    new: list[dict] = []
    seen = set(existing_ids)

    for url in urls:
        print(f"[크롤] 수집: {url[:60]}")
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info    = ydl.extract_info(url, download=False)
                entries = (info or {}).get("entries", [])
                for entry in entries:
                    if not entry:
                        continue
                    vid_id = entry.get("id", "")
                    if not vid_id or vid_id in seen:
                        continue
                    dur = entry.get("duration") or 0
                    if dur and dur > 90:
                        continue
                    title = entry.get("title", "")
                    if exclude_by_title(title):
                        continue
                    seen.add(vid_id)
                    new.append({
                        "id":           vid_id,
                        "title":        title,
                        "thumbnail":    f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg",
                        "url":          f"https://www.youtube.com/shorts/{vid_id}",
                        "added_date":   now_kst(),
                        "view_count":   entry.get("view_count", 0) or 0,
                        "duration_sec": int(dur),
                    })
                    if len(new) >= MAX_NEW * 2:
                        break
        except Exception as e:
            print(f"[크롤] 오류: {e}")

    new.sort(key=lambda v: v["view_count"], reverse=True)
    new = new[:MAX_NEW]
    print(f"[크롤] 신규 {len(new)}개")
    return new


# ── HTML 생성 ────────────────────────────────────────────
def build_card(v: dict) -> str:
    views = fmt_views(v.get("view_count", 0))
    date  = v.get("added_date", "")
    title = v.get("title", "").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<a class="card" href="{v['url']}" target="_blank" rel="noopener">
      <div class="thumb-wrap">
        <img loading="lazy" src="{v['thumbnail']}" alt="{title}">
        <span class="play-icon">&#9654;</span>
      </div>
      <div class="info">
        <p class="title">{title}</p>
        <p class="meta">
          <span>&#128065; {views}</span>
          <span>&#128197; {date}</span>
        </p>
      </div>
    </a>"""

def build_grid(videos: list[dict]) -> str:
    if not videos:
        return """<div class="empty">
      <div style="font-size:3rem">&#127916;</div>
      <p>첫 업데이트를 기다리는 중입니다.</p>
      <p>GitHub Actions가 오후 5시에 자동으로 채웁니다.</p>
    </div>"""
    return "<div class='grid'>" + "".join(build_card(v) for v in videos) + "</div>"

def regenerate_html(api_data: dict, crawl_data: dict) -> None:
    api_last   = api_data.get("last_updated", "—")
    crawl_last = crawl_data.get("last_updated", "—")
    last = api_last if api_last != "—" else crawl_last

    api_grid   = build_grid(api_data["videos"])
    crawl_grid = build_grid(crawl_data["videos"])

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>인기 YouTube Shorts</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: #0f0f0f;
      color: #e8e8e8;
      font-family: 'Segoe UI', 'Apple SD Gothic Neo', sans-serif;
      min-height: 100vh;
    }}
    header {{
      background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
      padding: 2rem 1rem 1.5rem;
      text-align: center;
      border-bottom: 2px solid #e63946;
    }}
    header h1 {{
      font-size: clamp(1.4rem, 4vw, 2.2rem);
      font-weight: 800;
      color: #fff;
    }}
    header h1 span {{ color: #e63946; }}
    .subtitle {{ margin-top: 0.5rem; font-size: 0.82rem; color: #aaa; }}
    .update-badge {{
      display: inline-block;
      margin-top: 0.8rem;
      padding: 0.25rem 0.8rem;
      background: #e63946;
      border-radius: 20px;
      font-size: 0.75rem;
      color: #fff;
      font-weight: 600;
    }}
    .conditions {{
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 0.4rem;
      padding: 0.8rem 1rem;
      max-width: 900px;
      margin: 0 auto;
    }}
    .conditions span {{
      background: #1e1e2e;
      border: 1px solid #333;
      border-radius: 20px;
      padding: 0.28rem 0.7rem;
      font-size: 0.73rem;
      color: #ccc;
    }}

    /* ── 탭 ── */
    .tab-bar {{
      display: flex;
      gap: 0.5rem;
      padding: 1rem 1rem 0;
      max-width: 1200px;
      margin: 0 auto;
      border-bottom: 2px solid #222;
    }}
    .tab-btn {{
      padding: 0.55rem 1.4rem;
      border: none;
      border-radius: 8px 8px 0 0;
      cursor: pointer;
      font-size: 0.88rem;
      font-weight: 600;
      background: #1e1e2e;
      color: #999;
      transition: all 0.2s;
      position: relative;
      bottom: -2px;
    }}
    .tab-btn:hover {{ color: #fff; background: #2a2a3e; }}
    .tab-btn.active {{
      background: #e63946;
      color: #fff;
      border-bottom: 2px solid #e63946;
    }}
    .tab-meta {{
      font-size: 0.7rem;
      color: #888;
      padding: 0.4rem 1rem;
      max-width: 1200px;
      margin: 0 auto;
    }}
    .tab-content {{ display: none; }}
    .tab-content.active {{ display: block; }}

    /* ── 그리드 ── */
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
      gap: 1rem;
      padding: 1rem;
      max-width: 1200px;
      margin: 0 auto;
    }}
    .card {{
      display: block;
      text-decoration: none;
      background: #1a1a1a;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid #2a2a2a;
      transition: transform .2s, border-color .2s, box-shadow .2s;
    }}
    .card:hover {{
      transform: translateY(-4px);
      border-color: #e63946;
      box-shadow: 0 8px 24px rgba(230,57,70,.25);
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
      font-size: 2.5rem;
      color: rgba(255,255,255,.85);
      opacity: 0;
      background: rgba(0,0,0,.35);
      transition: opacity .2s;
    }}
    .card:hover .play-icon {{ opacity: 1; }}
    .info {{ padding: 0.6rem 0.7rem 0.75rem; }}
    .title {{
      font-size: 0.82rem;
      font-weight: 600;
      line-height: 1.35;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
      color: #eee;
    }}
    .meta {{
      display: flex;
      justify-content: space-between;
      margin-top: 0.45rem;
      font-size: 0.7rem;
      color: #888;
    }}
    .empty {{
      text-align: center;
      padding: 4rem 1rem;
      color: #555;
    }}
    .empty p {{ margin-top: 0.5rem; font-size: 0.9rem; }}
    footer {{
      text-align: center;
      padding: 2rem 1rem;
      font-size: 0.75rem;
      color: #444;
      border-top: 1px solid #1e1e1e;
      margin-top: 1rem;
    }}
    @media (max-width: 480px) {{
      .grid {{ grid-template-columns: repeat(2, 1fr); gap: 0.6rem; padding: 0.6rem; }}
      .tab-btn {{ padding: 0.45rem 0.9rem; font-size: 0.8rem; }}
    }}
  </style>
</head>
<body>

<header>
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
  <button class="tab-btn active" onclick="showTab('tab-api', this)">
    &#128273; YouTube API
  </button>
  <button class="tab-btn" onclick="showTab('tab-crawl', this)">
    &#127760; 트렌드 크롤링
  </button>
</div>

<div id="tab-api" class="tab-content active">
  <p class="tab-meta">YouTube Data API v3 · 업데이트: {api_last}</p>
  {api_grid}
</div>

<div id="tab-crawl" class="tab-content">
  <p class="tab-meta">YouTube 트렌딩 크롤링 · 업데이트: {crawl_last}</p>
  {crawl_grid}
</div>

<footer>
  자동 수집 · 매일 17:00 KST · YouTube Shorts 트렌드 기반<br>
  &copy; {datetime.now(KST).year} yclaude
</footer>

<script>
  function showTab(id, btn) {{
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(id).classList.add('active');
    btn.classList.add('active');
  }}
</script>

</body>
</html>
"""
    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    total = len(api_data["videos"]) + len(crawl_data["videos"])
    print(f"index.html 재생성 완료 (API {len(api_data['videos'])}개 + 크롤 {len(crawl_data['videos'])}개)")


# ── 메인 ─────────────────────────────────────────────────
def main():
    api_data   = load_json(VIDEOS_API)
    crawl_data = load_json(VIDEOS_CRAWL)

    existing_api   = {v["id"] for v in api_data["videos"]}
    existing_crawl = {v["id"] for v in crawl_data["videos"]}

    # Tab 1: YouTube API (키 있을 때만)
    if API_KEY:
        new_api = fetch_api(existing_api)
        if new_api:
            api_data["videos"] = new_api + api_data["videos"]
        save_json(VIDEOS_API, api_data)
    else:
        print("[API] YOUTUBE_API_KEY 없음, API 탭 스킵")
        save_json(VIDEOS_API, api_data)

    # Tab 2: yt-dlp 크롤링 (항상 실행)
    new_crawl = fetch_crawl(existing_crawl)
    if new_crawl:
        crawl_data["videos"] = new_crawl + crawl_data["videos"]
    save_json(VIDEOS_CRAWL, crawl_data)

    # HTML 재생성
    regenerate_html(api_data, crawl_data)


if __name__ == "__main__":
    main()
