#!/usr/bin/env python3
"""Open-Source Necromancer — этап 1: поиск и оценка заброшенных open-source проектов.

Только чтение: всё идёт через `gh api` (GitHub REST), ничего не создаётся и не публикуется.
Фильтры: звёзды 500..15000, нет пушей давно (или архив), строго пермиссивная лицензия,
языки C / C++ / Python, чистое алгоритмическое ядро. Потом оценка (score) по эвристикам.

Запуск:  python finder.py [--years 5] [--pages 3] [--deep 40] [--out ../out]
"""
import argparse, json, os, re, subprocess, sys, time, datetime, urllib.request, urllib.parse

PERMISSIVE = {"MIT": "mit", "Apache-2.0": "apache-2.0", "BSD-3-Clause": "bsd-3-clause", "BSD-2-Clause": "bsd-2-clause", "Unlicense": "unlicense"}
LANGS = ["C", "C++", "Python"]

# тематика: слова, по которым репозиторий считается «алгоритмическим ядром»
DOMAIN = {
    "compression": ["compress", "codec", "lz4", "lzma", "zlib", "huffman", "deflate", "entropy coder", "decompress", "bwt", "zstd", "brotli", "lzss", "rle"],
    "crypto": ["crypt", "hash", "cipher", "aes", "sha", "blake", "chacha", "rsa", "ecc", "curve25519", "signature", "argon", "scrypt", "bcrypt"],
    "dsp": ["dsp", "fft", "audio", "filter", "resampl", "wavelet", "mp3", "vorbis", "opus", "synth", "spectrum", "noise reduction", "pitch"],
    "physics": ["physics", "collision", "rigid body", "fluid", "verlet", "n-body", "soft body", "kinematics", "constraint solver"],
    "graphics": ["raytrac", "ray trac", "path trac", "renderer", "rasteriz", "mesh", "voxel", "noise", "perlin", "simplex", "procedural", "terrain", "marching"],
    "geometry": ["geometry", "polygon", "triangulat", "voronoi", "delaunay", "convex hull", "clipping", "bezier", "spline", "kd-tree", "kdtree", "bvh", "inverse kinematics", "quadtree", "octree"],
    "pathfinding": ["pathfind", "path find", "astar", "navmesh", "dijkstra", "jump point", "flow field"],
    "parser": ["parser", "lexer", "tokeniz", "regex", "grammar", "markdown", "expression evaluator", "bencode", "sexp"],
    "math": ["matrix", "linear algebra", "sparse", "bignum", "bigint", "numeric", "prng", "interpolat", "quaternion", "fixed-point", "bloom filter", "skip list", "hash table", "trie", "bitset", "rope"],
}
# тяжёлые зависимости/платформенный хлам: штраф
BAD_DEPS = ["qt", "gtk", "x11", "xlib", "wxwidgets", "directx", "win32", "mfc", "cocoa", "opengl", "sdl", "glut", "boost", "cuda", "opencl", "windows.h", "android", "ios "]
DEMAND = re.compile(r"\b(rust|wasm|webassembly|emscripten|64[- ]?bit|port(ing)?|python binding|node binding|ffi)\b", re.I)


def gh(path, params=None, retries=4):
    """GET через gh api; возвращает (json, заголовки-лимиты не нужны)."""
    cmd = ["gh", "api", "-X", "GET", path]
    for k, v in (params or {}).items():
        cmd += ["-f", f"{k}={v}"]
    for attempt in range(retries):
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if p.returncode == 0:
            try:
                return json.loads(p.stdout)
            except Exception:
                return None
        err = (p.stderr or "") + (p.stdout or "")
        if "rate limit" in err.lower() or "403" in err or "secondary" in err.lower():
            wait = 35 * (attempt + 1)
            print(f"  [лимит] жду {wait}с …", file=sys.stderr); time.sleep(wait); continue
        if "404" in err or "422" in err or "451" in err:
            return None
        time.sleep(2)
    return None


def search_repos(q, pages):
    out = []
    for page in range(1, pages + 1):
        d = gh("search/repositories", {"q": q, "sort": "stars", "order": "desc", "per_page": 100, "page": page})
        time.sleep(2.3)
        if not d or not d.get("items"):
            break
        out += d["items"]
        if len(d["items"]) < 100:
            break
    return out


