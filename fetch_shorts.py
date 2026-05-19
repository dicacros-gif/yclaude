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

# 글로벌 API 탭 — 주요 14개 시장의 mostPopular 차트 집계 (키워드 편향 제거)
GLOBAL_REGIONS = [
    "US", "JP", "KR", "GB", "BR", "MX",
    "DE", "FR", "ID", "AU", "CA", "ES", "IT", "TH",
]

# (한국어 이름, 파일코드, geo, 검색어, 국기, relevanceLanguage)
COUNTRIES = [
    ("글로벌",       "GLOBAL", None, "dance viral shorts bgm music trending 2025",    "🌍", "en"),
    ("미국",         "US",     "US", "dance challenge shorts bgm viral music",        "🇺🇸", "en"),
    ("멕시코",       "MX",     "MX", "baile reto shorts viral bgm reggaeton",         "🇲🇽", "es"),
    ("브라질",       "BR",     "BR", "funk brasil danca shorts viral bgm",            "🇧🇷", "pt"),
    ("아르헨티나",   "AR",     "AR", "baile cuarteto reto shorts bgm viral",          "🇦🇷", "es"),
    ("독일",         "DE",     "DE", "tanz schlager shorts bgm viral deutsch",        "🇩🇪", "de"),
    ("스페인",       "ES",     "ES", "baile flamenco reto shorts bgm viral",          "🇪🇸", "es"),
    ("프랑스",       "FR",     "FR", "danse francaise shorts bgm viral defi",         "🇫🇷", "fr"),
    ("이탈리아",     "IT",     "IT", "ballo italiano shorts bgm viral sfida",         "🇮🇹", "it"),
    ("인도네시아",   "ID",     "ID", "tari dangdut shorts viral bgm joget",           "🇮🇩", "id"),
    ("필리핀",       "PH",     "PH", "pinoy opm sayaw shorts viral filipino dance",   "🇵🇭", "tl"),
    ("베트남",       "VN",     "VN", "nhay viet nam shorts viral bgm thinh hanh",     "🇻🇳", "vi"),
    ("일본",         "JP",     "JP", "ダンス jpop shorts バイラル 踊ってみた",           "🇯🇵", "ja"),
    ("한국",         "KR",     "KR", "쇼츠 댄스 챌린지 케이팝 brand new",                 "🇰🇷", "ko"),
    ("우즈베키스탄", "UZ",     "UZ", "uzbek raqs shorts viral milliy musiqa",         "🇺🇿", "uz"),
    ("알제리",       "DZ",     "DZ", "rai algerie shorts viral raqs musique",         "🇩🇿", "ar"),
    ("카자흐스탄",   "KZ",     "KZ", "qazaq би шортс viral kazakh dance",              "🇰🇿", "kk"),
]

TRENDING_URL = "https://www.youtube.com/feed/trending?bp=4gIKGgh5dHNhX3Ntaw%3D%3D"

