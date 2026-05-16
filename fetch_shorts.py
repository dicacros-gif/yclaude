"""
YouTube Shorts 트렌드 수집 — 국가별 17개 탭 (GitHub Actions 전용)
각 국가의 YouTube 트렌딩 Shorts + 국가별 언어 검색어로 수집
"""

import json, os, re, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST        = timezone(timedelta(hours=9))
BASE       = Path(__file__).parent
INDEX_HTML = BASE / "index.html"
MAX_NEW    = 15   # 국가별 최대 신규 영상 수
DUR_RE     = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')

# ── 국가 정의 ────────────────────────────────────────────
# 처리 순서 = 중복 제거 우선순위 (앞 국가가 바이럴 영상 독점)
# → 글로벌·주요 시장 먼저, 한국은 뒤쪽 처리
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
def _card(v: dict) -> str:
    views = fmt_views(v.get("view_count", 0))
    date  = v.get("added_date", "")
    title = (v.get("title", "") or v["id"]).replace("<","&lt;").replace(">","&gt;")
    return f"""<a class="card" href="{v['url']}" target="_blank" rel="noopener">
      <div class="tw">
        <img loading="lazy" src="{v['thumbnail']}" alt="{title}">
        <span class="pi">&#9654;</span>
      </div>
      <div class="info">
        <p class="tt">{title or '(제목 없음)'}</p>
        <p class="meta"><span>👁 {views}</span><span>📅 {date}</span></p>
      </div>
    </a>"""

def _grid(videos: list[dict]) -> str:
    if not videos:
        return """<div class="empty">
      <div style="font-size:2.5rem">🎬</div>
      <p>업데이트 대기 중</p>
      <p class="sub">GitHub Actions가 매일 17:00 KST에 자동으로 채웁니다</p>
    </div>"""
    return "<div class='grid'>" + "".join(_card(v) for v in videos) + "</div>"