ML_RE = re.compile(r"neural|deep[- ]?learn|tensorflow|pytorch|keras|caffe|mxnet|\bgan\b|reinforcement|machine[- ]learning|\bml\b|detection|segmentation|\bnlp\b|\bbert\b|transformer|recommend|dataset|tutorial|course|leetcode|interview|awesome|cheat|\bbook\b|learning|\bcnn\b|\brnn\b|\bgpt\b|chatbot|trading|bitcoin|blockchain|exploit|malware|ctf\b", re.I)
APP_RE = re.compile(r"\b(client|server|bot|app|apps|api|sdk|wrapper|plugin|gui|framework|website|extension|dashboard|scraper|crawler|library for (?:talking|connecting))\b", re.I)
_PATS = {}
def _pat(w):
    if w not in _PATS:
        e = re.escape(w)
        _PATS[w] = re.compile((r"\b" + e + r"\b") if len(w) <= 4 else (r"\b" + e), re.I)
    return _PATS[w]

def domain_hits(text):
    hits = []
    for dom, words in DOMAIN.items():
        if any(_pat(w).search(text) for w in words):
            hits.append(dom)
    return hits


def base_score(r, cutoff):
    """Быстрая оценка по метаданным (без дополнительных запросов)."""
    text = " ".join([r.get("name") or "", r.get("description") or "", " ".join(r.get("topics") or [])])
    if ML_RE.search(text):
        return None
    hits = domain_hits(text)
    if not hits:
        return None
    s = 0.0
    s += 18 * min(2, len(hits))                       # алгоритмическое ядро по теме
    if APP_RE.search(text): s -= 12                    # приложение/клиент/обёртка, а не чистый алгоритм
    stars = r["stargazers_count"]
    s += min(14, (stars - 500) / 700)                  # известность (культовость)
    if r.get("archived"): s += 6
    s += min(8, r.get("forks_count", 0) / 60)          # форки = живой спрос
    if r.get("open_issues_count", 0) >= 5: s += 4      # есть неотвеченное
    size_mb = r.get("size", 0) / 1024
    if size_mb > 60: s -= 14
    elif size_mb > 25: s -= 6
    lowtext = text.lower()
    if any(b in lowtext for b in BAD_DEPS): s -= 12
    if r.get("homepage") and "github.io" in (r.get("homepage") or ""): s -= 2
    return round(s, 1), hits


def deep_check(r):
    """Глубокая проверка: языки, дерево файлов (зависимости), спрос на Rust/WASM, живость."""
    full = r["full_name"]
    info = {"full_name": full}
    langs = gh(f"repos/{full}/languages") or {}
    tot = sum(langs.values()) or 1
    info["lang_mix"] = {k: round(v / tot, 2) for k, v in sorted(langs.items(), key=lambda kv: -kv[1])[:4]}
    core = sum(v for k, v in langs.items() if k in ("C", "C++", "Python", "C#", "Header")) / tot
    info["core_lang_share"] = round(core, 2)
    time.sleep(0.4)
    branch = r.get("default_branch") or "master"
    tree = gh(f"repos/{full}/git/trees/{branch}", {"recursive": "1"})
    files = [t["path"] for t in (tree or {}).get("tree", []) if t.get("type") == "blob"]
    info["files"] = len(files)
    low = " ".join(files).lower()
    bad = sorted({b for b in BAD_DEPS if re.search(r"(^|[/_\-.])" + re.escape(b.strip()) + r"([/_\-.]|$)", low)})
    info["bad_deps"] = bad
    info["has_tests"] = bool(re.search(r"(^|/)(tests?|testing|spec)(/|\.)", low))
    info["has_build"] = bool(re.search(r"(cmakelists|makefile|setup\.py|pyproject|meson\.build|configure\.ac)", low))
    info["has_license_file"] = bool(re.search(r"(^|/)(license|copying|unlicense)", low))
    info["src_files"] = sum(1 for f in files if re.search(r"\.(c|cc|cpp|cxx|h|hpp|py)$", f.lower()))
    time.sleep(0.4)
    # спрос: открытые issues про rust/wasm/64-bit/порт
    q = f"repo:{full} type:issue (rust OR wasm OR webassembly OR 64-bit OR port OR binding)"
    d = gh("search/issues", {"q": q, "per_page": 20})
    time.sleep(2.3)
    items = (d or {}).get("items", [])
    dem = [i for i in items if DEMAND.search((i.get("title") or "") + " " + (i.get("body") or "")[:400])]
    info["demand_issues"] = len(dem)
    info["demand_titles"] = [i["title"][:90] for i in dem[:3]]
    info["demand_unanswered"] = sum(1 for i in dem if i.get("comments", 0) == 0 and i.get("state") == "open")
    return info


