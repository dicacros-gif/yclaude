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
MAX_NEW     = 15
MAX_API     = 40
DUR_RE      = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
API_KEY     = os.environ.get("YOUTUBE_API_KEY", "")

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

COUNTRIES = [
    ("글로벌",       "GLOBAL", None, "dance viral shorts bgm music trending 2025",    "🌍"),
    ("미국",         "US",     "US", "dance challenge shorts bgm viral music",        "🇺🇸"),
    ("멕시코",       "MX",     "MX", "baile reto shorts viral bgm",                   "🇲🇽"),
    ("브라질",       "BR",     "BR", "danca desafio shorts bgm viral",                "🇧🇷"),
    ("아르헨티나",   "AR",     "AR", "baile reto shorts bgm viral",                   "🇦🇷"),
    ("독일",         "DE",     "DE", "tanz challenge shorts bgm viral",               "🇩🇪"),
    ("스페인",       "ES",     "ES", "baile reto shorts bgm viral",                   "🇪🇸"),
    ("프랑스",       "FR",     "FR", "danse defi shorts bgm viral",                   "🇫🇷"),
    ("이탈리아",     "IT",     "IT", "ballo sfida shorts bgm viral",                  "🇮🇹"),
    ("인도네시아",   "ID",     "ID", "dance challenge shorts bgm viral",              "🇮🇩"),
    ("필리핀",       "PH",     "PH", "dance challenge shorts bgm viral",              "🇵🇭"),
    ("베트남",       "VN",     "VN", "nhay shorts viral bgm thinh hanh",              "🇻🇳"),
    ("일본",         "JP",     "JP", "dance shorts bgm viral #shorts",                "🇯🇵"),
    ("한국",         "KR",     "KR", "dance shorts bgm viral #shorts",                "🇰🇷"),
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
        time.sleep(1.5)

    new.sort(key=lambda v: v["view_count"], reverse=True)
    result = new[:MAX_NEW]
    print(f"    → 신규 {len(result)}개")
    return result


# ── HTML 생성 ────────────────────────────────────────────
def _esc(s: str) -> str:
    return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def _card(v: dict, idx: int) -> str:
    views = fmt_views(v.get("view_count", 0))
    date  = v.get("added_date", "")
    title = _esc(v.get("title", "") or v["id"])
    rank_cls = "rank top" if idx < 3 else "rank"
    return f"""<div class="card" data-views="{v.get('view_count',0)}" data-date="{date}" data-title="{title.lower()}">
  <span class="{rank_cls}">{idx+1}</span>
  <a class="tw" href="{v['url']}" target="_blank" rel="noopener" aria-label="{title}">
    <img loading="lazy" src="{v['thumbnail']}" alt="">
    <span class="pi">▶</span>
  </a>
  <div class="info">
    <p class="tt">{title or '(제목 없음)'}</p>
    <div class="meta"><span>👁 {views}</span><span>📅 {date}</span></div>
  </div>
</div>"""

def _api_card(v: dict, idx: int) -> str:
    title     = _esc(v.get("title","") or v["id"])
    views     = fmt_views(v.get("view_count", 0))
    likes     = fmt_views(v.get("like_count", 0))
    comments  = fmt_views(v.get("comment_count", 0))
    dur       = v.get("duration_str","")
    ch_title  = _esc(v.get("channel_title",""))
    ch_thumb  = v.get("channel_thumb","")
    pub       = v.get("published_at","")
    tags      = v.get("tags",[])
    thumb     = v.get("thumbnail_hq") or v.get("thumbnail","")
    dur_html  = f'<span class="dur">{dur}</span>' if dur else ""
    ch_av     = (f'<img class="ch-img" src="{ch_thumb}" alt="">'
                 if ch_thumb else '<span class="ch-ph">▶</span>')
    tag_html  = "".join(f'<span class="tag">#{_esc(t)}</span>' for t in tags[:2])
    rank_cls  = "rank top" if idx < 3 else "rank"
    return f"""<div class="card api-card" data-views="{v.get('view_count',0)}" data-likes="{v.get('like_count',0)}" data-date="{pub}" data-title="{title.lower()}">
  <span class="{rank_cls}">{idx+1}</span>
  <a class="tw" href="{v['url']}" target="_blank" rel="noopener" aria-label="{title}">
    <img loading="lazy" src="{thumb}" alt="">
    {dur_html}
    <span class="pi">▶</span>
  </a>
  <div class="info">
    <p class="tt">{title or '(제목 없음)'}</p>
    <div class="ch">{ch_av}<span class="ch-nm">{ch_title}</span></div>
    <div class="stats"><span>👁 {views}</span><span>❤️ {likes}</span><span>💬 {comments}</span></div>
    {f'<div class="tags">{tag_html}</div>' if tag_html else ''}
    <p class="pub">📅 {pub}</p>
  </div>
</div>"""

def _empty(icon: str, msg: str, sub: str) -> str:
    return f"""<div class="empty">
  <div class="ic">{icon}</div>
  <p><span class="pulse"></span>{msg}</p>
  <p class="sub">{sub}</p>
</div>"""

def _grid(videos: list[dict], tab_id: str, name: str, flag: str) -> str:
    if not videos:
        return f"""<div class="th"><div class="th-l"><b>{name}</b><span class="th-s">대기 중</span></div></div>""" + _empty("🎬", "수집 대기 중", "GitHub Actions가 매일 17:00 KST에 자동 실행됩니다")
    header = f"""<div class="th">
  <div class="th-l"><b>{name}</b><span class="th-s">트렌딩 {len(videos)}개</span></div>
  <div class="sp-w">
    <button class="sp active" onclick="sortBy('{tab_id}','views',this)">👁 조회수</button>
    <button class="sp" onclick="sortBy('{tab_id}','date',this)">🕒 최신</button>
  </div>
</div>"""
    return header + "<div class='grid'>" + "".join(_card(v, i) for i, v in enumerate(videos)) + "</div>"

def _api_section(videos: list[dict], tab_id: str = "t0") -> str:
    if not videos:
        return f"""<div class="th"><div class="th-l"><b>YouTube Data API</b><span class="th-s">대기 중</span></div></div>""" + _empty("🔑", "API 수집 대기 중", "GitHub Actions가 곧 채웁니다 · YOUTUBE_API_KEY 등록 완료")

    top = videos[0]
    h_title = _esc(top.get("title",""))
    h_views = fmt_views(top.get("view_count", 0))
    h_likes = fmt_views(top.get("like_count", 0))
    h_comments = fmt_views(top.get("comment_count", 0))
    h_ch = _esc(top.get("channel_title",""))
    h_thumb = top.get("thumbnail_hq") or top.get("thumbnail","")
    h_dur = top.get("duration_str","")
    h_pub = top.get("published_at","")
    hero = f"""<div class="hero">
  <a class="hero-bg" href="{top['url']}" target="_blank" rel="noopener">
    <img src="{h_thumb}" alt="">
  </a>
  <div class="hero-card">
    <a class="hero-thumb" href="{top['url']}" target="_blank" rel="noopener" aria-label="{h_title}">
      <img src="{h_thumb}" alt="">
      {f'<span class="dur">{h_dur}</span>' if h_dur else ''}
      <span class="pi">▶</span>
    </a>
    <div class="hero-info">
      <div class="hero-badge">🔥 NOW TRENDING #1</div>
      <p class="h-title">{h_title}</p>
      <p class="h-ch">📺 {h_ch}</p>
      <div class="h-stats">
        <div class="stat-chip"><span class="ic">👁</span><div class="sc-v"><b>{h_views}</b><span>조회수</span></div></div>
        <div class="stat-chip"><span class="ic">❤️</span><div class="sc-v"><b>{h_likes}</b><span>좋아요</span></div></div>
        <div class="stat-chip"><span class="ic">💬</span><div class="sc-v"><b>{h_comments}</b><span>댓글</span></div></div>
        <div class="stat-chip"><span class="ic">📅</span><div class="sc-v"><b>{h_pub or '—'}</b><span>발행일</span></div></div>
      </div>
    </div>
  </div>
</div>"""

    header = f"""<div class="th">
  <div class="th-l"><b>YouTube Data API</b><span class="th-s">전체 {len(videos)}개 · 다국적 검색</span></div>
  <div class="sp-w">
    <button class="sp active" onclick="sortBy('{tab_id}','views',this)">👁 조회수</button>
    <button class="sp" onclick="sortBy('{tab_id}','likes',this)">❤️ 좋아요</button>
    <button class="sp" onclick="sortBy('{tab_id}','date',this)">🕒 최신</button>
  </div>
</div>"""
    cards = "".join(_api_card(v, i) for i, v in enumerate(videos))
    return hero + header + f"<div class='grid api-grid'>{cards}</div>"


def regenerate_html(api_data: list[dict], all_data: list[tuple]) -> None:
    last_times = [d.get("last_updated","") for _,_,_,d in all_data if d.get("last_updated")]
    last = max(last_times) if last_times else "—"
    year = datetime.now(KST).year

    api_cnt = len(api_data)
    tab_btns = (
        f'<button class="tb active" onclick="showTab(\'t0\',this)">'
        f'<span>YouTube API</span><span class="cb">{api_cnt}</span></button>\n'
    )
    tab_contents = (
        f'<section id="t0" class="tc active">\n  {_api_section(api_data, "t0")}\n</section>\n'
    )

    for i, (name, code, flag, data) in enumerate(all_data, start=1):
        cnt = len(data["videos"])
        tab_btns += (
            f'<button class="tb" onclick="showTab(\'t{i}\',this)">'
            f'<span>{name}</span><span class="cb">{cnt}</span></button>\n'
        )
        tab_contents += (
            f'<section id="t{i}" class="tc">\n  {_grid(data["videos"], f"t{i}", name, flag)}\n</section>\n'
        )

    html = f"""<!DOCTYPE html>
<html lang="ko" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="글로벌 17개국 + YouTube Data API 기반 인기 Shorts 트렌딩 자동 수집">
  <title>SHORTS · 글로벌 트렌딩</title>
  <style>
    :root[data-theme="dark"]{{
      --bg-0:#08080d; --bg-1:#12121a; --bg-2:rgba(255,255,255,.04); --bg-3:rgba(255,255,255,.08);
      --bd:rgba(255,255,255,.08); --bd-h:rgba(255,255,255,.2);
      --tx:#fff; --tx2:rgba(255,255,255,.72); --tx3:rgba(255,255,255,.45);
      --bar:rgba(8,8,13,.72);
    }}
    :root[data-theme="light"]{{
      --bg-0:#f5f5f8; --bg-1:#fff; --bg-2:rgba(0,0,0,.03); --bg-3:rgba(0,0,0,.06);
      --bd:rgba(0,0,0,.08); --bd-h:rgba(0,0,0,.2);
      --tx:#0a0a0f; --tx2:rgba(0,0,0,.72); --tx3:rgba(0,0,0,.5);
      --bar:rgba(245,245,248,.8);
    }}
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    html{{scroll-behavior:smooth}}
    body{{background:var(--bg-0);color:var(--tx);
      font-family:-apple-system,BlinkMacSystemFont,'Pretendard','Segoe UI','Apple SD Gothic Neo',sans-serif;
      min-height:100vh;-webkit-font-smoothing:antialiased;
      transition:background .3s,color .3s;overflow-x:hidden;position:relative}}
    body::before{{content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
      background:
        radial-gradient(circle at 15% 0%,rgba(255,0,80,.10),transparent 45%),
        radial-gradient(circle at 85% 50%,rgba(0,200,255,.05),transparent 40%),
        radial-gradient(circle at 50% 100%,rgba(255,140,0,.06),transparent 45%);
      animation:bgshift 20s ease-in-out infinite alternate}}
    @keyframes bgshift{{0%{{transform:translate(0,0)}}100%{{transform:translate(-3%,2%)}}}}

    /* ── 최상단 바 ── */
    .topbar{{position:sticky;top:0;z-index:100;
      backdrop-filter:blur(24px) saturate(180%);-webkit-backdrop-filter:blur(24px) saturate(180%);
      background:var(--bar);border-bottom:1px solid var(--bd);
      padding:.55rem 1.1rem;display:flex;align-items:center;justify-content:space-between;gap:1rem}}
    .brand{{display:flex;align-items:center;gap:.5rem;font-weight:800}}
    .logo{{width:30px;height:30px;border-radius:9px;display:flex;align-items:center;justify-content:center;
      background:linear-gradient(135deg,#ff0050,#ff7e3a);
      box-shadow:0 0 20px rgba(255,0,80,.45),inset 0 1px 0 rgba(255,255,255,.25);
      font-size:.95rem}}
    .brand .name{{font-size:1rem;letter-spacing:-.02em;
      background:linear-gradient(135deg,#ff0050,#ff7e3a 60%,#ffc23a);
      -webkit-background-clip:text;background-clip:text;color:transparent}}
    .brand .upd{{font-size:.66rem;color:var(--tx3);font-weight:500;margin-left:.25rem}}
    .top-r{{display:flex;align-items:center;gap:.45rem}}

    .search{{position:relative;display:flex;align-items:center}}
    .search input{{background:var(--bg-2);border:1px solid var(--bd);color:var(--tx);
      padding:.4rem .7rem .4rem 1.85rem;border-radius:100px;font-size:.76rem;
      width:170px;outline:none;transition:all .25s;font-family:inherit}}
    .search input:focus{{border-color:#ff0050;box-shadow:0 0 0 3px rgba(255,0,80,.15);width:230px}}
    .search input::placeholder{{color:var(--tx3)}}
    .search::before{{content:'🔍';position:absolute;left:.65rem;font-size:.7rem;opacity:.6}}

    .tog{{background:var(--bg-2);border:1px solid var(--bd);border-radius:100px;
      padding:.35rem .55rem;font-size:.8rem;color:var(--tx);cursor:pointer;
      transition:all .2s;flex-shrink:0;line-height:1}}
    .tog:hover{{border-color:var(--bd-h);background:var(--bg-3);transform:translateY(-1px)}}

    /* ── 탭 바 ── */
    .tabbar-w{{position:sticky;top:48px;z-index:90;
      backdrop-filter:blur(20px) saturate(180%);-webkit-backdrop-filter:blur(20px) saturate(180%);
      background:var(--bar);border-bottom:1px solid var(--bd)}}
    .tabbar{{display:flex;overflow-x:auto;scrollbar-width:none;gap:.32rem;
      padding:.55rem .9rem;max-width:1500px;margin:0 auto}}
    .tabbar::-webkit-scrollbar{{display:none}}
    .tb{{flex-shrink:0;display:flex;align-items:center;gap:.4rem;
      padding:.45rem .85rem;border:1px solid var(--bd);border-radius:100px;
      background:var(--bg-2);color:var(--tx2);cursor:pointer;
      font-size:.78rem;font-weight:600;font-family:inherit;
      transition:all .25s cubic-bezier(.4,0,.2,1);white-space:nowrap}}
    .tb-i{{font-size:.95rem;line-height:1}}
    .tb:hover{{color:var(--tx);border-color:var(--bd-h);transform:translateY(-1px)}}
    .tb.active{{background:linear-gradient(135deg,#ff0050,#ff7e3a);
      color:#fff;border-color:transparent;box-shadow:0 6px 20px rgba(255,0,80,.4)}}
    .cb{{display:inline-flex;align-items:center;justify-content:center;
      min-width:20px;height:18px;padding:0 6px;border-radius:10px;
      background:rgba(255,255,255,.22);font-size:.62rem;font-weight:700}}
    .tb:not(.active) .cb{{background:var(--bg-3);color:var(--tx3)}}

    /* ── 탭 컨텐츠 ── */
    .tc{{display:none;animation:fadeUp .45s cubic-bezier(.4,0,.2,1)}}
    .tc.active{{display:block}}
    @keyframes fadeUp{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:translateY(0)}}}}

    /* ── 섹션 헤더 + sort pills ── */
    .th{{max-width:1500px;margin:0 auto;padding:1.1rem 1.2rem .35rem;
      display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.7rem}}
    .th-l{{display:flex;align-items:center;gap:.5rem;font-size:.94rem;font-weight:700}}
    .th-l b{{font-weight:700}}
    .th-f{{font-size:1.25rem;line-height:1}}
    .th-s{{font-size:.7rem;color:var(--tx3);font-weight:500;margin-left:.3rem}}
    .sp-w{{display:flex;gap:.2rem;background:var(--bg-2);padding:.2rem;
      border-radius:100px;border:1px solid var(--bd)}}
    .sp{{padding:.32rem .7rem;border:none;background:transparent;color:var(--tx3);
      font-size:.7rem;font-weight:600;cursor:pointer;border-radius:100px;
      transition:all .2s;font-family:inherit}}
    .sp:hover{{color:var(--tx)}}
    .sp.active{{background:linear-gradient(135deg,#ff0050,#ff7e3a);color:#fff;
      box-shadow:0 2px 10px rgba(255,0,80,.35)}}

    /* ── HERO (API 탭 최상단) ── */
    .hero{{position:relative;max-width:1500px;margin:.7rem auto 0;padding:0 1.2rem}}
    .hero-bg{{position:absolute;inset:0 1.2rem;border-radius:22px;overflow:hidden;
      filter:blur(40px) saturate(140%);opacity:.45;z-index:0;pointer-events:none}}
    .hero-bg img{{width:100%;height:100%;object-fit:cover;transform:scale(1.2)}}
    .hero-card{{position:relative;z-index:1;
      display:grid;grid-template-columns:200px 1fr;gap:1.6rem;padding:1.3rem;
      background:linear-gradient(135deg,rgba(255,0,80,.06),rgba(255,140,0,.02));
      border:1px solid var(--bd);border-radius:22px;
      backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px)}}
    .hero-thumb{{position:relative;width:200px;aspect-ratio:9/16;border-radius:18px;
      overflow:hidden;display:block;text-decoration:none;
      box-shadow:0 20px 50px rgba(0,0,0,.45),0 0 0 1px rgba(255,255,255,.05) inset;
      transition:transform .35s cubic-bezier(.4,0,.2,1)}}
    .hero-thumb:hover{{transform:translateY(-4px) scale(1.02)}}
    .hero-thumb img{{width:100%;height:100%;object-fit:cover;display:block;transition:transform .5s}}
    .hero-thumb:hover img{{transform:scale(1.05)}}
    .hero-thumb .pi{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
      font-size:3.5rem;color:#fff;
      background:radial-gradient(circle,rgba(0,0,0,.3),rgba(0,0,0,.55));
      opacity:0;transition:opacity .25s}}
    .hero-thumb:hover .pi{{opacity:1}}
    .hero-info{{display:flex;flex-direction:column;justify-content:center;gap:.8rem;min-width:0}}
    .hero-badge{{display:inline-flex;align-items:center;gap:.3rem;
      font-size:.62rem;font-weight:800;letter-spacing:.08em;
      color:#fff;background:linear-gradient(135deg,#ff0050,#ff7e3a);
      padding:.32rem .7rem;border-radius:100px;width:fit-content;
      box-shadow:0 4px 16px rgba(255,0,80,.4)}}
    .h-title{{font-size:1.25rem;font-weight:700;line-height:1.3;color:var(--tx);
      display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
    .h-ch{{font-size:.85rem;color:var(--tx2);font-weight:500}}
    .h-stats{{display:flex;gap:.55rem;flex-wrap:wrap;margin-top:.2rem}}
    .stat-chip{{display:flex;align-items:center;gap:.5rem;
      background:var(--bg-2);border:1px solid var(--bd);
      padding:.55rem .85rem;border-radius:14px;transition:all .2s}}
    .stat-chip:hover{{border-color:var(--bd-h);transform:translateY(-1px)}}
    .stat-chip .ic{{font-size:1.05rem;line-height:1}}
    .stat-chip .sc-v{{display:flex;flex-direction:column;gap:0;line-height:1.2}}
    .stat-chip .sc-v b{{font-size:.86rem;font-weight:700;color:var(--tx)}}
    .stat-chip .sc-v span{{font-size:.6rem;color:var(--tx3);font-weight:500}}

    /* ── grid + 카드 ── */
    .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));
      gap:.85rem;padding:.45rem 1.2rem 2rem;max-width:1500px;margin:0 auto}}
    .api-grid{{grid-template-columns:repeat(auto-fill,minmax(170px,1fr))}}

    .card{{position:relative;background:var(--bg-1);border:1px solid var(--bd);
      border-radius:16px;overflow:hidden;
      transition:transform .3s cubic-bezier(.4,0,.2,1),border-color .3s,box-shadow .3s;
      animation:cardIn .5s cubic-bezier(.4,0,.2,1) backwards}}
    .card:hover{{transform:translateY(-5px);border-color:rgba(255,0,80,.4);
      box-shadow:0 14px 40px rgba(255,0,80,.18)}}
    @keyframes cardIn{{from{{opacity:0;transform:translateY(12px)}}to{{opacity:1;transform:translateY(0)}}}}
    .card:nth-child(1){{animation-delay:0s}}.card:nth-child(2){{animation-delay:.03s}}
    .card:nth-child(3){{animation-delay:.06s}}.card:nth-child(4){{animation-delay:.09s}}
    .card:nth-child(5){{animation-delay:.12s}}.card:nth-child(6){{animation-delay:.15s}}
    .card:nth-child(7){{animation-delay:.18s}}.card:nth-child(8){{animation-delay:.21s}}

    .rank{{position:absolute;top:.5rem;left:.5rem;z-index:5;
      min-width:26px;height:26px;padding:0 7px;
      background:rgba(0,0,0,.72);backdrop-filter:blur(8px);color:#fff;
      border-radius:8px;display:flex;align-items:center;justify-content:center;
      font-size:.72rem;font-weight:800;letter-spacing:.02em}}
    .rank.top{{background:linear-gradient(135deg,#ff0050,#ff7e3a);
      box-shadow:0 5px 14px rgba(255,0,80,.5)}}

    .tw{{position:relative;display:block;aspect-ratio:9/16;
      overflow:hidden;background:#000;text-decoration:none}}
    .tw img{{width:100%;height:100%;object-fit:cover;transition:transform .5s}}
    .tw:hover img{{transform:scale(1.06)}}
    .pi{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
      font-size:2.4rem;color:#fff;
      background:radial-gradient(circle at center,rgba(0,0,0,.25),rgba(0,0,0,.55));
      opacity:0;transition:opacity .25s;text-decoration:none}}
    .tw:hover .pi{{opacity:1}}
    .dur{{position:absolute;bottom:.45rem;right:.45rem;
      background:rgba(0,0,0,.82);backdrop-filter:blur(4px);color:#fff;
      font-size:.64rem;padding:.13rem .42rem;border-radius:5px;
      font-weight:700;letter-spacing:.03em}}

    .info{{padding:.6rem .68rem .72rem}}
    .tt{{font-size:.78rem;font-weight:600;line-height:1.38;color:var(--tx);
      display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
      overflow:hidden;margin-bottom:.4rem;min-height:2.15em}}
    .ch{{display:flex;align-items:center;gap:.4rem;margin-bottom:.32rem}}
    .ch-img{{width:20px;height:20px;border-radius:50%;object-fit:cover;flex-shrink:0;
      border:1px solid var(--bd)}}
    .ch-ph{{width:20px;height:20px;border-radius:50%;background:var(--bg-3);
      flex-shrink:0;display:flex;align-items:center;justify-content:center;
      font-size:.55rem;color:var(--tx3)}}
    .ch-nm{{font-size:.7rem;color:var(--tx2);font-weight:500;
      overflow:hidden;white-space:nowrap;text-overflow:ellipsis;min-width:0;flex:1}}
    .stats{{display:flex;gap:.55rem;font-size:.65rem;color:var(--tx3);
      font-weight:500;flex-wrap:wrap}}
    .stats span{{display:inline-flex;align-items:center;gap:.18rem}}
    .meta{{display:flex;justify-content:space-between;font-size:.66rem;color:var(--tx3)}}
    .tags{{display:flex;flex-wrap:wrap;gap:.22rem;margin-top:.35rem}}
    .tag{{font-size:.58rem;padding:.1rem .42rem;border-radius:100px;
      background:rgba(255,0,80,.1);color:#ff5070;font-weight:600;
      border:1px solid rgba(255,0,80,.18)}}
    .pub{{font-size:.62rem;color:var(--tx3);margin-top:.32rem;font-weight:500}}

    /* ── 빈 상태 ── */
    .empty{{text-align:center;padding:4rem 1rem;color:var(--tx3);
      max-width:500px;margin:0 auto}}
    .empty .ic{{font-size:3.2rem;margin-bottom:.7rem;opacity:.55}}
    .empty p{{margin-top:.4rem;font-size:.88rem;font-weight:500}}
    .empty .sub{{font-size:.72rem;opacity:.75;margin-top:.3rem}}
    .pulse{{display:inline-block;width:8px;height:8px;background:#ff0050;
      border-radius:50%;animation:pulse 1.5s infinite;margin-right:.45rem;
      vertical-align:middle}}
    @keyframes pulse{{0%,100%{{opacity:1;transform:scale(1);box-shadow:0 0 0 0 rgba(255,0,80,.6)}}
      50%{{opacity:.55;transform:scale(1.4);box-shadow:0 0 0 10px rgba(255,0,80,0)}}}}

    /* ── 푸터 ── */
    footer{{text-align:center;padding:2.2rem 1rem 2.5rem;font-size:.7rem;
      color:var(--tx3);border-top:1px solid var(--bd);margin-top:2rem;line-height:1.65}}
    footer a{{color:var(--tx2);text-decoration:none}}
    footer a:hover{{color:#ff5070}}

    /* ── filter hidden ── */
    .card.hidden{{display:none}}

    /* ── 반응형 ── */
    @media(max-width:768px){{
      .hero-card{{grid-template-columns:1fr;gap:1rem;padding:1rem}}
      .hero-thumb{{width:100%;max-width:180px;margin:0 auto}}
      .h-title{{font-size:1.05rem}}
      .search input{{width:120px}}.search input:focus{{width:170px}}
      .brand .upd{{display:none}}
    }}
    @media(max-width:480px){{
      .grid{{grid-template-columns:repeat(2,1fr);gap:.5rem;padding:.35rem .55rem 2rem}}
      .api-grid{{grid-template-columns:repeat(2,1fr)}}
      .th{{padding:.85rem .7rem .25rem}}
      .hero{{padding:0 .6rem}}
      .hero-bg{{inset:0 .6rem}}
      .topbar{{padding:.5rem .7rem}}
      .h-stats{{gap:.4rem}}
      .stat-chip{{padding:.4rem .6rem}}
    }}
  </style>
</head>
<body>

<div class="topbar">
  <div class="brand">
    <span class="logo">🎬</span>
    <span class="name">SHORTS</span>
    <span class="upd">{last}</span>
  </div>
  <div class="top-r">
    <div class="search">
      <input id="sIn" type="text" placeholder="검색…" oninput="onSearch(this.value)">
    </div>
    <button class="tog" onclick="toggleTheme()" aria-label="테마 전환">
      <span id="ti">☀️</span>
    </button>
  </div>
</div>

<div class="tabbar-w"><div class="tabbar">
{tab_btns}</div></div>

<main>
{tab_contents}
</main>

<footer>
  YouTube Data API + 17개국 트렌딩 자동 수집 · 매일 17:00 KST<br>
  Powered by GitHub Actions · <a href="https://github.com/dicacros-gif/yclaude" target="_blank">github.com/dicacros-gif/yclaude</a> &copy; {year}
</footer>

<script>
  function showTab(id, btn){{
    document.querySelectorAll('.tc').forEach(t=>t.classList.remove('active'));
    document.querySelectorAll('.tb').forEach(b=>b.classList.remove('active'));
    document.getElementById(id).classList.add('active');
    btn.classList.add('active');
    btn.scrollIntoView({{block:'nearest',inline:'center',behavior:'smooth'}});
    document.getElementById('sIn').value='';
    document.querySelectorAll('.card.hidden').forEach(c=>c.classList.remove('hidden'));
  }}

  function onSearch(q){{
    q = (q||'').trim().toLowerCase();
    const active = document.querySelector('.tc.active');
    if (!active) return;
    active.querySelectorAll('.card').forEach(c=>{{
      const t = c.dataset.title || '';
      c.classList.toggle('hidden', q && !t.includes(q));
    }});
  }}

  function sortBy(tabId, key, btn){{
    const tab = document.getElementById(tabId);
    if (!tab) return;
    tab.querySelectorAll('.sp').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    const grid = tab.querySelector('.grid');
    if (!grid) return;
    const cards = Array.from(grid.querySelectorAll('.card'));
    cards.sort((a,b)=>{{
      const av = a.dataset[key] || '';
      const bv = b.dataset[key] || '';
      if (key === 'date') return bv.localeCompare(av);
      return (parseFloat(bv)||0) - (parseFloat(av)||0);
    }});
    cards.forEach((c,i)=>{{
      grid.appendChild(c);
      const r = c.querySelector('.rank');
      if (r){{ r.textContent = i+1; r.classList.toggle('top', i<3); }}
    }});
  }}

  (function(){{applyTheme(localStorage.getItem('theme')||'dark')}})();
  function toggleTheme(){{
    const c = document.documentElement.getAttribute('data-theme');
    applyTheme(c==='dark'?'light':'dark');
  }}
  function applyTheme(t){{
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('theme', t);
    document.getElementById('ti').textContent = t==='dark' ? '☀️' : '🌙';
  }}

  // Keyboard shortcuts
  document.addEventListener('keydown', e=>{{
    if (e.target.tagName === 'INPUT') return;
    if (e.key === '/'){{ e.preventDefault(); document.getElementById('sIn').focus(); }}
    if (e.key === 't'){{ toggleTheme(); }}
  }});
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

    global_seen: set[str] = set()
    api_stored = load_json(VIDEOS_API)
    global_seen.update(v["id"] for v in api_stored["videos"])
    for _, code, _, _, _ in COUNTRIES:
        data = load_json(json_path(code))
        global_seen.update(v["id"] for v in data["videos"])
    print(f"기존 전체 영상: {len(global_seen)}개 (중복 검사 기준)")

    print("\n[🔑 YouTube API 탭]")
    new_api = fetch_api_tab(global_seen)
    global_seen.update(v["id"] for v in new_api)
    if new_api:
        api_stored["videos"] = new_api + api_stored["videos"]
        api_stored["videos"] = api_stored["videos"][:MAX_API * 3]
    save_json(VIDEOS_API, api_stored)
    api_data = api_stored["videos"][:MAX_API]

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

    regenerate_html(api_data, all_data)
    print("\n=== 완료 ===")


if __name__ == "__main__":
    main()