def regenerate_html(all_data: list[tuple]) -> None:
    """all_data: [(name, code, flag, data_dict), ...]"""
    last_times = [d.get("last_updated","") for _,_,_,d in all_data if d.get("last_updated")]
    last = max(last_times) if last_times else "—"
    year = datetime.now(KST).year

    # 탭 버튼
    tab_btns = ""
    for i, (name, code, flag, data) in enumerate(all_data):
        cnt   = len(data["videos"])
        active = " active" if i == 0 else ""
        tab_btns += (
            f'<button class="tb{active}" '
            f'onclick="showTab(\'{code}\',this)">'
            f'{flag} {name}'
            f'<span class="cb">{cnt}</span></button>\n'
        )

    # 탭 콘텐츠
    tab_contents = ""
    for i, (name, code, flag, data) in enumerate(all_data):
        active  = " active" if i == 0 else ""
        updated = data.get("last_updated", "—")
        tab_contents += (
            f'<div id="{code}" class="tc{active}">\n'
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

    /* header */
    header{{background:var(--hbg);padding:1.5rem 1rem 1.1rem;
      text-align:center;border-bottom:2px solid #e63946;position:relative}}
    header h1{{font-size:clamp(1.2rem,4vw,2rem);font-weight:800;color:#fff}}
    header h1 span{{color:#f4a261}}
    .sub{{margin-top:.35rem;font-size:.78rem;color:rgba(255,255,255,.65)}}
    .badge{{display:inline-block;margin-top:.6rem;padding:.2rem .7rem;
      background:#e63946;border-radius:20px;font-size:.72rem;color:#fff;font-weight:600}}

    /* theme toggle */
    .tog{{position:absolute;top:.9rem;right:.9rem;background:var(--tog);
      border:none;border-radius:24px;padding:.32rem .75rem;font-size:.82rem;
      cursor:pointer;color:#fff;display:flex;align-items:center;gap:.3rem;
      font-weight:600;box-shadow:0 2px 8px rgba(0,0,0,.3);transition:opacity .2s}}
    .tog:hover{{opacity:.8}}

    /* conditions */
    .conds{{display:flex;flex-wrap:wrap;justify-content:center;
      gap:.3rem;padding:.65rem 1rem;max-width:960px;margin:0 auto}}
    .conds span{{background:var(--bg3);border:1px solid var(--bd);
      border-radius:20px;padding:.22rem .65rem;font-size:.7rem;color:var(--tx2)}}

    /* tab bar */
    .tabbar{{display:flex;overflow-x:auto;-webkit-overflow-scrolling:touch;
      scrollbar-width:none;padding:.8rem 1rem 0;
      border-bottom:2px solid var(--bd);gap:.3rem;
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
      max-width:1200px;margin:0 auto}}
    .tc{{display:none}}.tc.active{{display:block}}

    /* grid */
    .grid{{display:grid;
      grid-template-columns:repeat(auto-fill,minmax(165px,1fr));
      gap:.85rem;padding:.85rem 1rem;max-width:1200px;margin:0 auto}}
    .card{{display:block;text-decoration:none;background:var(--bg2);
      border-radius:12px;overflow:hidden;border:1px solid var(--bd);
      transition:transform .2s,border-color .2s,box-shadow .2s}}
    .card:hover{{transform:translateY(-4px);border-color:#e63946;
      box-shadow:0 8px 24px var(--sh)}}
    .tw{{position:relative;aspect-ratio:9/16;overflow:hidden;background:#111}}
    .tw img{{width:100%;height:100%;object-fit:cover;display:block}}
    .pi{{position:absolute;inset:0;display:flex;align-items:center;
      justify-content:center;font-size:2rem;color:rgba(255,255,255,.9);
      opacity:0;background:rgba(0,0,0,.28);transition:opacity .2s}}
    .card:hover .pi{{opacity:1}}
    .info{{padding:.5rem .6rem .65rem}}
    .tt{{font-size:.79rem;font-weight:600;line-height:1.35;
      display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
      overflow:hidden;color:var(--tx)}}
    .meta{{display:flex;justify-content:space-between;
      margin-top:.38rem;font-size:.67rem;color:var(--tx3)}}

    /* empty */
    .empty{{text-align:center;padding:3.5rem 1rem;color:var(--tx3)}}
    .empty p{{margin-top:.4rem;font-size:.85rem}}
    .empty .sub{{font-size:.75rem;color:var(--tx3);margin-top:.25rem}}

    footer{{text-align:center;padding:1.6rem 1rem;font-size:.72rem;
      color:var(--tx3);border-top:1px solid var(--fbd);margin-top:1rem}}

    @media(max-width:480px){{
      .grid{{grid-template-columns:repeat(2,1fr);gap:.5rem;padding:.55rem}}
      .tb{{padding:.38rem .75rem;font-size:.76rem}}
      .tog{{top:.55rem;right:.55rem;padding:.25rem .6rem;font-size:.76rem}}
    }}
  </style>
</head>
<body>

<header>
  <button class="tog" onclick="toggleTheme()">
    <span id="ti">☀️</span><span id="tl">라이트</span>
  </button>
  <h1>🎬 국가별 인기 <span>YouTube Shorts</span></h1>
  <div class="sub">배경음악 · 자막없음 · 1~2명 · 댄스/상황</div>
  <div class="badge">마지막 업데이트: {last}</div>
</header>

<div class="conds">
  <span>🎵 배경음악만</span>
  <span>🚫 자막 없음</span>
  <span>👤 인물 1~2명</span>
  <span>💃 댄스 / 상황</span>
  <span>📈 매일 17:00 KST 자동 업데이트</span>
  <span>🌍 17개국 트렌딩</span>
</div>

<div class="tabbar">
{tab_btns}</div>

{tab_contents}

<footer>
  17개국 YouTube Shorts 트렌딩 자동 수집 · 매일 17:00 KST<br>
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
    print(f"index.html 완료 — 총 {total}개 영상 / {len(all_data)}개국")


# ── 메인 ─────────────────────────────────────────────────
def main():
    print("=== YouTube Shorts 국가별 수집 시작 ===")

    # ① 모든 국가의 기존 영상 ID를 한 번에 수집 → 전역 중복 방지 세트
    global_seen: set[str] = set()
    for _, code, _, _, _ in COUNTRIES:
        data = load_json(json_path(code))
        global_seen.update(v["id"] for v in data["videos"])
    print(f"기존 전체 영상: {len(global_seen)}개 (중복 검사 기준)")

    all_data = []

    for name, code, geo, query, flag in COUNTRIES:
        print(f"\n[{flag} {name} / {code}]")
        p    = json_path(code)
        data = load_json(p)

        # ② 이번 실행에서 수집된 ID도 포함한 전역 세트로 중복 차단
        new = fetch_country(name, code, geo, query, global_seen)

        # ③ 새 영상 ID를 전역 세트에 등록 → 이후 국가에서 중복 수집 방지
        global_seen.update(v["id"] for v in new)

        if new:
            data["videos"] = new + data["videos"]
        save_json(p, data)
        all_data.append((name, code, flag, data))

    regenerate_html(all_data)
    print("\n=== 완료 ===")


if __name__ == "__main__":
    main()