def crates_conflict(name):
    """Есть ли уже крейт с таким именем / близким названием (только чтение crates.io)."""
    q = urllib.parse.quote(name.lower())
    req = urllib.request.Request(f"https://crates.io/api/v1/crates?q={q}&per_page=5", headers={"User-Agent": "oss-necromancer-finder (read-only)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            d = json.load(resp)
        return [(c["name"], c.get("downloads", 0)) for c in d.get("crates", [])]
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=5.0)
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--deep", type=int, default=40)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "out"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    cutoff_dt = datetime.date.today().replace(year=datetime.date.today().year - int(a.years))
    cutoff = cutoff_dt.isoformat()
    print(f"отсечка по активности: pushed < {cutoff}")

    pool = {}
    NEG = " ".join(f"-license:{x}" for x in ["gpl-2.0", "gpl-3.0", "agpl-3.0", "lgpl-2.1", "lgpl-3.0", "mpl-2.0", "other"])
    terms = sorted({w for words in DOMAIN.values() for w in words})
    for lang in LANGS:
        for term in terms:
            q = f'"{term}" in:name,description,topics stars:500..15000 pushed:<{cutoff} language:{lang} fork:false {NEG}'
            items = search_repos(q, 1)
            new = sum(1 for r in items if r["full_name"] not in pool)
            if items: print(f"{lang:7} {term:22} → {len(items):3} (новых {new})")
            for r in items:
                pool[r["full_name"]] = r
    print(f"всего уникальных: {len(pool)}")

    scored = []
    for r in pool.values():
        spdx = (r.get("license") or {}).get("spdx_id")
        if spdx not in PERMISSIVE:        # жёсткий барьер: GPL/AGPL/NOASSERTION отсекаются
            continue
        sc = base_score(r, cutoff)
        if sc is None:
            continue
        scored.append((sc[0], sc[1], r))
    scored.sort(key=lambda x: -x[0])
    print(f"после тематического фильтра: {len(scored)}")

    results = []
    for sc, hits, r in scored[: a.deep]:
        print(f"  глубокая проверка {r['full_name']}  (база {sc})")
        d = deep_check(r)
        total = sc
        total += min(18, d["demand_issues"] * 6) + min(6, d["demand_unanswered"] * 3)   # неудовлетворённый спрос
        total -= 10 * min(2, len(d["bad_deps"]))                                          # тяжёлые зависимости
        if d["core_lang_share"] < 0.6: total -= 10
        if d["has_tests"]: total += 4                                                     # есть эталонные тесты
        if d["src_files"] > 400: total -= 8                                               # слишком большой
        if d["src_files"] < 3: total -= 10
        res = {
            "repo": r["full_name"], "url": r["html_url"], "stars": r["stargazers_count"], "forks": r["forks_count"],
            "license": r["license"]["spdx_id"], "pushed": r["pushed_at"][:10], "archived": r["archived"],
            "lang": r.get("language"), "desc": (r.get("description") or "")[:140], "topics": r.get("topics", []),
            "domains": hits, "base": sc, "score": round(total, 1), "open_issues": r["open_issues_count"], **d,
        }
        results.append(res)
    results.sort(key=lambda x: -x["score"])

    # конфликт имён на crates.io только для финалистов
    for res in results[:15]:
        name = re.sub(r"[^a-z0-9]+", "-", res["repo"].split("/")[1].lower()).strip("-")
        res["crates_similar"] = crates_conflict(name)
        time.sleep(1.1)

    with open(os.path.join(a.out, "candidates.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    with open(os.path.join(a.out, "candidates.md"), "w", encoding="utf-8") as f:
        f.write(f"# Кандидаты Necromancer ({datetime.date.today()})\n\n")
        f.write(f"Фильтр: stars 500..15000, pushed < {cutoff}, лицензии {', '.join(PERMISSIVE)}, языки {', '.join(LANGS)}.\n\n")
        f.write("| # | Репозиторий | ★ | Лицензия | Последний push | Темы | Score | Спрос (issues) | Зависимости-риск | Тесты |\n|---|---|---|---|---|---|---|---|---|---|\n")
        for i, r in enumerate(results, 1):
            f.write(f"| {i} | [{r['repo']}]({r['url']}) | {r['stars']} | {r['license']} | {r['pushed']}{' (архив)' if r['archived'] else ''} | {', '.join(r['domains'])} | **{r['score']}** | {r['demand_issues']} | {', '.join(r['bad_deps']) or '—'} | {'да' if r['has_tests'] else 'нет'} |\n")
    print("готово:", os.path.abspath(os.path.join(a.out, "candidates.md")))


if __name__ == "__main__":
    main()
