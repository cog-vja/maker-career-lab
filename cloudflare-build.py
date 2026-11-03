#!/usr/bin/env python3
"""Build a narrowly scoped Cloudflare Workers Static Assets site.

Run from the GitHub repository with:
    python3 cloudflare-build.py

Outputs dist/ (does not rewrite repository source files).
This script deliberately does not publish drafts, review JSON or EDINET secrets.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "dist"
OLD = "https://cog-vja.github.io/maker-career-lab/"
NEW = "https://maker-career-lab.com/"
GA_OLD = "G-GKLVPVKKZ4"
GA_NEW = "G-G3EBC7ZZQ9"

# Strict allowlist: these are the ONLY root assets that go online.
ROOT_HTML = (
    "index.html", "company-check.html", "about.html", "agent-guide.html",
    "career-options.html", "contact.html", "disclosure.html", "industry-compare.html",
    "it-scm-career.html", "manufacturer-profit.html", "privacy.html", "salary-market.html",
)
STATIC_ASSETS = (
    "style.css", "onecareer-ads.css", "onecareer-ads.js",
    "affiliate-config.js", "affiliate-render.js", "analytics-events.js",
    "company-data.js", "company-compare.js", "contact-config.js",
    "contact-form-v321.js", "favicon.ico", "favicon.png", "apple-touch-icon.png",
    "site-logo-192.png", "og-image.png",
)
OTHER_OPTIONAL = ("google551bf0fb86f23e67.html",)


def assert_dataset(source: Path) -> None:
    text = source.read_text(encoding="utf-8")
    match = re.search(r"window\.MCL_COMPANIES\s*=\s*(\[[\s\S]*?\])\s*;", text)
    if not match:
        raise RuntimeError("company-data.js: MCL_COMPANIES を確認できません")
    data = json.loads(match.group(1))
    ids = [str(row.get("id")) for row in data]
    if len(data) < 1000 or len(ids) != len(set(ids)):
        raise RuntimeError(f"企業データが想定と異なります: {len(data)}社 / 重複{len(ids)-len(set(ids))}件")
    if any(str(row.get("id")) == "6390" for row in data):
        raise RuntimeError("保留企業6390が公開データに含まれています")
    print(f"[OK] 企業データ: {len(data)}社、証券コード重複なし")


def as_clean_url(url: str) -> str:
    """Switch local page links to Workers Static Assets' extensionless URLs."""
    if url.startswith(("#", "mailto:", "tel:", "javascript:", "data:", "//")):
        return url
    parts = urlsplit(url)
    if parts.scheme and not parts.netloc:
        return url
    if parts.netloc and parts.netloc != "maker-career-lab.com":
        return url
    path = parts.path
    if path.endswith("index.html"):
        path = path[: -len("index.html")] or "./"
    elif path.endswith(".html") and "google551bf0fb86f23e67" not in path:
        path = path[:-5]
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def transform_html(html: str, path: Path) -> str:
    html = html.replace(OLD, NEW)
    # One production property only. Keep the source GitHub Pages site intact.
    html = html.replace(GA_OLD, GA_NEW)
    if GA_OLD in html or html.count(GA_NEW) < 2:
        raise RuntimeError(f"{path}: GA4移行に失敗しました")
    if not re.search(r"gtag\s*\(\s*['\"]config['\"]\s*,\s*['\"]" + GA_NEW, html):
        raise RuntimeError(f"{path}: 新しいGA4 configタグがありません")
    # Rewrite only anchor href values; scripts/css/external links remain intact.
    def link_rewrite(m: re.Match) -> str:
        url = m.group(2)
        if url.startswith(OLD):
            url = NEW + url[len(OLD):]
        return m.group(1) + as_clean_url(url) + m.group(3)
    html = re.sub(r'(<a\b[^>]*?\bhref\s*=\s*["\'])([^"\']+)(["\'])', link_rewrite, html, flags=re.I)
    # Each canonical is extensionless (Workers auto-trailing-slash rewrites .html).
    expected = NEW if path.relative_to(ROOT).as_posix() == "index.html" else NEW + path.relative_to(ROOT).as_posix()[:-5]
    found = re.findall(r'<link\b[^>]*\brel\s*=\s*["\']canonical["\'][^>]*>', html, flags=re.I)
    if len(found) > 1:
        raise RuntimeError(f"{path}: canonicalが複数あります")
    if found:
        html = html.replace(found[0], f'<link rel="canonical" href="{expected}"/>')
    else:
        html = re.sub(r'</head>', f'<link rel="canonical" href="{expected}"/></head>', html, count=1, flags=re.I)
    if expected not in html:
        raise RuntimeError(f"{path}: canonical設定に失敗しました")
    return html