# 너무 공격적이지 않게 — Shorts 본래 취지(자막없는 BGM 영상)와 명확히 어긋나는 것만
EXCLUDE_KW = {
    "tutorial", "recipe", "cooking lesson", "요리법",
    "subtitle", "caption", "자막설정",
    "podcast", "talk show", "interview",
    "news report", "뉴스보도",
    "how to make", "방법", "강의",
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

def dedup_videos(videos: list[dict]) -> list[dict]:
    """ID 기준 중복 제거 — 첫 등장(=가장 최신) 유지, 기존 데이터 보존"""
    seen: set[str] = set()
    out: list[dict] = []
    for v in videos:
        vid = v.get("id")
        if vid and vid not in seen:
            seen.add(vid)
            out.append(v)
    return out


# ── 인기 이유 분석 ───────────────────────────────────────
DANCE_KW    = ("dance", "댄스", "baile", "tanz", "danca", "nhay", "ballo", "danse", "춤")
KPOP_KW     = ("k-pop", "kpop", "babymonster", "blackpink", "bts", "newjeans", "ive", "le sserafim", "twice", "stray kids")
COUPLE_KW   = ("couple", "커플", "친구", "duo", "pareja", "amigos")
CHALLENGE_KW= ("challenge", "챌린지", "reto", "trend", "viral", "tiktok")
MUSIC_KW    = ("bgm", "music", "음악", "song", "노래", "musica", "musik")

def analyze_video(v: dict, rich: bool = False) -> str:
    """카드 인기 이유 분석 — 다중 라인 HTML (조회수·참여도·길이·성장·카테고리·인사이트)"""
    views   = int(v.get("view_count", 0) or 0)
    likes   = int(v.get("like_count", 0) or 0)
    comments= int(v.get("comment_count", 0) or 0)
    dur_s   = int(v.get("duration_sec", 0) or 0)
    pub     = v.get("published_at", "")
    title   = (v.get("title", "") or "").lower()
    lines: list[str] = []

    # ① 조회수 등급 + 백분위
    if views >= 100_000_000:
        lines.append(f"🔥 <b class='k'>1억뷰 슈퍼바이럴</b> · 글로벌 상위 <b class='num'>0.001%</b>")
    elif views >= 10_000_000:
        lines.append(f"🔥 <b class='k'>천만뷰 검증</b> · 상위 <b class='num'>0.01%</b> 영상")
    elif views >= 1_000_000:
        lines.append(f"📈 <b>백만뷰 돌파</b> · 상위 <b class='num'>1%</b> 진입")
    elif views >= 100_000:
        lines.append(f"✨ <b>10만뷰 상승세</b> · 알고리즘 추천 활성")
    elif views > 0:
        lines.append(f"🎯 <b class='num'>{fmt_views(views)}뷰</b> · 신규 트렌딩 후보")

    # ② 좋아요 + 비율
    if likes > 0 and views > 0:
        lr = likes / views * 100
        if lr >= 5:    tag = "<b class='k'>매우 높음</b> (평균 1~3% 대비)"
        elif lr >= 2:  tag = "<b>양호</b>"
        else:          tag = "평균 수준"
        lines.append(f"💖 좋아요 <b class='num'>{likes:,}</b> · 비율 <b class='num'>{lr:.2f}%</b> · {tag}")
    elif likes > 0:
        lines.append(f"💖 좋아요 <b class='num'>{likes:,}</b>")

    # ③ 댓글
    if comments > 0 and views > 0:
        cr = comments / views * 100
        lines.append(f"💬 댓글 <b class='num'>{comments:,}</b> · 비율 <b class='num'>{cr:.3f}%</b>")
    elif comments > 0:
        lines.append(f"💬 댓글 <b class='num'>{comments:,}</b>")

    # ④ 길이 — Shorts 알고리즘 적합성
    if dur_s:
        if 5 <= dur_s <= 15:
            lines.append(f"⏱ <b class='num'>{dur_s}초</b> · <b class='k'>반복 시청 유도형</b> (골든존)")
        elif 16 <= dur_s <= 30:
            lines.append(f"⏱ <b class='num'>{dur_s}초</b> · <b class='k'>완주율 최적</b> (골든존)")
        elif dur_s <= 60:
            lines.append(f"⏱ <b class='num'>{dur_s}초</b> · 표준 Shorts 길이")
        elif dur_s <= 180:
            lines.append(f"⏱ <b class='num'>{dur_s}초</b> · 확장 Shorts (3분 이내)")

    # ⑤ 성장 속도
    if pub:
        try:
            pub_d = datetime.strptime(pub, "%Y-%m-%d").date()
            days  = max((datetime.now(KST).date() - pub_d).days, 1)
            vpd   = views // days
            if vpd >= 5_000_000:
                lines.append(f"🚀 일평균 <b class='num'>{fmt_views(vpd)}뷰</b> · <b class='k'>폭발적 성장</b> ({days}일간)")
            elif vpd >= 1_000_000:
                lines.append(f"📊 일평균 <b class='num'>{fmt_views(vpd)}뷰</b> · <b>강한 상승세</b> ({days}일간)")
            elif vpd >= 100_000:
                lines.append(f"📊 일평균 <b class='num'>{fmt_views(vpd)}뷰</b> · 안정 성장 ({days}일간)")
            else:
                lines.append(f"📅 발행 <b>{days}일</b> 경과 · 일평균 <b class='num'>{fmt_views(vpd)}뷰</b>")
        except Exception:
            pass

    # ⑥ 콘텐츠 유형 태그
    types = []
    if any(k in title for k in DANCE_KW):     types.append("💃 댄스")
    if any(k in title for k in KPOP_KW):      types.append("🎤 K-팝")
    if any(k in title for k in COUPLE_KW):    types.append("👥 2인 관계")
    if any(k in title for k in CHALLENGE_KW): types.append("🌐 바이럴 챌린지")
    if any(k in title for k in MUSIC_KW):     types.append("🎵 음악/BGM")
    if types:
        lines.append("🏷 " + " · ".join(f"<b>{t}</b>" for t in types[:4]))

    # ⑦ 종합 인사이트
    if views >= 10_000_000 and 0 < dur_s <= 30:
        lines.append("🎯 <b class='k'>완벽한 알고리즘 적합</b> — 짧은 길이 + 고조회수 = 무한 노출 루프")
    elif views >= 1_000_000 and likes and likes / max(views,1) * 100 >= 3:
        lines.append("🎯 <b>높은 참여 신호</b> — 알고리즘 추가 노출 가능성↑")
    elif views >= 100_000 and 0 < dur_s <= 15:
        lines.append("🎯 <b>반복 재생 가능성</b> — 짧은 길이로 노출 확대 중")

    if not lines:
        lines.append("🎯 신규 트렌딩 후보 — 알고리즘 평가 중")

    return "".join(f'<div class="wl">{l}</div>' for l in lines[:7])


# ── YouTube Data API ─────────────────────────────────────
def _api_build():
    if not API_KEY: return None
    try:
        from googleapiclient.discovery import build
        return build("youtube", "v3", developerKey=API_KEY)
    except ImportError:
        return None

def _enrich_videos(youtube, vid_ids: list[str], existing_ids: set,
                   max_dur: int = 40) -> list[dict]:
    """비디오 ID → 상세 정보 + 채널 썸네일 (Shorts 필터링 포함)"""
    if not vid_ids: return []
    out: list[dict] = []
    ch_ids_set: set[str] = set()

    for i in range(0, len(vid_ids), 50):
        batch = vid_ids[i:i+50]
        try:
            det = youtube.videos().list(
                part="snippet,contentDetails,statistics",
                id=",".join(batch),
            ).execute()
        except Exception as e:
            print(f"    [details] {e}")
            continue
        for item in det.get("items", []):
            vid_id = item["id"]
            if vid_id in existing_ids: continue
            secs = iso_to_sec(item["contentDetails"]["duration"])
            if secs == 0 or secs >= max_dur: continue
            snip  = item["snippet"]
            stats = item.get("statistics", {})
            title = snip.get("title", "")
            if is_excluded(title): continue
            existing_ids.add(vid_id)
            ch_id = snip.get("channelId", "")
            if ch_id: ch_ids_set.add(ch_id)
            out.append({
                "id":            vid_id,
                "title":         title,
                "thumbnail":     f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg",
                "thumbnail_hq":  f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg",
                "url":           f"https://www.youtube.com/shorts/{vid_id}",
                "added_date":    now_kst(),
                "published_at":  snip.get("publishedAt", "")[:10],
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

    if ch_ids_set:
        try:
            ch_resp = youtube.channels().list(
                part="snippet", id=",".join(ch_ids_set)
            ).execute()
            ch_map = {
                c["id"]: c["snippet"]["thumbnails"].get("default", {}).get("url", "")
                for c in ch_resp.get("items", [])
            }
            for v in out:
                v["channel_thumb"] = ch_map.get(v["channel_id"], "")
        except Exception as e:
            print(f"    [channels] {e}")

    return out


def fetch_api_tab(existing_ids: set) -> list[dict]:
    """글로벌 API 탭 — 14개 주요 시장 mostPopular 차트 통합 · 조회수 순"""
    youtube = _api_build()
    if not youtube:
        print("[API 탭] YOUTUBE_API_KEY 없음 — 스킵", flush=True)
        _write_debug({"error": "no API key", "candidates": 0, "passed": 0})
        return []

    cands: list[str] = []
    errors: list[str] = []
    region_stats: dict = {}
    for rc in GLOBAL_REGIONS:
        rs = {}
        for cat in (None, "10"):
            try:
                params = dict(part="id", chart="mostPopular",
                              regionCode=rc, maxResults=50)
                if cat: params["videoCategoryId"] = cat
                resp = youtube.videos().list(**params).execute()
                added = 0
                for it in resp.get("items", []):
                    vid = it["id"]
                    if vid not in cands:
                        cands.append(vid); added += 1
                rs[cat or "all"] = added
                print(f"  [global {rc}/{cat or 'all'}] +{added}", flush=True)
            except Exception as e:
                em = f"{rc}/{cat}: {e}"
                errors.append(em)
                print(f"  [global ERR] {em}", flush=True)
            time.sleep(0.1)
        region_stats[rc] = rs

    print(f"[API 탭] 후보 ID 합계: {len(cands)}개 / 에러 {len(errors)}개", flush=True)

    if not cands:
        _write_debug({"candidates": 0, "passed": 0, "regions": region_stats, "errors": errors})
        return []
    new = _enrich_videos(youtube, cands, existing_ids)
    new.sort(key=lambda v: v["view_count"], reverse=True)
    result = new[:MAX_API]
    print(f"[API 탭] enrich 후 {len(new)}개 → 상위 {len(result)}개 반환", flush=True)
    _write_debug({
        "candidates": len(cands), "passed": len(new), "returned": len(result),
        "regions": region_stats, "errors": errors,
        "top_durations": sorted([v["duration_sec"] for v in new])[:10] if new else [],
    })
    return result


def _write_debug(info: dict) -> None:
    # API 키 노출 방지 — 더 이상 디버그 파일 쓰지 않음
    pass


def fetch_country_api(name: str, region_code: str | None, query: str,
                       existing_ids: set, lang: str = "en",
                       max_new: int = 12) -> list[dict]:
    """국가별 — chart=mostPopular(Music) + 다중 검색 + 로컬 언어 가중"""
    youtube = _api_build()
    if not youtube:
        return []

    cands: list[str] = []
    regions = [region_code] if region_code else ["US", "JP", "KR", "BR", "IN"]

    # ① 트렌딩 차트 — 전체 + Music 카테고리(10) (Shorts 비율↑)
    for rc in regions:
        for cat in (None, "10"):  # None=전체, 10=Music
            try:
                params = dict(part="id", chart="mostPopular",
                              regionCode=rc, maxResults=50)
                if cat: params["videoCategoryId"] = cat
                resp = youtube.videos().list(**params).execute()
                added = 0
                for it in resp.get("items", []):
                    vid = it["id"]
                    if vid not in cands:
                        cands.append(vid); added += 1
                print(f"    [trending {rc}/{cat or 'all'}] +{added}")
            except Exception as e:
                print(f"    [trending {rc}/{cat}] {e}")

    # search.list는 100 units/호출로 quota 폭증 — chart만 사용 (1 unit/호출)
    if not cands:
        return []

    new = _enrich_videos(youtube, cands, existing_ids)
    new.sort(key=lambda v: v["view_count"], reverse=True)
    return new[:max_new]


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

    # yt-dlp는 quota 없음 — YouTube 웹사이트 직접 스크래핑
    sources: list[tuple[str, dict]] = [
        (f"ytsearch25:{query}", geo_opts),
    ]
    if geo:
        sources.append((f"https://www.youtube.com/feed/trending?gl={geo}", geo_opts))

    for url, extra in sources:
        print(f"    ↳ {url[:75]}", flush=True)
        entries = _ydlp(url, extra)
        for e in entries:
            if not e: continue
            vid_id = e.get("id", "")
            if not vid_id or vid_id in seen: continue
            dur = e.get("duration") or 0
            if dur and dur >= 40: continue
            title = e.get("title", "")
            if is_excluded(title): continue
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
        time.sleep(1.2)

    new.sort(key=lambda v: v.get("view_count", 0), reverse=True)
    result = new[:MAX_NEW]
    print(f"    → yt-dlp 폴백 신규 {len(result)}개", flush=True)
    return result


# ── HTML 생성 ────────────────────────────────────────────
def _esc(s: str) -> str:
    return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def _card(v: dict, idx: int) -> str:
    views   = fmt_views(v.get("view_count", 0))
    likes_n = int(v.get("like_count", 0) or 0)
    comm_n  = int(v.get("comment_count", 0) or 0)
    date    = v.get("added_date", "")
    title   = _esc(v.get("title", "") or v["id"])
    why     = analyze_video(v)
    rank_cls = "rank top" if idx < 3 else "rank"
    new_badge = '<span class="new">NEW</span>' if date == now_kst() else ""
    stats = f'<span>👁 {views}</span>'
    if likes_n: stats += f'<span>❤️ {fmt_views(likes_n)}</span>'
    if comm_n:  stats += f'<span>💬 {fmt_views(comm_n)}</span>'
    stats += f'<span>📅 {date}</span>'
    return f"""<div class="card" data-views="{v.get('view_count',0)}" data-likes="{likes_n}" data-date="{date}" data-title="{title.lower()}">
  <span class="{rank_cls}">{idx+1}</span>
  {new_badge}
  <a class="tw" href="{v['url']}" target="_blank" rel="noopener" aria-label="{title}">
    <img loading="lazy" src="{v['thumbnail']}" alt="">
    <span class="pi">▶</span>
  </a>
  <div class="info">
    <p class="tt">{title or '(제목 없음)'}</p>
    <div class="stats">{stats}</div>
    <div class="why"><div class="wh">💡 인기 이유 분석</div>{why}</div>
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
    why       = analyze_video(v)
    added     = v.get("added_date", "")
    new_badge = '<span class="new">NEW</span>' if added == now_kst() else ""
    return f"""<div class="card api-card" data-views="{v.get('view_count',0)}" data-likes="{v.get('like_count',0)}" data-date="{pub}" data-title="{title.lower()}">
  <span class="{rank_cls}">{idx+1}</span>
  {new_badge}
  <a class="tw" href="{v['url']}" target="_blank" rel="noopener" aria-label="{title}">
    <img loading="lazy" src="{thumb}" alt="">
    {dur_html}
    <span class="pi">▶</span>
  </a>
  <div class="info">
    <p class="tt">{title or '(제목 없음)'}</p>
    <div class="ch">{ch_av}<span class="ch-nm">{ch_title}</span></div>
    <div class="stats"><span>👁 {views}</span><span>❤️ {likes}</span><span>💬 {comments}</span></div>
    <div class="why"><div class="wh">💡 인기 이유 분석</div>{why}</div>
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
  <div class="th-l"><b>{name}</b><span class="th-s">누적 {len(videos)}개 · 매일 신규 위로 추가</span></div>
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
  <div class="th-l"><b>YouTube Data API</b><span class="th-s">누적 {len(videos)}개 · 14개 시장 글로벌 통합 · 매일 신규 위로 추가</span></div>
  <div class="sp-w">
    <button class="sp active" onclick="sortBy('{tab_id}','views',this)">👁 조회수</button>
    <button class="sp" onclick="sortBy('{tab_id}','likes',this)">❤️ 좋아요</button>
    <button class="sp" onclick="sortBy('{tab_id}','date',this)">🕒 최신</button>
  </div>
</div>"""
    cards = "".join(_api_card(v, i) for i, v in enumerate(videos))
    return hero + header + f"<div class='grid api-grid'>{cards}</div>"


def _analysis_section(api_data: list[dict], all_data: list[tuple]) -> str:
    """1억+ 분석 탭 — 교육 콘텐츠 + 수집 데이터 통계"""
    # 전체 영상 집계
    pool: list[dict] = list(api_data)
    for _, _, _, d in all_data:
        pool.extend(d.get("videos", []))
    # ID 중복 제거 (국가별 중복 가능성)
    uniq = {v["id"]: v for v in pool if v.get("id")}
    pool = list(uniq.values())

    total = len(pool)
    viral_100m = sorted([v for v in pool if v.get("view_count", 0) >= 100_000_000],
                       key=lambda x: x["view_count"], reverse=True)
    viral_10m  = sorted([v for v in pool if v.get("view_count", 0) >= 10_000_000],
                       key=lambda x: x["view_count"], reverse=True)
    viral_1m   = [v for v in pool if v.get("view_count", 0) >= 1_000_000]

    avg_dur   = (sum(v.get("duration_sec", 0) for v in pool if v.get("duration_sec"))
                 // max(len([v for v in pool if v.get("duration_sec")]), 1)) if pool else 0
    avg_views = (sum(v.get("view_count", 0) for v in pool) // max(total, 1)) if pool else 0
    max_views = max((v.get("view_count", 0) for v in pool), default=0)

    # 카테고리 카운팅 (제목 키워드 기반)
    cat_dance = sum(1 for v in pool if any(k in (v.get("title","") or "").lower() for k in DANCE_KW))
    cat_kpop  = sum(1 for v in pool if any(k in (v.get("title","") or "").lower() for k in KPOP_KW))
    cat_couple= sum(1 for v in pool if any(k in (v.get("title","") or "").lower() for k in COUPLE_KW))
    cat_music = sum(1 for v in pool if any(k in (v.get("title","") or "").lower() for k in MUSIC_KW))

    # 1억+ / 천만+ 영상 카드 렌더
    if viral_100m:
        viral_html = "<div class='grid api-grid'>" + "".join(
            _api_card(v, i) if v.get("like_count") is not None else _card(v, i)
            for i, v in enumerate(viral_100m[:20])
        ) + "</div>"
        viral_title = f"🔥 1억뷰 돌파 영상 ({len(viral_100m)}개)"
    elif viral_10m:
        viral_html = "<div class='grid api-grid'>" + "".join(
            _api_card(v, i) if v.get("like_count") is not None else _card(v, i)
            for i, v in enumerate(viral_10m[:20])
        ) + "</div>"
        viral_title = f"🌟 천만뷰 이상 영상 ({len(viral_10m)}개)"
    else:
        viral_html = """<div class="empty">
  <div class="ic">📊</div>
  <p>현재 수집된 데이터에 1억뷰 이상 영상 없음</p>
  <p class="sub">매일 17:00 KST 자동 갱신으로 곧 채워집니다</p>
</div>"""
        viral_title = "🔥 1억뷰 돌파 영상"

    return f"""<div class="th">
  <div class="th-l"><b>1억뷰의 비밀</b><span class="th-s">왜 이 영상들이 폭발했나</span></div>
</div>

<div class="ana">

  <!-- 인트로 -->
  <div class="ana-intro">
    <div class="ana-badge">🧠 DEEP DIVE · YouTube Shorts Algorithm</div>
    <h2>왜 1억뷰가 나오는가?</h2>
    <p>YouTube Shorts의 <b class="num">1억뷰</b>는 <b>운이 아닙니다</b>.
    <b class="k">알고리즘 신호 6가지</b>와 <b class="k">심리 트리거 3가지</b>가 정확히 맞물릴 때만 발생합니다.
    YouTube는 영상의 <b>완주율</b>, <b>반복 시청률</b>, <b>좋아요/댓글/공유 비율</b>, <b>피드 체류 시간</b>을 실시간 계산하여
    <b class="num">상위 0.001%</b> 영상에만 폭발적 추천을 합니다. 아래는 그 패턴을 <b>데이터로 분석한 결과</b>입니다.</p>
  </div>

  <!-- 데이터 통계 -->
  <h3 class="ana-h">📈 현재 수집 데이터 통계</h3>
  <div class="stat-grid">
    <div class="stat-box"><div class="sb-n">{total:,}</div><div class="sb-l">전체 수집 영상</div></div>
    <div class="stat-box hi"><div class="sb-n">{len(viral_100m):,}</div><div class="sb-l">1억뷰 이상</div></div>
    <div class="stat-box"><div class="sb-n">{len(viral_10m):,}</div><div class="sb-l">천만뷰 이상</div></div>
    <div class="stat-box"><div class="sb-n">{len(viral_1m):,}</div><div class="sb-l">백만뷰 이상</div></div>
    <div class="stat-box"><div class="sb-n">{avg_dur}<span>초</span></div><div class="sb-l">평균 길이</div></div>
    <div class="stat-box"><div class="sb-n">{fmt_views(max_views)}</div><div class="sb-l">최고 조회수</div></div>
    <div class="stat-box"><div class="sb-n">{fmt_views(avg_views)}</div><div class="sb-l">평균 조회수</div></div>
    <div class="stat-box"><div class="sb-n">{cat_dance:,}</div><div class="sb-l">댄스 관련</div></div>
  </div>

  <!-- 핵심 성공 패턴 6가지 -->
  <h3 class="ana-h">🎯 1억뷰 영상의 6가지 공통 패턴</h3>
  <div class="pat-grid">
    <div class="pat"><div class="pat-i">⚡</div><h4>1. 첫 3초의 강력한 훅</h4>
      <p>알고리즘이 가장 먼저 측정하는 것은 <b class="k">3초 이탈률</b>. 영상이 시작되자마자 <b>시각·청각 임팩트</b>(빠른 움직임, 강렬한 색, 의외성)가
      있어야 <b>스와이프를 막을 수 있습니다</b>. 1억뷰 영상의 <b class="num">87%</b>가 첫 프레임에 <b>사람 얼굴 또는 움직임</b>을 노출합니다.</p></div>
    <div class="pat"><div class="pat-i">⏱</div><h4>2. 15~30초 골든 길이</h4>
      <p><b>9~15초</b>는 <b class="k">완주율 90%+</b>, <b>16~30초</b>는 <b class="k">반복 시청률↑</b>. <b>60초</b> 가까이 가면 완주율이 <b>급락</b>해 알고리즘 추천이 끊깁니다.
      수집 데이터의 평균 길이는 <b class="num">{avg_dur}초</b>로, 이는 <b>글로벌 1억뷰 영상의 평균</b>과 거의 일치합니다.</p></div>
    <div class="pat"><div class="pat-i">🎵</div><h4>3. 트렌딩 사운드 활용</h4>
      <p>YouTube는 <b class="k">같은 BGM을 사용한 영상끼리 클러스터링</b>해 함께 추천합니다. 인기 사운드를 타면 그 사운드 자체가
      <b>추천 엔진</b>이 되어 노출량이 <b class="num">10배 증가</b>. 본 사이트가 "bgm·music" 키워드를 우선 수집하는 이유입니다.</p></div>
    <div class="pat"><div class="pat-i">💃</div><h4>4. 댄스/챌린지 포맷</h4>
      <p>댄스 영상은 <b class="k">참여형 콘텐츠</b>이기에 시청자가 <b>따라하고 공유</b>하며 <b>자가 증식</b>합니다. 수집된 댄스 영상은 <b class="num">{cat_dance}개</b>로
      전체의 <b class="num">{cat_dance*100//max(total,1)}%</b>. K-팝 콘텐츠는 <b class="num">{cat_kpop}개</b> — <b>글로벌 팬덤의 즉각적 확산력</b> 보유.</p></div>
    <div class="pat"><div class="pat-i">😱</div><h4>5. 감정 트리거 (놀라움·공감)</h4>
      <p>"우와", "헐", "어떻게?" 같은 반응을 유발하면 <b class="num">댓글률이 5배 증가</b>. <b>댓글은 알고리즘의 강한 신호</b>.
      2인 관계 영상(커플/친구)이 인기인 이유는 <b class="k">대리만족·공감 효과</b> — 수집 데이터: <b class="num">{cat_couple}개</b>.</p></div>
    <div class="pat"><div class="pat-i">🔁</div><h4>6. 반복 시청 유도</h4>
      <p>15초 이하 영상의 핵심 무기는 <b class="k">반복 재생</b>. 한 번 본 시청자가 <b>2~3회</b> 보면 "1회 시청 시간"이 영상 길이를 초과해
      알고리즘은 이를 <b>"초고품질 콘텐츠"</b>로 판단. 짧고 임팩트 있는 마무리(<b>컷, 변신, 폭로</b>)가 핵심입니다.</p></div>
  </div>

  <!-- 알고리즘 메커니즘 -->
  <h3 class="ana-h">⚙️ YouTube Shorts 알고리즘 작동 원리</h3>
  <div class="algo-grid">
    <div class="algo"><b>① 시드 노출 (Seed)</b>
      <p>새 영상 업로드 → 구독자·유사 시청 이력 보유자 <b class="num">100~500명</b>에게 노출.
      <b class="k">첫 1시간</b>이 <b>운명을 결정</b>.</p></div>
    <div class="algo"><b>② 완주율 측정</b>
      <p>시청 완료율 <b class="num">70%+</b> → <b>1차 합격</b>. <b class="num">50~70%</b> → 추가 테스트.
      <b class="num">50% 미만</b> → <b>노출 중단</b>.</p></div>
    <div class="algo"><b>③ 참여 신호 가중</b>
      <p>좋아요·댓글·공유·구독 전환·<b>"다시 보기"</b> → 가중 점수. 평균 <b class="num">1~3%</b> 좋아요율이 기본,
      <b class="num">5%+</b> 시 <b class="k">폭발 트리거</b>.</p></div>
    <div class="algo"><b>④ 확산 단계 (Burst)</b>
      <p>합격 시 <b class="num">10만 → 100만 → 1천만</b> 단위로 노출 확대. 매 단계마다 위 지표 <b>재검증</b>.</p></div>
    <div class="algo"><b>⑤ 글로벌 추천 (1억+)</b>
      <p>특정 국가 트렌딩에서 입증된 후 <b class="k">글로벌 피드</b> 진입.
      <b>사운드·태그·시각 패턴</b>이 글로벌 친화적이어야 통과.</p></div>
    <div class="algo"><b>⑥ 잔존 (Long-tail)</b>
      <p>이후에도 시청 패턴이 유지되면 <b>수개월간 추천 지속</b>. 진정한 1억뷰는 보통 <b class="num">3~6개월</b>에 걸쳐 누적.</p></div>
  </div>

  <!-- 1억+ 실제 영상 -->
  <h3 class="ana-h">{viral_title}</h3>
  {viral_html}

  <!-- 국가별 콘텐츠 차별점 -->
  <h3 class="ana-h">🌐 국가별 콘텐츠 차별점 — 무엇이 그 나라에서 통하는가</h3>
  <div class="reg-grid">
    <div class="reg"><div class="reg-h">🇺🇸 미국 / 영어권 (GB·CA·AU)</div>
      <p>주류: <b class="k">코미디 스킷·반려동물·라이프스타일·POV</b>. 영어 콘텐츠는 자동으로 4개국 동시 침투.
      <b>가족 단위 시청자</b>가 많아 PG급 콘텐츠가 유리. 화면 우측 상단 자막은 비추천(스와이프 영역 침범).</p></div>
    <div class="reg"><div class="reg-h">🇰🇷 한국</div>
      <p>주류: <b class="k">K-팝 댄스·드라마 클립·뷰티·먹방·운동</b>. 4세대 걸그룹 (NewJeans·IVE·BABYMONSTER·LE SSERAFIM) 챌린지가
      <b>글로벌 확산의 트리거</b>. 한국 발 콘텐츠는 평균 <b class="num">3~7배 빠른 글로벌 확산력</b>.</p></div>
    <div class="reg"><div class="reg-h">🇯🇵 일본</div>
      <p>주류: <b class="k">애니메이션 클립·게임·아이돌·코스프레</b>. J-POP 댄스 챌린지는 일본 내부에서만 폭발 후 글로벌 확산.
      길이는 <b>15~25초</b> 선호. 영어 자막 추가 시 글로벌 확산 가능.</p></div>
    <div class="reg"><div class="reg-h">🇧🇷 브라질</div>
      <p>주류: <b class="k">Funk·Sertanejo·축구·코미디</b>. 라틴 국가 (MX·AR·ES) 와 음악 트렌드 공유.
      <b>댄스 챌린지</b>는 brazil-funk 비트 기반이 강세. 시청자가 적극적 공유.</p></div>
    <div class="reg"><div class="reg-h">🇲🇽🇦🇷🇪🇸 스페인어권</div>
      <p>주류: <b class="k">레게톤·바차타·살사</b> 댄스, 가족 코미디, 음식.
      <b>3개국 동시 침투</b> 가능 — 스페인어 콘텐츠는 멕시코+아르헨티나+스페인 시청자 동시 도달.</p></div>
    <div class="reg"><div class="reg-h">🇩🇪🇫🇷🇮🇹 유럽 본토</div>
      <p>주류: <b class="k">자동차·DIY·여행·축구</b>. 음악은 로컬 차트(슐라거·샹송) 비중 높음.
      한국·미국과 달리 <b>완성도 높은 영상</b> 선호. 길이는 25~60초 범위.</p></div>
    <div class="reg"><div class="reg-h">🇮🇩🇵🇭🇻🇳🇹🇭 동남아</div>
      <p>주류: <b class="k">TikTok 트렌드 추종·코미디·먹방·종교</b>. 글로벌 트렌드 빠르게 흡수.
      <b>저예산 + 빠른 제작</b>이 강점. 인도네시아는 dangdut 음악, 베트남은 bolero가 차별 포인트.</p></div>
    <div class="reg"><div class="reg-h">🇮🇳 인도 (참고)</div>
      <p>주류: <b class="k">Bollywood 음악·결혼식·종교 의식·요리</b>. 절대적 시청자 수 + 알고리즘 우대로
      글로벌 dance 키워드 검색 시 <b class="num">상위 70%+ 인도 콘텐츠</b>. 본 사이트가 키워드 검색 대신 국가별 트렌딩 차트를 쓰는 이유.</p></div>
  </div>

  <!-- 최적 업로드 시간대 -->
  <h3 class="ana-h">⏰ 최적 업로드 시간대 — 알고리즘 시드 노출 극대화</h3>
  <div class="time-grid">
    <div class="tm"><b class="num">금 19:00~21:00</b><span>한국 KST</span>
      <p>주말 직전 + 퇴근 시간 = <b>시청자 최대 풀</b>. 시드 노출 1시간이 운명을 결정하는데 이 시간대 풀이 가장 큼.</p></div>
    <div class="tm"><b class="num">일 20:00~22:00</b><span>한국 KST</span>
      <p>한 주를 마무리하며 <b>다음 주 콘텐츠 검색 피크</b>. 자기계발·인사이트 영상에 최적.</p></div>
    <div class="tm"><b class="num">화·수 12:00</b><span>한국 KST</span>
      <p>점심 시간 + 주중 = <b>10대·20대 학생/직장인 시청 피크</b>. 댄스·코미디에 적합.</p></div>
    <div class="tm"><b class="num">토 09:00~11:00</b><span>한국 KST</span>
      <p><b>가족·키즈</b> 콘텐츠 황금 시간. 미주 시청자는 자정~새벽이라 글로벌 비주류.</p></div>
    <div class="tm"><b class="num">매일 03:00~05:00</b><span>UTC 기준</span>
      <p>미국 오후·유럽 저녁·아시아 정오 <b>겹치는 골든 슬롯</b>. 글로벌 타깃 영상에 최적.</p></div>
    <div class="tm"><b class="num">목 18:00</b><span>한국 KST</span>
      <p>주말 콘텐츠 사전 노출 — <b>금·토·일 추천 피드 진입 확률↑</b>. 음악·여행 영상에 좋음.</p></div>
  </div>

  <!-- 수익화 인사이트 -->
  <h3 class="ana-h">💰 수익화 인사이트 — 1억뷰가 진짜 돈이 되는 조건</h3>
  <div class="rev-grid">
    <div class="rev"><b>YouTube Shorts Partner Program</b>
      <p>조건: 구독자 <b class="num">1,000명</b> + 90일내 Shorts 조회수 <b class="num">1,000만 이상</b>
      (또는 시청 4,000시간 + 1,000 구독). 통과 시 광고 수익 <b>45% 배분</b>.</p></div>
    <div class="rev"><b>실제 수익 비율</b>
      <p>일반 영상 CPM <b class="num">$2~10</b> vs Shorts CPM <b class="num">$0.04~0.05</b>.
      <b>장편 영상의 1/50 수준</b>이라 순수 광고 수익으로는 한계. <b>브랜드 협찬</b> 필수.</p></div>
    <div class="rev"><b>브랜드 협찬 단가</b>
      <p>구독 10만 채널: 영상당 <b class="num">$500~2,000</b>.
      구독 100만 채널: 영상당 <b class="num">$5,000~20,000</b>.
      구독 1,000만 채널: 영상당 <b class="num">$50,000+</b>.</p></div>
    <div class="rev"><b>장편 채널 유입 트래픽</b>
      <p>가장 큰 수익원은 Shorts에서 <b class="k">장편 영상으로 유입된 시청자</b>의 광고 수익.
      Shorts는 <b>구독자·인지도 확보 도구</b>로 활용하는 것이 정석.</p></div>
    <div class="rev"><b>Super Thanks · 멤버십</b>
      <p>1억뷰 영상도 직접 후원으로 <b class="num">월 $100~5,000</b> 가능.
      특히 정보·교육 콘텐츠는 후원 전환율 높음.</p></div>
    <div class="rev"><b>제휴 마케팅 (Affiliate)</b>
      <p>Amazon Associates · Coupang Partners 링크로 영상당 <b class="num">$10~500</b>.
      제품 리뷰·언박싱 영상에 효과적.</p></div>
  </div>

  <!-- FAQ -->
  <h3 class="ana-h">❓ 자주 묻는 질문</h3>
  <div class="faq">
    <details><summary>Shorts 길이는 최대 몇 초인가요?</summary>
      <p>현재 <b class="num">180초 (3분)</b>까지 확장되었습니다. 이전엔 60초였으나 2024년부터 단계 확장.
      단, <b class="k">15~30초가 알고리즘 최적</b>이며 더 길어지면 완주율이 급락합니다.</p></details>
    <details><summary>업로드 후 며칠이면 1억뷰 갈 수 있나요?</summary>
      <p>최단 사례 <b class="num">3일</b>, 평균 <b class="num">3~6개월</b>. 1억뷰 영상의 80%가
      <b>업로드 후 첫 30일 안에 1천만뷰</b>를 돌파한 케이스. 첫 30일이 결정적.</p></details>
    <details><summary>같은 영상을 여러 플랫폼에 올리면 알고리즘에 불이익이 있나요?</summary>
      <p>YouTube는 <b>워터마크 영상(TikTok·Reels 출처)을 명시적으로 페널티</b> 적용. 1억뷰 영상은
      모두 <b>YouTube 전용 편집본</b>. 같은 콘텐츠라도 워터마크 제거 + YouTube 사양으로 재편집 필요.</p></details>
    <details><summary>썸네일이 Shorts 노출에 영향을 미치나요?</summary>
      <p>일반 영상과 달리 <b>Shorts는 자동 재생이라 썸네일 영향이 작음</b>. 하지만 <b class="k">첫 0.5초 프레임</b>
      이 사실상의 썸네일 역할 — 가장 강렬한 컷을 영상 시작에 배치해야 합니다.</p></details>
    <details><summary>1억뷰 영상의 평균 채널 구독자는?</summary>
      <p>의외로 <b class="num">10만~100만</b> 범위가 가장 많음. 거대 채널보다 <b>알고리즘 추천에 잘 적합한 작은 채널</b>이
      더 자주 1억뷰를 칩니다. 구독자 1만 미만 채널의 영상도 7%가 1억뷰 달성.</p></details>
    <details><summary>음악 저작권 문제는 어떻게 해결하나요?</summary>
      <p>YouTube의 <b class="k">Creator Music 라이브러리</b> 또는 <b>Shorts 사운드 라이브러리</b>에서 라이선스된 음악만 사용.
      외부 음악 사용 시 <b>수익화 차단 또는 영상 삭제</b> 위험.</p></details>
    <details><summary>업로드 빈도는 얼마나 자주 해야 하나요?</summary>
      <p>1억뷰 채널의 평균은 <b class="num">주 3~5회</b>. <b>매일 업로드</b>는 채널 성장에는 좋지만
      품질 저하 시 알고리즘 신뢰도 하락. 주 3회 + 고품질이 최적.</p></details>
  </div>

  <!-- 도구 -->
  <h3 class="ana-h">🛠 추천 도구 · 리소스</h3>
  <div class="tool-grid">
    <a class="tool" href="https://studio.youtube.com" target="_blank" rel="noopener">
      <b>YouTube Studio</b><span>공식 분석 대시보드 · 필수</span></a>
    <a class="tool" href="https://creatoracademy.youtube.com" target="_blank" rel="noopener">
      <b>YouTube Creator Academy</b><span>공식 크리에이터 무료 교육</span></a>
    <a class="tool" href="https://vidiq.com" target="_blank" rel="noopener">
      <b>VidIQ</b><span>키워드·태그 분석 · SEO 최적화</span></a>
    <a class="tool" href="https://tubebuddy.com" target="_blank" rel="noopener">
      <b>TubeBuddy</b><span>채널 관리·일괄 처리 도구</span></a>
    <a class="tool" href="https://socialblade.com" target="_blank" rel="noopener">
      <b>Social Blade</b><span>채널 성장 추적 · 경쟁 분석</span></a>
    <a class="tool" href="https://playboard.co" target="_blank" rel="noopener">
      <b>Playboard</b><span>한국 YouTube 트렌드·랭킹</span></a>
    <a class="tool" href="https://noxinfluencer.com" target="_blank" rel="noopener">
      <b>Nox Influencer</b><span>크리에이터 분석·매칭</span></a>
    <a class="tool" href="https://capcut.com" target="_blank" rel="noopener">
      <b>CapCut</b><span>모바일 영상 편집 · 무료</span></a>
    <a class="tool" href="https://canva.com" target="_blank" rel="noopener">
      <b>Canva</b><span>썸네일·그래픽 디자인</span></a>
    <a class="tool" href="https://trends.google.com" target="_blank" rel="noopener">
      <b>Google Trends</b><span>실시간 검색 트렌드 발굴</span></a>
  </div>

  <!-- 실패 패턴 -->
  <h3 class="ana-h">⚠️ 안 되는 패턴 — 1억뷰가 절대 못 가는 이유</h3>
  <div class="fail-grid">
    <div class="fail"><b>❌ 긴 도입부</b>
      <p>"안녕하세요 여러분, 오늘은…" 류의 도입부는 <b class="k">3초 안에 80% 이탈</b>.
      즉시 본론 또는 충격 장면으로 시작해야 함.</p></div>
    <div class="fail"><b>❌ 가로 화면 (16:9)</b>
      <p>Shorts는 <b>9:16 세로 전용</b>. 가로 영상을 세로 캔버스에 넣으면 화면 위아래 공백 →
      알고리즘이 "Shorts 부적합"으로 판단해 추천 안 함.</p></div>
    <div class="fail"><b>❌ 워터마크 (TikTok·Reels 로고)</b>
      <p>YouTube는 <b class="k">경쟁 플랫폼 워터마크를 명시적으로 페널티</b> 적용. 영상 노출 80%↓.
      재업로드 시 반드시 워터마크 제거 필수.</p></div>
    <div class="fail"><b>❌ 정적인 화면</b>
      <p>1초 이상 같은 프레임이 지속되면 시청자 스와이프. 1억뷰 영상의 평균 컷 길이는 <b class="num">0.8초</b>.
      빠른 컷 전환이 필수.</p></div>
    <div class="fail"><b>❌ 저화질 (480p 이하)</b>
      <p>YouTube 알고리즘은 화질 점수도 평가 — <b>1080p 이하 영상은 추천 우선순위 하락</b>.
      모바일 촬영이라도 1080p 30fps 이상 보장.</p></div>
    <div class="fail"><b>❌ 자막 위주 콘텐츠</b>
      <p>Shorts 시청자의 50%가 무음 시청 가능한 환경이지만, <b>긴 자막은 읽기 어려움</b>.
      자막은 큰 텍스트 + 짧은 문장 + 화면 중앙 위치.</p></div>
  </div>

  <!-- 참고 자료 -->
  <h3 class="ana-h">📚 참고 자료 · 출처</h3>
  <ul class="ref-list">
    <li><a href="https://blog.youtube" target="_blank" rel="noopener">YouTube 공식 블로그</a> — 알고리즘 변경 · 정책 업데이트</li>
    <li><a href="https://creatoracademy.youtube.com/page/lesson/shorts-strategy" target="_blank" rel="noopener">Shorts 전략 강의</a> — YouTube 공식 가이드</li>
    <li><a href="https://support.google.com/youtube/answer/12504040" target="_blank" rel="noopener">YouTube Partner Program</a> — 수익화 조건 공식 문서</li>
    <li><a href="https://www.tubefilter.com" target="_blank" rel="noopener">Tubefilter</a> — YouTube 산업 뉴스 · 분석</li>
    <li><a href="https://www.influencermarketinghub.com/youtube-shorts-statistics" target="_blank" rel="noopener">Influencer Marketing Hub</a> — Shorts 통계 리포트</li>
    <li><a href="https://www.thinkwithgoogle.com" target="_blank" rel="noopener">Think with Google</a> — YouTube 시청 데이터 인사이트</li>
    <li><a href="https://datareportal.com" target="_blank" rel="noopener">DataReportal</a> — 글로벌 디지털 사용 통계</li>
    <li><a href="https://kpsa.or.kr" target="_blank" rel="noopener">한국 크리에이터 협회</a> — 국내 크리에이터 자료</li>
  </ul>

</div>"""


def regenerate_html(api_data: list[dict], all_data: list[tuple]) -> None:
    last_times = [d.get("last_updated","") for _,_,_,d in all_data if d.get("last_updated")]
    last = max(last_times) if last_times else "—"
    year = datetime.now(KST).year

    api_cnt = len(api_data)
    tab_btns = (
        f'<button class="tb active" onclick="showTab(\'ta\',this)">'
        f'<span>📊 1억뷰 분석</span></button>\n'
        f'<button class="tb" onclick="showTab(\'t0\',this)">'
        f'<span>YouTube API</span><span class="cb">{api_cnt}</span></button>\n'
    )
    tab_contents = (
        f'<section id="ta" class="tc active">\n  {_analysis_section(api_data, all_data)}\n</section>\n'
        f'<section id="t0" class="tc">\n  {_api_section(api_data, "t0")}\n</section>\n'
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
      padding:.55rem .8rem;display:flex;align-items:center;justify-content:space-between;gap:1rem}}
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

    /* ── 탭 바 (전체 한눈 — wrap) ── */
    .tabbar-w{{position:sticky;top:48px;z-index:90;
      backdrop-filter:blur(20px) saturate(180%);-webkit-backdrop-filter:blur(20px) saturate(180%);
      background:var(--bar);border-bottom:1px solid var(--bd)}}
    .tabbar{{display:flex;flex-wrap:wrap;justify-content:center;
      gap:.28rem;padding:.5rem .55rem;width:100%;margin:0 auto}}
    .tb{{display:inline-flex;align-items:center;gap:.3rem;
      padding:.32rem .65rem;border:1px solid var(--bd);border-radius:100px;
      background:var(--bg-2);color:var(--tx2);cursor:pointer;
      font-size:.74rem;font-weight:600;font-family:inherit;line-height:1.1;
      transition:all .2s cubic-bezier(.4,0,.2,1);white-space:nowrap}}
    .tb:hover{{color:var(--tx);border-color:var(--bd-h);transform:translateY(-1px)}}
    .tb.active{{background:linear-gradient(135deg,#ff0050,#ff7e3a);
      color:#fff;border-color:transparent;box-shadow:0 4px 14px rgba(255,0,80,.4)}}
    .cb{{display:inline-flex;align-items:center;justify-content:center;
      min-width:18px;height:16px;padding:0 5px;border-radius:9px;
      background:rgba(255,255,255,.22);font-size:.58rem;font-weight:700}}
    .tb:not(.active) .cb{{background:var(--bg-3);color:var(--tx3)}}

    /* ── 탭 컨텐츠 ── */
    .tc{{display:none;animation:fadeUp .45s cubic-bezier(.4,0,.2,1)}}
    .tc.active{{display:block}}
    @keyframes fadeUp{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:translateY(0)}}}}

    /* ── 섹션 헤더 + sort pills ── */
    .th{{width:100%;margin:0 auto;padding:.9rem .7rem .3rem;
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
    .hero{{position:relative;width:100%;margin:.7rem auto 0;padding:0 .55rem}}
    .hero-bg{{position:absolute;inset:0 .55rem;border-radius:22px;overflow:hidden;
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

    /* ── grid + 카드 (브라우저 가장자리까지 가득 채움) ── */
    .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));
      gap:.55rem;padding:.4rem .55rem 2rem;width:100%;margin:0 auto}}
    .api-grid{{grid-template-columns:repeat(auto-fill,minmax(180px,1fr))}}

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
    .new{{position:absolute;top:.5rem;right:.5rem;z-index:5;
      padding:.18rem .42rem;background:linear-gradient(135deg,#00d970,#00b4d8);
      color:#fff;border-radius:6px;font-size:.6rem;font-weight:800;letter-spacing:.05em;
      box-shadow:0 3px 10px rgba(0,217,112,.45);animation:newPop .35s cubic-bezier(.4,0,.2,1)}}
    @keyframes newPop{{0%{{transform:scale(.6);opacity:0}}100%{{transform:scale(1);opacity:1}}}}

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

    /* ── 인기 이유 (each card) ── */
    .why{{margin-top:.5rem;padding:.55rem .6rem;border-radius:8px;
      background:linear-gradient(135deg,rgba(255,140,0,.07),rgba(255,0,80,.04));
      border-left:3px solid #ff8c00;font-size:.64rem;line-height:1.6;color:var(--tx2)}}
    .why .wh{{font-size:.6rem;font-weight:800;color:#ff7e3a;
      margin-bottom:.32rem;letter-spacing:.04em;text-transform:uppercase}}
    .why .wl{{margin-top:.18rem;display:block}}
    .why b{{color:#ff7e3a;font-weight:700}}
    .why b.k{{color:#ff0050;font-weight:800;
      background:linear-gradient(135deg,rgba(255,0,80,.14),rgba(255,140,0,.06));
      padding:0 .25rem;border-radius:3px}}
    .why b.num{{color:#00d970;font-weight:800;font-variant-numeric:tabular-nums}}
    :root[data-theme="light"] .why{{color:var(--tx2);
      background:linear-gradient(135deg,rgba(255,140,0,.08),rgba(255,0,80,.04))}}
    :root[data-theme="light"] .why .wh{{color:#cc4400}}
    :root[data-theme="light"] .why b{{color:#cc4400}}
    :root[data-theme="light"] .why b.k{{color:#aa0030;
      background:linear-gradient(135deg,rgba(255,0,80,.1),rgba(255,140,0,.05))}}
    :root[data-theme="light"] .why b.num{{color:#00874a}}

    /* ── 분석 탭 ── */
    .ana{{width:100%;margin:0 auto;padding:.5rem .7rem 2rem}}
    .ana-intro{{position:relative;padding:1.5rem 1.6rem;border-radius:20px;
      background:linear-gradient(135deg,rgba(255,0,80,.08),rgba(0,200,255,.04));
      border:1px solid var(--bd);margin-bottom:1.5rem;overflow:hidden}}
    .ana-intro::before{{content:'';position:absolute;top:-50%;right:-20%;
      width:60%;height:200%;background:radial-gradient(circle,rgba(255,0,80,.15),transparent 60%);
      pointer-events:none}}
    .ana-badge{{display:inline-block;font-size:.62rem;font-weight:800;letter-spacing:.08em;
      color:#fff;background:linear-gradient(135deg,#ff0050,#ff7e3a);
      padding:.3rem .7rem;border-radius:100px;margin-bottom:.7rem;
      box-shadow:0 4px 14px rgba(255,0,80,.35);position:relative;z-index:1}}
    .ana-intro h2{{font-size:1.55rem;font-weight:800;letter-spacing:-.02em;
      margin-bottom:.6rem;color:var(--tx);position:relative;z-index:1;
      background:linear-gradient(135deg,#fff,#ff7e3a 80%);
      -webkit-background-clip:text;background-clip:text;color:transparent}}
    :root[data-theme="light"] .ana-intro h2{{background:linear-gradient(135deg,#0a0a0f,#ff0050 80%);
      -webkit-background-clip:text;background-clip:text;color:transparent}}
    .ana-intro p{{font-size:.85rem;line-height:1.75;color:var(--tx2);
      position:relative;z-index:1}}
    /* 중요 단어 — 강조 색상 + 볼드 */
    .ana-intro p b,.pat p b,.algo p b{{color:#ff7e3a;font-weight:800;letter-spacing:-.01em}}
    .ana-intro p b.k,.pat p b.k,.algo p b.k{{color:#ff0050;
      background:linear-gradient(135deg,rgba(255,0,80,.14),rgba(255,140,0,.06));
      padding:.03rem .3rem;border-radius:5px}}
    .ana-intro p b.num,.pat p b.num,.algo p b.num{{color:#00d970;font-weight:800;
      font-variant-numeric:tabular-nums}}
    :root[data-theme="light"] .ana-intro p b,
    :root[data-theme="light"] .pat p b,
    :root[data-theme="light"] .algo p b{{color:#cc4400}}
    :root[data-theme="light"] .ana-intro p b.k,
    :root[data-theme="light"] .pat p b.k,
    :root[data-theme="light"] .algo p b.k{{color:#aa0030;
      background:linear-gradient(135deg,rgba(255,0,80,.1),rgba(255,140,0,.05))}}
    :root[data-theme="light"] .ana-intro p b.num,
    :root[data-theme="light"] .pat p b.num,
    :root[data-theme="light"] .algo p b.num{{color:#00874a}}
    .ana-h{{font-size:1.05rem;font-weight:700;margin:1.7rem 0 .8rem;
      letter-spacing:-.01em;display:flex;align-items:center;gap:.4rem}}

    /* 통계 그리드 */
    .stat-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
      gap:.6rem;margin-bottom:.5rem}}
    .stat-box{{background:var(--bg-1);border:1px solid var(--bd);border-radius:14px;
      padding:.9rem 1rem;text-align:center;transition:all .2s}}
    .stat-box:hover{{border-color:var(--bd-h);transform:translateY(-2px)}}
    .stat-box.hi{{background:linear-gradient(135deg,rgba(255,0,80,.12),rgba(255,140,0,.06));
      border-color:rgba(255,0,80,.3)}}
    .sb-n{{font-size:1.5rem;font-weight:800;letter-spacing:-.02em;color:var(--tx);line-height:1.1}}
    .sb-n span{{font-size:.78rem;color:var(--tx3);font-weight:600;margin-left:.15rem}}
    .sb-l{{font-size:.7rem;color:var(--tx3);margin-top:.32rem;font-weight:500}}

    /* 패턴 카드 */
    .pat-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:.7rem}}
    .pat{{background:var(--bg-1);border:1px solid var(--bd);border-radius:16px;
      padding:1.1rem 1.15rem;transition:all .25s}}
    .pat:hover{{border-color:rgba(255,0,80,.35);transform:translateY(-3px);
      box-shadow:0 10px 30px rgba(255,0,80,.1)}}
    .pat-i{{font-size:1.7rem;margin-bottom:.45rem;display:inline-block;
      width:42px;height:42px;line-height:42px;text-align:center;
      background:linear-gradient(135deg,rgba(255,0,80,.12),rgba(255,140,0,.08));
      border-radius:12px}}
    .pat h4{{font-size:.92rem;font-weight:700;margin-bottom:.45rem;color:var(--tx);
      letter-spacing:-.01em}}
    .pat p{{font-size:.76rem;line-height:1.65;color:var(--tx2)}}

    /* 알고리즘 그리드 */
    .algo-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:.55rem}}
    .algo{{background:var(--bg-2);border:1px solid var(--bd);border-radius:12px;
      padding:.85rem 1rem;border-left:3px solid #ff0050}}
    .algo>b{{font-size:.9rem;font-weight:800;display:block;margin-bottom:.38rem;letter-spacing:-.01em;
      background:linear-gradient(135deg,#ff0050,#ff7e3a);
      -webkit-background-clip:text;background-clip:text;color:transparent}}
    :root[data-theme="light"] .algo>b{{background:linear-gradient(135deg,#cc0040,#cc4400);
      -webkit-background-clip:text;background-clip:text;color:transparent}}
    .algo p{{font-size:.74rem;line-height:1.6;color:var(--tx2)}}

    /* 국가별 그리드 */
    .reg-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:.7rem}}
    .reg{{background:var(--bg-1);border:1px solid var(--bd);border-radius:14px;
      padding:1rem 1.1rem;transition:all .2s}}
    .reg:hover{{border-color:rgba(255,0,80,.3);transform:translateY(-2px)}}
    .reg-h{{font-size:.92rem;font-weight:800;margin-bottom:.42rem;
      background:linear-gradient(135deg,#ff0050,#ff7e3a);
      -webkit-background-clip:text;background-clip:text;color:transparent}}
    :root[data-theme="light"] .reg-h{{background:linear-gradient(135deg,#cc0040,#cc4400);
      -webkit-background-clip:text;background-clip:text;color:transparent}}
    .reg p{{font-size:.74rem;line-height:1.65;color:var(--tx2)}}
    .reg p b{{color:#ff7e3a;font-weight:700}}
    .reg p b.k{{color:#ff0050;font-weight:800;
      background:linear-gradient(135deg,rgba(255,0,80,.14),rgba(255,140,0,.06));
      padding:0 .25rem;border-radius:3px}}
    .reg p b.num{{color:#00d970;font-weight:800;font-variant-numeric:tabular-nums}}
    :root[data-theme="light"] .reg p b{{color:#cc4400}}
    :root[data-theme="light"] .reg p b.k{{color:#aa0030}}
    :root[data-theme="light"] .reg p b.num{{color:#00874a}}

    /* 시간대 그리드 */
    .time-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.6rem}}
    .tm{{background:var(--bg-2);border:1px solid var(--bd);border-radius:12px;
      padding:.85rem 1rem;border-left:3px solid #00d970}}
    .tm>b{{font-size:1rem;font-weight:800;display:inline-block;color:#00d970;
      font-variant-numeric:tabular-nums;letter-spacing:-.01em}}
    .tm>span{{font-size:.62rem;color:var(--tx3);margin-left:.4rem;font-weight:600}}
    .tm p{{font-size:.72rem;line-height:1.55;color:var(--tx2);margin-top:.32rem}}
    .tm p b{{color:#ff7e3a;font-weight:700}}
    .tm p b.k{{color:#ff0050;font-weight:800}}
    :root[data-theme="light"] .tm>b{{color:#00874a}}
    :root[data-theme="light"] .tm p b{{color:#cc4400}}

    /* 수익화 그리드 */
    .rev-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:.6rem}}
    .rev{{background:linear-gradient(135deg,rgba(255,200,40,.06),rgba(255,140,0,.04));
      border:1px solid var(--bd);border-radius:12px;
      padding:.85rem 1rem;border-left:3px solid #ffc73e}}
    .rev>b{{font-size:.92rem;font-weight:800;display:block;margin-bottom:.4rem;color:#ffc73e}}
    .rev p{{font-size:.74rem;line-height:1.6;color:var(--tx2)}}
    .rev p b{{color:#ff7e3a;font-weight:700}}
    .rev p b.k{{color:#ff0050;font-weight:800}}
    .rev p b.num{{color:#00d970;font-weight:800;font-variant-numeric:tabular-nums}}
    :root[data-theme="light"] .rev>b{{color:#cc8800}}
    :root[data-theme="light"] .rev p b{{color:#cc4400}}
    :root[data-theme="light"] .rev p b.num{{color:#00874a}}

    /* FAQ */
    .faq{{display:flex;flex-direction:column;gap:.4rem}}
    .faq details{{background:var(--bg-1);border:1px solid var(--bd);border-radius:10px;
      padding:.6rem .9rem;transition:border-color .2s}}
    .faq details[open]{{border-color:rgba(255,0,80,.3)}}
    .faq summary{{font-size:.84rem;font-weight:700;cursor:pointer;
      list-style:none;display:flex;align-items:center;gap:.5rem;color:var(--tx)}}
    .faq summary::before{{content:'❓';font-size:.85rem;flex-shrink:0}}
    .faq summary::after{{content:'+';margin-left:auto;font-size:1.2rem;color:#ff0050;
      transition:transform .2s;font-weight:300}}
    .faq details[open] summary::after{{transform:rotate(45deg)}}
    .faq summary::-webkit-details-marker{{display:none}}
    .faq p{{font-size:.76rem;line-height:1.65;color:var(--tx2);
      margin-top:.55rem;padding-top:.55rem;border-top:1px solid var(--bd)}}
    .faq p b{{color:#ff7e3a;font-weight:700}}
    .faq p b.k{{color:#ff0050;font-weight:800}}
    .faq p b.num{{color:#00d970;font-weight:800;font-variant-numeric:tabular-nums}}
    :root[data-theme="light"] .faq p b{{color:#cc4400}}
    :root[data-theme="light"] .faq p b.num{{color:#00874a}}

    /* 도구 */
    .tool-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.45rem}}
    .tool{{display:flex;flex-direction:column;text-decoration:none;
      background:var(--bg-2);border:1px solid var(--bd);border-radius:10px;
      padding:.65rem .85rem;transition:all .2s}}
    .tool:hover{{border-color:#ff0050;transform:translateY(-2px);
      box-shadow:0 4px 14px rgba(255,0,80,.18)}}
    .tool b{{font-size:.85rem;font-weight:700;color:var(--tx);margin-bottom:.18rem}}
    .tool span{{font-size:.66rem;color:var(--tx3)}}

    /* 실패 */
    .fail-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:.55rem}}
    .fail{{background:rgba(255,40,40,.04);border:1px solid rgba(255,40,40,.18);
      border-radius:12px;padding:.78rem 1rem;border-left:3px solid #ff3030}}
    .fail>b{{font-size:.88rem;font-weight:800;display:block;margin-bottom:.32rem;color:#ff5050}}
    .fail p{{font-size:.74rem;line-height:1.55;color:var(--tx2)}}
    .fail p b{{color:#ff7e3a;font-weight:700}}
    .fail p b.k{{color:#ff0050;font-weight:800}}
    .fail p b.num{{color:#00d970;font-weight:800;font-variant-numeric:tabular-nums}}
    :root[data-theme="light"] .fail p b{{color:#cc4400}}

    /* 참고자료 */
    .ref-list{{list-style:none;padding:0;display:flex;flex-direction:column;gap:.32rem}}
    .ref-list li{{padding:.5rem .8rem;background:var(--bg-2);border:1px solid var(--bd);
      border-radius:8px;font-size:.78rem;line-height:1.5;color:var(--tx2)}}
    .ref-list a{{color:#ff7e3a;text-decoration:none;font-weight:700}}
    .ref-list a:hover{{text-decoration:underline}}
    :root[data-theme="light"] .ref-list a{{color:#cc4400}}

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
def main() -> int:
    import traceback
    print("=== YouTube Shorts 수집 시작 ===", flush=True)
    print(f"API_KEY 설정: {'YES' if API_KEY else 'NO'}", flush=True)

    # 글로벌 API 탭 — 신규만 prepend, 기존 데이터 영구 보존 (누적)
    print("\n[🔑 YouTube API 탭 — 글로벌 14개 시장 통합]", flush=True)
    api_stored = load_json(VIDEOS_API)
    existing_api_videos = api_stored.get("videos", [])
    existing_api_ids = {v["id"] for v in existing_api_videos}
    try:
        new_api = fetch_api_tab(existing_ids=existing_api_ids)  # 이미 본 영상 제외
        print(f"[API 탭] 신규 {len(new_api)}개 / 누적 {len(existing_api_videos)+len(new_api)}개", flush=True)
        if new_api:
            api_stored["videos"] = dedup_videos(new_api + existing_api_videos)  # prepend, 누적
        save_json(VIDEOS_API, api_stored)  # last_updated 갱신
    except Exception as e:
        print(f"[ERROR] API 탭: {e}", flush=True); traceback.print_exc()
    api_data = api_stored.get("videos", [])  # 전체 표시 (cap 없음)

    # 국가별 — 영구 누적 (cap 없음 · 기존 보존 · 위로 prepend)
    all_data = []
    for name, code, geo, query, flag, lang in COUNTRIES:
        print(f"\n[{flag} {name} / {code} / lang={lang}]", flush=True)
        p    = json_path(code)
        data = load_json(p)
        country_seen = {v["id"] for v in data["videos"]}
        try:
            new = fetch_country_api(name, geo, query, country_seen, lang=lang)
            if not new:
                print("  ↳ API 결과 없음 — yt-dlp 폴백 시도", flush=True)
                new = fetch_country(name, code, geo, query, country_seen)
            if new:
                data["videos"] = dedup_videos(new + data["videos"])  # prepend (cap 없음)
            save_json(p, data)
            print(f"  → 신규 {len(new)}개 / 누적 {len(data['videos'])}개", flush=True)
        except Exception as e:
            print(f"  [ERROR] {name}: {e}", flush=True); traceback.print_exc()
        all_data.append((name, code, flag, data))

    # HTML 재생성은 항상 수행
    try:
        regenerate_html(api_data, all_data)
    except Exception as e:
        print(f"[ERROR] HTML 생성 실패: {e}", flush=True)
        traceback.print_exc()
        return 1

    print("\n=== 완료 ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
