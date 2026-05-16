"""
YouTube Shorts 트렌드 수집 — YouTube API 탭 + 국가별 17개 탭 (GitHub Actions 전용)
"""

import json, os, re, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST         = timezone(timedelta(hours=9))
BASE        = Path(__file__).parent
INDEX_HTML  = BASE / "index.html"
VIDEOS_API  = BASE / "videos_api.json"
MAX_NEW     = 15   # 국가별 최대 신규 영상 수
MAX_API     = 40   # API 탭 최대 영상 수
DUR_RE      = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
API_KEY     = os.environ.get("YOUTUBE_API_KEY", "")

# YouTube Data API 검색어 (지역 다양화)
API_QUERIES = [
    ("dance shorts viral bgm 2025",         "US"),
    ("dance challenge couple shorts music",  "US"),
    ("solo dance shorts background music",   "BR"),
    ("baile shorts viral bgm trending",      "MX"),
    ("tanz shorts viral bgm",                "DE"),
    ("danca shorts viral bgm",               "BR"),
    ("dance shorts no lyrics trending",      "PH"),
    ("viral dance bgm shorts music",         "JP"),
]

# ── 국가 정의 ────────────────────────────────────────────
# 처리 순서 = 중복 제거 우선순위 (앞 국가가 바이럴 영상 독점)
# (한국어 이름, 파일코드, geo_bypass_country, 검색 키워드, 국기)
COUNTRIES = [
    # ① 글로벌 우선
    ("글로벌",       "GLOBAL", None, "dance viral shorts bgm music trending 2025",    "🌍"),
    # ② 북미·남미 (YouTube 최대 시장)
    ("미국",         "US",     "US", "dance challenge shorts bgm viral music",        "🇺🇸"),
    ("멕시코",       "MX",     "MX", "baile reto shorts viral bgm",                   "🇲🇽"),
    ("브라질",       "BR",     "BR", "danca desafio shorts bgm viral",                "🇧🇷"),
    ("아르헨티나",   "AR",     "AR", "baile reto shorts bgm viral",                   "🇦🇷"),
    # ③ 유럽
    ("독일",         "DE",     "DE", "tanz challenge shorts bgm viral",               "🇩🇪"),
    ("스페인",       "ES",     "ES", "baile reto shorts bgm viral",                   "🇪🇸"),
    ("프랑스",       "FR",     "FR", "danse defi shorts bgm viral",                   "🇫🇷"),
    ("이탈리아",     "IT",     "IT", "ballo sfida shorts bgm viral",                  "🇮🇹"),
    # ④ 동남아·아시아
    ("인도네시아",   "ID",     "ID", "dance challenge shorts bgm viral",              "🇮🇩"),
    ("필리핀",       "PH",     "PH", "dance challenge shorts bgm viral",              "🇵🇭"),
    ("베트남",       "VN",     "VN", "nhay shorts viral bgm thinh hanh",              "🇻🇳"),
    ("일본",         "JP",     "JP", "dance shorts bgm viral #shorts",                "🇯🇵"),
    ("한국",         "KR",     "KR", "dance shorts bgm viral #shorts",                "🇰🇷"),
    # ⑤ 중앙아·아프리카
    ("우즈베키스탄", "UZ",     "UZ", "dance shorts viral bgm challenge",              "🇺🇿"),
    ("알제리",       "DZ",     "DZ", "dance shorts viral bgm",                        "🇩🇿"),
    ("카자흐스탄",   "KZ",     "KZ", "dance shorts viral bgm challenge",              "🇰🇿"),
]

TRENDING_URL = "https://www.youtube.com/feed/trending?bp=4gIKGgh5dHNhX3Ntaw%3D%3D"

EXCLUDE_KW = {
    "tutorial", "recipe", "cooking", "요리", "vlog", "브이로그",
    "자막", "subtitle", "caption", "lyrics", "가사", "review", "리뷰",
    "unboxing", "언박싱", "news", "뉴스", "asmr", "mukbang", "먹방",
    "gaming", "게임", "prank", "compilation", "모음", "how to",
}


# ── 유틸 ────────────────────────────────────────────────
def json_path(code: str) -> Path:
    return BASE / f"videos_{code}.json"

def load_json(p: Path) -> dict:
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"last_updated": "", "videos": []}

