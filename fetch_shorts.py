"""
YouTube Shorts 트렌드 수집 스크립트
- 매일 17:00 KST (08:00 UTC) GitHub Actions에서 실행
- 조건: 배경음악, 자막 없음, 인물 1~2명, 춤/상황
- videos.json 업데이트 후 index.html 재생성
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from googleapiclient.discovery import build
except ImportError:
    print("ERROR: google-api-python-client 미설치. pip install google-api-python-client")
    sys.exit(1)

# ── 설정 ────────────────────────────────────────────────
API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
VIDEOS_JSON = Path(__file__).parent / "videos.json"
INDEX_HTML   = Path(__file__).parent / "index.html"

KST = timezone(timedelta(hours=9))
MAX_NEW_PER_RUN = 20   # 회차당 최대 신규 영상 수

# 수집 검색어 목록 (조건에 맞는 키워드)
SEARCH_QUERIES = [
    "dance shorts no lyrics",
    "dance challenge couple shorts",
    "solo dance shorts trending",
    "dance shorts 1 person",
    "couple moment shorts viral",
    "background music dance shorts",
]

# ── ISO 8601 duration → 초 변환 ──────────────────────────
_DUR_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")

def duration_to_seconds(iso: str) -> int:
    m = _DUR_RE.match(iso or "")
    if not m:
        return 9999
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s


# ── YouTube API 호출 ─────────────────────────────────────
def fetch_candidate_ids(youtube, query: str, published_after: str) -> list[str]:
    resp = youtube.search().list(
        q=query,
        part="id",
        type="video",
        videoDuration="short",
        order="viewCount",
        publishedAfter=published_after,
        regionCode="KR",
        relevanceLanguage="ko",
        maxResults=25,
    ).execute()
    return [item["id"]["videoId"] for item in resp.get("items", [])]


def fetch_video_details(youtube, video_ids: list[str]) -> list[dict]:
    if not video_ids:
        return []
    resp = youtube.videos().list(
        part="snippet,contentDetails,statistics",
        id=",".join(video_ids),
    ).execute()
    results = []
    for item in resp.get("items", []):
        vid_id   = item["id"]
        seconds  = duration_to_seconds(item["contentDetails"]["duration"])
        if seconds > 90:   # 90초 초과 → Shorts 아님
            continue
        snippet  = item["snippet"]
        stats    = item.get("statistics", {})
        results.append({
            "id":          vid_id,
            "title":       snippet.get("title", ""),
            "thumbnail":   f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg",
            "url":         f"https://www.youtube.com/shorts/{vid_id}",
            "added_date":  datetime.now(KST).strftime("%Y-%m-%d"),
            "view_count":  int(stats.get("viewCount", 0)),
            "duration_sec": seconds,
        })
    return results


# ── videos.json 로드/저장 ────────────────────────────────
def load_videos() -> dict:
    if VIDEOS_JSON.exists():
        with open(VIDEOS_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {"last_updated": "", "videos": []}


def save_videos(data: dict) -> None:
    data["last_updated"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    with open(VIDEOS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── index.html 재생성 ────────────────────────────────────
def format_views(n: int) -> str:
    if n >= 100_000_000:
        return f"{n/100_000_000:.1f}억"
    if n >= 10_000:
        return f"{n/10_000:.1f}만"
    return f"{n:,}"


def build_card(v: dict) -> str:
    views = format_views(v.get("view_count", 0))
    date  = v.get("added_date", "")
    title = v.get("title", "").replace("<", "&lt;").replace(">", "&gt;")
    return f"""
    <a class="card" href="{v['url']}" target="_blank" rel="noopener">
      <div class="thumb-wrap">
        <img loading="lazy" src="{v['thumbnail']}" alt="{title}">
        <span class="play-icon">&#9654;</span>
      </div>
      <div class="info">
        <p class="title">{title}</p>
        <p class="meta">
          <span class="views">&#128065; {views}</span>
          <span class="date">&#128197; {date}</span>
        </p>
      </div>
    </a>"""


def regenerate_html(data: dict) -> None:
    last = data.get("last_updated", "—")
    cards_html = "\n".join(build_card(v) for v in data["videos"])

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
      letter-spacing: -0.5px;
      color: #fff;
    }}

    header h1 span {{ color: #e63946; }}

    .subtitle {{
      margin-top: 0.5rem;
      font-size: 0.82rem;
      color: #aaa;
    }}

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
      padding: 1rem;
      max-width: 900px;
      margin: 0 auto;
    }}

    .conditions span {{
      background: #1e1e2e;
      border: 1px solid #333;
      border-radius: 20px;
      padding: 0.3rem 0.75rem;
      font-size: 0.75rem;
      color: #ccc;
    }}

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

    .info {{
      padding: 0.6rem 0.7rem 0.75rem;
    }}

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
    }}

    @media (max-width: 480px) {{
      .grid {{ grid-template-columns: repeat(2, 1fr); gap: 0.6rem; padding: 0.6rem; }}
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
  <span>&#128200; 매일 17:00 KST 업데이트</span>
</div>

<main>
{"<div class='grid'>" + cards_html + "</div>" if data["videos"] else
 "<div class='empty'><div style='font-size:3rem'>&#127916;</div><p>첫 업데이트를 기다리는 중입니다.</p><p>GitHub Actions가 오후 5시에 자동으로 채웁니다.</p></div>"}
</main>

<footer>
  자동 수집 · 매일 17:00 KST · YouTube Shorts 트렌드 기반<br>
  &copy; {datetime.now(KST).year} yclaude
</footer>

</body>
</html>
"""
    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"index.html 재생성 완료 ({len(data['videos'])}개 영상)")


# ── 메인 ─────────────────────────────────────────────────
def main():
    if not API_KEY:
        print("ERROR: 환경변수 YOUTUBE_API_KEY 가 설정되지 않았습니다.")
        sys.exit(1)

    youtube = build("youtube", "v3", developerKey=API_KEY)
    data    = load_videos()
    existing_ids = {v["id"] for v in data["videos"]}

    # 최근 14일 이내 발행 영상 검색
    since = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")

    new_videos: list[dict] = []
    seen_this_run: set[str] = set()

    for query in SEARCH_QUERIES:
        print(f"검색: {query!r}")
        candidate_ids = fetch_candidate_ids(youtube, query, since)
        fresh_ids = [i for i in candidate_ids if i not in existing_ids and i not in seen_this_run]
        if not fresh_ids:
            continue
        details = fetch_video_details(youtube, fresh_ids)
        for v in details:
            seen_this_run.add(v["id"])
            new_videos.append(v)
        if len(new_videos) >= MAX_NEW_PER_RUN:
            break

    # 조회수 내림차순 정렬 후 상위 MAX_NEW_PER_RUN개
    new_videos.sort(key=lambda v: v["view_count"], reverse=True)
    new_videos = new_videos[:MAX_NEW_PER_RUN]

    if new_videos:
        data["videos"] = new_videos + data["videos"]  # 새 영상을 맨 위에
        print(f"신규 {len(new_videos)}개 추가 (누적 {len(data['videos'])}개)")
    else:
        print("신규 영상 없음 (중복 또는 조건 불충족)")

    save_videos(data)
    regenerate_html(data)


if __name__ == "__main__":
    main()
