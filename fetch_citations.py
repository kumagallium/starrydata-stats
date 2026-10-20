# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Fetch the list of works that cite the Starrydata papers, via OpenAlex.

For each tracked paper, pages through the OpenAlex "cites:" filter, de-duplicates
the citing works by OpenAlex ID, and writes output/citations.json. The dashboard
generator (generate_dashboard.py) picks this file up when present.

On any network / API failure the existing output/citations.json is left untouched
and the script exits 0 with a warning, so the daily job is never blocked. A
partial fetch never overwrites the file.

Usage:
    python fetch_citations.py
    uv run fetch_citations.py

Environment:
    OPENALEX_API_KEY   optional; sent as the api_key query parameter

Outputs:
    output/citations.json
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUT_PATH = BASE_DIR / "output" / "citations.json"

API = "https://api.openalex.org/works"
SELECT = "id,doi,title,publication_year,publication_date,authorships,primary_location,type"

# Tracked papers (hard-coded).
PAPERS = [
    {"key": "starrydata2025", "doi": "10.1080/27660400.2025.2506976", "openalex": "W4410542656",
     "title": "Starrydata: from published plots to shared materials data",
     "short": "Starrydata (2025)", "year": 2025,
     "authors": "Y. Katsura, M. Kumagai, T. Mato, Y. Takada, Y. Ando, E. Fujita, F. Hosono, E. Koyama, "
                "F. Mudasar, T. N. T. Phuong, N. Saito, Y. Sakamoto, A. Tanaka, D. Yana, K. Kimura, "
                "K. Tsuda, M. Demura",
     "journal": "Science and Technology of Advanced Materials: Methods 5, 1 (2025) 2506976"},
    {"key": "pbte2019", "doi": "10.1080/14686996.2019.1603885", "openalex": "W2948233954",
     "title": "Data-driven analysis of electron relaxation times in PbTe-type thermoelectric materials",
     "short": "PbTe τ (2019)", "year": 2019,
     "authors": "Y. Katsura, M. Kumagai, T. Kodani, M. Kaneshige, Y. Ando, S. Gunji, Y. Imai, H. Ouchi, "
                "K. Tobita, K. Kimura, K. Tsuda",
     "journal": "Science and Technology of Advanced Materials 20 (2019) 511–520"},
]

TAG_RE = re.compile(r"<[^>]+>")


def http_json(url: str, retries: int = 3) -> dict:
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "starrydata-stats-dashboard"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"request failed: {last}")


def fetch_citing(openalex_id: str, api_key: str) -> list:
    works, cursor = [], "*"
    while cursor:
        params = {"filter": f"cites:{openalex_id}", "per-page": "200", "cursor": cursor, "select": SELECT}
        if api_key:
            params["api_key"] = api_key
        data = http_json(API + "?" + urllib.parse.urlencode(params, safe=",:*"))
        works.extend(data.get("results", []))
        cursor = (data.get("meta") or {}).get("next_cursor")
        if not data.get("results"):
            break
    return works


def clean(s) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub("", s or "")).strip()


def normalize(w: dict, cites: list) -> dict:
    auths = w.get("authorships") or []
    names = [clean((a.get("author") or {}).get("display_name")) for a in auths]
    names = [n for n in names if n]
    src = ((w.get("primary_location") or {}).get("source") or {})
    doi = w.get("doi") or ""
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return {
        "id": w.get("id", ""),
        "doi": doi or None,
        "title": clean(w.get("title")) or "(untitled)",
        "year": w.get("publication_year"),
        "date": w.get("publication_date") or "",
        "authors": names[:3],
        "n_authors": len(auths),
        "venue": clean(src.get("display_name")),
        "type": w.get("type") or "",
        "cites": cites,
    }


def main() -> int:
    api_key = os.environ.get("OPENALEX_API_KEY", "")
    merged, counts = {}, {}
    try:
        for p in PAPERS:
            # OpenAlex occasionally mis-links references; a work cannot cite a paper
            # published after it, so drop citations dated before the cited paper's year.
            ws = [w for w in fetch_citing(p["openalex"], api_key)
                  if (w.get("publication_year") or p["year"]) >= p["year"]]
            counts[p["key"]] = len({w["id"] for w in ws})
            for w in ws:
                e = merged.setdefault(w["id"], (w, []))
                if p["key"] not in e[1]:
                    e[1].append(p["key"])
    except Exception as e:  # network / API failure: keep the existing file
        print(f"Warning: citation fetch failed ({e}); keeping existing {OUT_PATH.name}", file=sys.stderr)
        return 0

    works = [normalize(w, c) for w, c in merged.values()]
    works.sort(key=lambda w: w["date"], reverse=True)
    out = {
        "fetched_at": date.today().isoformat(),
        "source": "OpenAlex",
        "papers": [{"key": p["key"], "doi": p["doi"], "title": p["title"], "short": p["short"],
                    "authors": p["authors"], "journal": p["journal"],
                    "count": counts[p["key"]]} for p in PAPERS],
        "works": works,
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(OUT_PATH)
    print(f"Wrote {OUT_PATH}: " + ", ".join(f"{k}={v}" for k, v in counts.items()) + f", unique={len(works)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