def save_json(p: Path, data: dict) -> None:
    data["last_updated"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def now_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")

def is_excluded(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in EXCLUDE_KW)

def fmt_views(n: int) -> str:
    if n >= 100_000_000: return f"{n/100_000_000:.1f}억"
    if n >= 10_000:      return f"{n/10_000:.1f}만"
    return f"{n:,}" if n else "—"

def fmt_dur(secs: int) -> str:
    if not secs: return ""
    m, s = divmod(secs, 60)
    return f"{m}:{s:02d}"

def iso_to_sec(dur: str) -> int:
    m = DUR_RE.match(dur or "")
    if not m: return 0
    h, mi, s = (int(x or 0) for x in m.groups())
    return h*3600 + mi*60 + s


# ── YouTube Data API 탭 ──────────────────────────────────
def fetch_api_tab(existing_ids: set) -> list[dict]:
    if not API_KEY:
        print("[API 탭] YOUTUBE_API_KEY 없음 — 스킵")
        return []
    try:
        from googleapiclient.discovery import build
    except ImportError:
        print("[API 탭] google-api-python-client 미설치")
        return []

    youtube = build("youtube", "v3", developerKey=API_KEY)
    since   = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
    seen    = set(existing_ids)
    cands: list[str] = []

    # ① 다중 검색어로 후보 ID 수집
    for query, region in API_QUERIES:
        print(f"  [API] {query!r} ({region})")
        try:
            resp = youtube.search().list(
                q=query, part="id", type="video",
                videoDuration="short", order="viewCount",
                publishedAfter=since, regionCode=region,
                maxResults=20,
            ).execute()
            for it in resp.get("items", []):
                vid = it["id"]["videoId"]
                if vid not in seen and vid not in cands:
                    cands.append(vid)
        except Exception as e:
            print(f"    검색 오류: {e}")
        time.sleep(0.3)

    if not cands:
        return []

    # ② 상세 정보 (통계 + snippet + contentDetails)
    new: list[dict] = []
    for i in range(0, len(cands), 50):
        batch = cands[i:i+50]
        try:
            det = youtube.videos().list(
                part="snippet,contentDetails,statistics",
                id=",".join(batch),
            ).execute()
        except Exception as e:
            print(f"  [API] 상세 조회 오류: {e}")
            continue

        ch_ids = []
        raw: list[dict] = []
        for item in det.get("items", []):
            secs = iso_to_sec(item["contentDetails"]["duration"])
            if secs > 90: continue
            snip  = item["snippet"]
            stats = item.get("statistics", {})
            title = snip.get("title", "")
            if is_excluded(title): continue
            vid_id = item["id"]
            seen.add(vid_id)
            pub = snip.get("publishedAt", "")[:10]
            ch_id = snip.get("channelId", "")
            if ch_id: ch_ids.append(ch_id)
            raw.append({
                "id":            vid_id,
                "title":         title,
                "thumbnail":     f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg",
                "thumbnail_hq":  f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg",
                "url":           f"https://www.youtube.com/shorts/{vid_id}",
                "added_date":    now_kst(),
                "published_at":  pub,
                "view_count":    int(stats.get("viewCount", 0)),
                "like_count":    int(stats.get("likeCount", 0)),
                "comment_count": int(stats.get("commentCount", 0)),
                "duration_sec":  secs,
                "duration_str":  fmt_dur(secs),
                "channel_id":    ch_id,
                "channel_title": snip.get("channelTitle", ""),
                "channel_thumb": "",
                "category_id":   snip.get("categoryId", ""),
                "tags":          snip.get("tags", [])[:5],
                "description":   snip.get("description", "")[:120],
            })

        # ③ 채널 썸네일 일괄 조회
        if ch_ids:
            try:
                ch_resp = youtube.channels().list(
                    part="snippet", id=",".join(set(ch_ids))
                ).execute()
                ch_map = {
                    c["id"]: c["snippet"]["thumbnails"].get("default", {}).get("url", "")
                    for c in ch_resp.get("items", [])
                }
                for v in raw:
                    v["channel_thumb"] = ch_map.get(v["channel_id"], "")
            except Exception:
                pass

        new.extend(raw)

    new.sort(key=lambda v: v["view_count"], reverse=True)
    result = new[:MAX_API]
    print(f"[API 탭] 신규 {len(result)}개")
    return result


# ── yt-dlp 수집 ──────────────────────────────────────────
def _ydlp(url: str, opts: dict) -> list[dict]:
    try:
        import yt_dlp
    except ImportError:
        return []
    full_opts = {
        "quiet": True, "no_warnings": True,
        "extract_flat": True, "playlistend": 35,
        "ignoreerrors": True, **opts,
    }
    try:
        with yt_dlp.YoutubeDL(full_opts) as ydl:
            info = ydl.extract_info(url, download=False) or {}
            return info.get("entries", [])
    except Exception as e:
        print(f"    yt-dlp 오류: {e}")
        return []


def fetch_country(name: str, code: str, geo: str | None,
                  query: str, existing_ids: set) -> list[dict]:
    geo_opts = {"geo_bypass_country": geo} if geo else {}
    seen = set(existing_ids)
    new: list[dict] = []

    sources = [
        (TRENDING_URL,                geo_opts),
        (f"ytsearchdate30:{query}",   geo_opts),
    ]

    for url, extra in sources:
        print(f"    ↳ {url[:70]}")
        entries = _ydlp(url, extra)
        for e in entries:
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
            new.append({
                "id":           vid_id,
                "title":        title,
                "thumbnail":    f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg",
                "url":          f"https://www.youtube.com/shorts/{vid_id}",
                "added_date":   now_kst(),
                "view_count":   e.get("view_count", 0) or 0,
                "duration_sec": int(dur),
            })
        time.sleep(1.5)   # YouTube 레이트 리밋 방지

    new.sort(key=lambda v: v["view_count"], reverse=True)
    result = new[:MAX_NEW]
    print(f"    → 신규 {len(result)}개")
    return result


# ── HTML 생성 ────────────────────────────────────────────
def _esc(s: str) -> str:
    return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def _card(v: dict) -> str:
    views = fmt_views(v.get("view_count", 0))
    date  = v.get("added_date", "")
    title = _esc(v.get("title", "") or v["id"])
    return f"""<div class="card">
  <a class="tw" href="{v['url']}" target="_blank" rel="noopener">
    <img loading="lazy" src="{v['thumbnail']}" alt="{title}">
    <span class="pi">&#9654;</span>
  </a>
  <div class="info">
    <p class="tt">{title or '(제목 없음)'}</p>
    <p class="meta"><span>👁 {views}</span><span>📅 {date}</span></p>
  </div>
</div>"""

def _api_card(v: dict) -> str:
    title     = _esc(v.get("title","") or v["id"])
    views     = fmt_views(v.get("view_count", 0))
    likes     = fmt_views(v.get("like_count", 0))
    comments  = fmt_views(v.get("comment_count", 0))
    dur       = v.get("duration_str","")
    ch_title  = _esc(v.get("channel_title",""))
    ch_thumb  = v.get("channel_thumb","")
    pub       = v.get("published_at","")
    tags      = v.get("tags",[])
    desc      = _esc(v.get("description","") or "")
    thumb     = v.get("thumbnail_hq") or v.get("thumbnail","")
    dur_html  = f'<span class="dur">{dur}</span>' if dur else ""
    ch_av     = (f'<img class="ch-img" src="{ch_thumb}" alt="">'
                 if ch_thumb else '<span class="ch-ph">▶</span>')
    tag_html  = "".join(f'<span class="tag">#{_esc(t)}</span>' for t in tags[:3])
    return f"""<div class="card api-card">
  <a class="tw" href="{v['url']}" target="_blank" rel="noopener">
    <img loading="lazy" src="{thumb}" alt="{title}">
    {dur_html}
    <span class="pi">&#9654;</span>
  </a>
  <div class="info">
    <p class="tt">{title or '(제목 없음)'}</p>
    <div class="ch"><span class="ch-av">{ch_av}</span><span class="ch-nm">{ch_title}</span></div>
    <div class="stats"><span>👁 {views}</span><span>❤️ {likes}</span><span>💬 {comments}</span></div>
    {f'<p class="desc">{desc}</p>' if desc else ''}
    {f'<div class="tags">{tag_html}</div>' if tag_html else ''}
    <p class="pub">📅 {pub}</p>
  </div>
</div>"""

def _grid(videos: list[dict]) -> str:
    if not videos:
        return """<div class="empty">
  <div style="font-size:2.5rem">🎬</div>
  <p>업데이트 대기 중</p>
  <p class="sub">GitHub Actions가 매일 17:00 KST에 자동으로 채웁니다</p>
</div>"""
    return "<div class='grid'>" + "".join(_card(v) for v in videos) + "</div>"

def _api_grid(videos: list[dict]) -> str:
    if not videos:
        return """<div class="empty">
  <div style="font-size:2.5rem">🔑</div>
  <p>API 키 설정 필요</p>
  <p class="sub">GitHub Secret에 YOUTUBE_API_KEY를 등록하세요</p>
</div>"""
    return "<div class='grid api-grid'>" + "".join(_api_card(v) for v in videos) + "</div>"


def regenerate_html(api_data: list[dict], all_data: list[tuple]) -> None:
    """api_data: API 탭 영상 / all_data: [(name, code, flag, data_dict), ...]"""
    last_times = [d.get("last_updated","") for _,_,_,d in all_data if d.get("last_updated")]
    last = max(last_times) if last_times else "—"
    year = datetime.now(KST).year

    # t0 = YouTube API 탭
    api_cnt = len(api_data)
    tab_btns = (
        f'<button class="tb active" onclick="showTab(\'t0\',this)">'
        f'🔑 YouTube API<span class="cb">{api_cnt}</span></button>\n'
    )
    tab_contents = (
        f'<div id="t0" class="tc active">\n'
        f'  <p class="tm">🔑 YouTube Data API · 조회수 순 · 다양한 국가 검색 기반</p>\n'
        f'  {_api_grid(api_data)}\n'
        f'</div>\n'
    )

    # t1~ = 국가별 탭
    for i, (name, code, flag, data) in enumerate(all_data, start=1):
        cnt     = len(data["videos"])
        updated = data.get("last_updated", "—")
        tab_btns += (
            f'<button class="tb" onclick="showTab(\'t{i}\',this)">'
            f'{flag} {name}<span class="cb">{cnt}</span></button>\n'
        )
        tab_contents += (
            f'<div id="t{i}" class="tc">\n'
            f'  <p class="tm">{flag} {name} · {updated}</p>\n'
            f'  {_grid(data["videos"])}\n'
            f'</div>\n'
        )

    html = f"""<!DOCTYPE html>
<html lang="ko" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>인기 YouTube Shorts — 국가별</title>
  <style>
    :root[data-theme="dark"]{{
      --bg:#0f0f0f;--bg2:#1a1a1a;--bg3:#1e1e2e;
      --bd:#2a2a2a;--tx:#e8e8e8;--tx2:#aaa;--tx3:#888;
      --hbg:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);
      --tabbg:#1e1e2e;--tabtx:#999;
      --sh:rgba(230,57,70,.25);--fbd:#1e1e1e;--tog:#2a2a3e;
    }}
    :root[data-theme="light"]{{
      --bg:#f4f4f4;--bg2:#fff;--bg3:#e8e8f0;
      --bd:#ddd;--tx:#111;--tx2:#444;--tx3:#666;
      --hbg:linear-gradient(135deg,#2c3e7a,#3b5fc0,#1a73e8);
      --tabbg:#e0e0f0;--tabtx:#444;
      --sh:rgba(230,57,70,.18);--fbd:#ddd;--tog:#c8d4f0;
    }}
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:var(--bg);color:var(--tx);
      font-family:'Segoe UI','Apple SD Gothic Neo',sans-serif;
      min-height:100vh;transition:background .25s,color .25s}}

    /* 최소 상단바 */
    .topbar{{display:flex;align-items:center;justify-content:space-between;
      padding:.28rem .7rem;background:var(--hbg);border-bottom:2px solid #e63946}}
    .topbar .upd{{font-size:.62rem;color:rgba(255,255,255,.6)}}
    .topbar .upd b{{color:#f4a261;font-weight:700}}

    /* theme toggle */
    .tog{{background:var(--tog);border:none;border-radius:16px;
      padding:.18rem .5rem;font-size:.68rem;cursor:pointer;color:#fff;
      display:flex;align-items:center;gap:.22rem;font-weight:600;
      box-shadow:0 1px 4px rgba(0,0,0,.3);transition:opacity .2s;flex-shrink:0}}
    .tog:hover{{opacity:.8}}

    /* tab bar */
    .tabbar{{display:flex;overflow-x:auto;-webkit-overflow-scrolling:touch;
      scrollbar-width:none;padding:.5rem .7rem 0;
      border-bottom:2px solid var(--bd);gap:.25rem;
      position:sticky;top:0;z-index:10;
      background:var(--bg);backdrop-filter:blur(8px)}}
    .tabbar::-webkit-scrollbar{{display:none}}
    .tb{{flex-shrink:0;padding:.45rem 1rem;border:none;border-radius:8px 8px 0 0;
      cursor:pointer;font-size:.82rem;font-weight:600;
      background:var(--tabbg);color:var(--tabtx);
      transition:all .2s;position:relative;bottom:-2px;white-space:nowrap}}
    .tb:hover{{color:var(--tx)}}
    .tb.active{{background:#e63946;color:#fff;border-bottom:2px solid #e63946}}
    .cb{{display:inline-block;background:rgba(255,255,255,.22);
      border-radius:10px;padding:0 .38rem;font-size:.68rem;margin-left:.25rem}}

    /* tab content */
    .tm{{font-size:.7rem;color:var(--tx3);padding:.4rem 1rem .05rem;
      max-width:1400px;margin:0 auto}}
    .tc{{display:none}}.tc.active{{display:block}}

    /* grid — 가로형 카드 목록 */
    .grid{{display:grid;
      grid-template-columns:repeat(auto-fill,minmax(280px,1fr));
      gap:.55rem;padding:.85rem 1rem;max-width:1400px;margin:0 auto}}
    .api-grid{{grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}}

    /* card — 썸네일 왼쪽, 정보 오른쪽 */
    .card{{display:flex;flex-direction:row;align-items:flex-start;
      background:var(--bg2);border-radius:10px;overflow:hidden;
      border:1px solid var(--bd);
      transition:border-color .2s,box-shadow .2s}}
    .card:hover{{border-color:#e63946;box-shadow:0 4px 18px var(--sh)}}

    /* 썸네일 — 작은 세로형 고정 크기 */
    .tw{{position:relative;flex-shrink:0;
      width:72px;height:128px;overflow:hidden;background:#111;display:block}}
    .tw img{{width:100%;height:100%;object-fit:cover;display:block}}
    .pi{{position:absolute;inset:0;display:flex;align-items:center;
      justify-content:center;font-size:1.4rem;color:rgba(255,255,255,.95);
      opacity:0;background:rgba(0,0,0,.32);transition:opacity .2s;
      text-decoration:none}}
    .tw:hover .pi{{opacity:1}}

    .info{{flex:1;min-width:0;padding:.45rem .6rem .5rem}}
    .tt{{font-size:.8rem;font-weight:600;line-height:1.38;
      display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;
      overflow:hidden;color:var(--tx)}}
    .meta{{display:flex;justify-content:space-between;
      margin-top:.38rem;font-size:.67rem;color:var(--tx3)}}

    /* API 카드 전용 */
    .dur{{position:absolute;bottom:.35rem;right:.35rem;
      background:rgba(0,0,0,.75);color:#fff;font-size:.65rem;
      padding:.1rem .38rem;border-radius:4px;font-weight:700;letter-spacing:.02em}}
    .ch{{display:flex;align-items:center;gap:.35rem;margin-top:.32rem}}
    .ch-av{{flex-shrink:0;display:flex;align-items:center}}
    .ch-img{{width:22px;height:22px;border-radius:50%;object-fit:cover}}
    .ch-ph{{font-size:.75rem;color:var(--tx3)}}
    .ch-nm{{font-size:.69rem;color:var(--tx2);
      overflow:hidden;white-space:nowrap;text-overflow:ellipsis}}
    .stats{{display:flex;gap:.45rem;font-size:.64rem;color:var(--tx3);margin-top:.22rem;flex-wrap:wrap}}
    .desc{{font-size:.65rem;color:var(--tx3);margin-top:.2rem;line-height:1.4;
      display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
    .tags{{display:flex;flex-wrap:wrap;gap:.18rem;margin-top:.22rem}}
    .tag{{font-size:.6rem;padding:.07rem .32rem;border-radius:6px;
      background:rgba(230,57,70,.14);color:#e63946;font-weight:600}}
    .pub{{font-size:.62rem;color:var(--tx3);margin-top:.28rem}}

    /* empty */
    .empty{{text-align:center;padding:3.5rem 1rem;color:var(--tx3)}}
    .empty p{{margin-top:.4rem;font-size:.85rem}}
    .empty .sub{{font-size:.75rem;color:var(--tx3);margin-top:.25rem}}

    footer{{text-align:center;padding:1.6rem 1rem;font-size:.72rem;
      color:var(--tx3);border-top:1px solid var(--fbd);margin-top:1rem}}

    @media(max-width:480px){{
      .grid{{grid-template-columns:1fr;gap:.4rem;padding:.5rem}}
      .tw{{width:64px;height:114px}}
      .tb{{padding:.35rem .65rem;font-size:.74rem}}
    }}
  </style>
</head>
<body>

<div class="topbar">
  <span class="upd">🕔 <b>{last}</b></span>
  <button class="tog" onclick="toggleTheme()">
    <span id="ti">☀️</span><span id="tl">라이트</span>
  </button>
</div>

<div class="tabbar">
{tab_btns}</div>

{tab_contents}

<footer>
  YouTube API + 17개국 Shorts 트렌딩 자동 수집 · 매일 17:00 KST<br>
  GitHub Actions 완전 자동화 &copy; {year} yclaude
</footer>

<script>
  function showTab(id,btn){{
    document.querySelectorAll('.tc').forEach(t=>t.classList.remove('active'));
    document.querySelectorAll('.tb').forEach(b=>b.classList.remove('active'));
    document.getElementById(id).classList.add('active');
    btn.classList.add('active');
    btn.scrollIntoView({{block:'nearest',inline:'center',behavior:'smooth'}});
  }}
  (function(){{applyTheme(localStorage.getItem('theme')||'dark')}})();
  function toggleTheme(){{
    const c=document.documentElement.getAttribute('data-theme');
    applyTheme(c==='dark'?'light':'dark');
  }}
  function applyTheme(t){{
    document.documentElement.setAttribute('data-theme',t);
    localStorage.setItem('theme',t);
    const d=t==='dark';
    document.getElementById('ti').textContent=d?'☀️':'🌙';
    document.getElementById('tl').textContent=d?'라이트':'다크';
  }}
</script>
</body>
</html>
"""
    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    total = sum(len(d["videos"]) for _,_,_,d in all_data)
    print(f"index.html 완료 — API {api_cnt}개 + 국가별 {total}개 영상 / {len(all_data)}개국")


# ── 메인 ─────────────────────────────────────────────────
def main():
    print("=== YouTube Shorts 수집 시작 ===")

    # ① 기존 전체 ID 수집 (전역 중복 방지)
    global_seen: set[str] = set()
    api_stored = load_json(VIDEOS_API)
    global_seen.update(v["id"] for v in api_stored["videos"])
    for _, code, _, _, _ in COUNTRIES:
        data = load_json(json_path(code))
        global_seen.update(v["id"] for v in data["videos"])
    print(f"기존 전체 영상: {len(global_seen)}개 (중복 검사 기준)")

    # ② YouTube API 탭 수집
    print("\n[🔑 YouTube API 탭]")
    new_api = fetch_api_tab(global_seen)
    global_seen.update(v["id"] for v in new_api)
    if new_api:
        api_stored["videos"] = new_api + api_stored["videos"]
        # 최대 MAX_API * 3 보관 (과거 히스토리 유지)
        api_stored["videos"] = api_stored["videos"][:MAX_API * 3]
    save_json(VIDEOS_API, api_stored)
    api_data = api_stored["videos"][:MAX_API]

    # ③ 국가별 yt-dlp 수집
    all_data = []
    for name, code, geo, query, flag in COUNTRIES:
        print(f"\n[{flag} {name} / {code}]")
        p    = json_path(code)
        data = load_json(p)

        new = fetch_country(name, code, geo, query, global_seen)
        global_seen.update(v["id"] for v in new)

        if new:
            data["videos"] = new + data["videos"]
        save_json(p, data)
        all_data.append((name, code, flag, data))

    # ④ HTML 재생성
    regenerate_html(api_data, all_data)
    print("\n=== 완료 ===")


if __name__ == "__main__":
    main()