def transform_analytics(js: str) -> str:
    """Normalize location-path checks for extensionless Workers HTML routes.

    The existing new-GA4 destination guard checks dataLayer, so after HTML
    uses GA_NEW, it will not duplicate its config event. Preserve it intact.
    """
    if GA_NEW not in js:
        raise RuntimeError("analytics-events.js に新GA4の設定がありません")
    if GA_OLD in js:
        raise RuntimeError("analytics-events.js に旧GA4 IDが残っています")
    return js.replace(r"\.html$", r"(?:\.html)?$")


def make_sitemap(raw: str, html_paths: list[str]) -> str:
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ET.fromstring(raw)
    locs = root.findall("s:url/s:loc", ns)
    if not locs:
        raise RuntimeError("sitemap.xml にURLがありません")
    newlocs = []
    for loc in locs:
        if not (loc.text or "").startswith(OLD):
            raise RuntimeError("sitemap.xml に想定外のURLがあります")
        newloc = as_clean_url(NEW + loc.text[len(OLD):])
        loc.text = newloc
        newlocs.append(newloc)
    expected = {NEW if p == "index.html" else NEW + p[:-5] for p in html_paths}
    if set(newlocs) != expected or len(newlocs) != len(expected):
        raise RuntimeError(f"sitemap不一致: 実際{len(newlocs)}URL / HTML{len(expected)}件")
    ET.register_namespace("", ns["s"])
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def build() -> None:
    if not (ROOT / ".github" / "workflows").is_dir():
        raise RuntimeError("GitHubのリポジトリ直下に置いて実行してください")
    names = list(ROOT_HTML) + list(STATIC_ASSETS) + ["robots.txt", "sitemap.xml"]
    missing = [p for p in names if not (ROOT / p).is_file()]
    if missing:
        raise RuntimeError("必要な公開ファイルがありません: " + ", ".join(missing))
    article_files = sorted((ROOT / "articles").glob("*.html"))
    if len(article_files) < 8:
        raise RuntimeError("記事数が想定より少ないため中断します")
    assert_dataset(ROOT / "company-data.js")
    # Validate before replacing any previous dist tree.
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    copied_html = []
    for item in [ROOT / p for p in ROOT_HTML] + article_files:
        relative = item.relative_to(ROOT)
        dest = OUT / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(transform_html(item.read_text(encoding="utf-8"), item), encoding="utf-8")
        copied_html.append(relative.as_posix())
    for name in STATIC_ASSETS:
        origin = ROOT / name
        dest = OUT / name
        if name == "analytics-events.js":
            dest.write_text(transform_analytics(origin.read_text(encoding="utf-8")), encoding="utf-8")
        else:
            shutil.copyfile(origin, dest)
    for name in OTHER_OPTIONAL:
        if (ROOT / name).is_file():
            shutil.copyfile(ROOT / name, OUT / name)
    (OUT / "sitemap.xml").write_text(make_sitemap((ROOT / "sitemap.xml").read_text(encoding="utf-8"), copied_html), encoding="utf-8")
    (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\nSitemap: " + NEW + "sitemap.xml\n", encoding="utf-8")
    # Workers Static Assets supports _headers. Keep workers.dev out of Google;
    # do not noindex the actual purchased .com site.
    (OUT / "_headers").write_text(
        "/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n\n"
        "https://:worker.:account.workers.dev/*\n  X-Robots-Tag: noindex\n",
        encoding="utf-8")
    (OUT / "404.html").write_text(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="robots" content="noindex">'
        '<title>ページが見つかりません｜メーカーキャリアラボ</title></head><body>'
        '<main><h1>ページが見つかりません</h1><p><a href="/">メーカーキャリアラボのトップへ戻る</a></p>'
        '</main></body></html>\n', encoding="utf-8")
    (OUT / "_redirects").write_text("/index / 301\n", encoding="utf-8")
    # Extra guard: past audits / sources / internal tools must never be served.
    paths = {p.relative_to(OUT).as_posix() for p in OUT.rglob("*") if p.is_file()}
    if any(p.startswith(("site-ready/", "site-update/", "site-reference/", "fixtures/", ".github/")) for p in paths):
        raise RuntimeError("公開禁止フォルダを検出しました")
    if any("cog-vja.github.io/maker-career-lab/" in (OUT / p).read_text(encoding="utf-8") for p in copied_html):
        raise RuntimeError("公開HTMLに旧GitHub PagesのURLが残っています")
    print(f"[OK] Cloudflare Workers Static Assets: HTML {len(copied_html)}件 / 公開ファイル {len(paths)}件")
    print("[OK] 新ドメイン: " + NEW + "  / 出力: dist/")
    print("[OK] GitHub Pagesの既存ファイルは変更していません")


if __name__ == "__main__":
    build()
