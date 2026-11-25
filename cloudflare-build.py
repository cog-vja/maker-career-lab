#!/usr/bin/env python3
"""Build a narrowly scoped Cloudflare Workers Static Assets site.

Run from the GitHub repository with:
    python3 cloudflare-build.py

Outputs dist/ (does not rewrite repository source files).
This script deliberately does not publish drafts, review JSON or EDINET secrets.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
from html import escape
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree as ET

from mcl_growth_batch import BATCH1_ARTICLES, BATCH1_COMPARISONS, BATCH1_PUBLISHED, BATCH1_REVISED
from mcl_revenue_layer import augment_output, REVENUE_ARTICLES

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "dist"
OLD = "https://cog-vja.github.io/maker-career-lab/"
NEW = "https://maker-career-lab.com/"
GA_OLD = "G-GKLVPVKKZ4"
GA_NEW = "G-G3EBC7ZZQ9"
GOOGLE_TAG = "GT-KT5GGMBR"
BATCH1_LAST_CHANGE = max(BATCH1_REVISED, BATCH1_PUBLISHED or BATCH1_REVISED)
COMPARISON_ARTICLES = {
    "fa-robotics-maker-comparison": ("6861", "6954", "6506", "6645"),
    "semiconductor-materials-comparison": ("4063", "3436", "4186", "5384"),
}
PHASE1_ARTICLES = {
    "production-management-career", "manufacturer-inhouse-se-career", *COMPARISON_ARTICLES,
}
# The original main deployment completed at 22:52 JST on November 24.
# The revision date records an editorial edit, independent of rollout time.
PHASE1_PUBLISHED = "2026-11-24"
PHASE1_REVISED = "2026-11-24"
FINANCIAL_TABLE_MARKER = "<!-- MCL_PHASE1_FINANCIAL_TABLE -->"
AFFILIATE_MARKER = "<!-- MCL_PHASE1_AFFILIATE -->"

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


def assert_dataset(source: Path) -> list[dict]:
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
    return data


def financial_range(values, number_format):
    """Describe the endpoints at the same precision as the displayed table."""
    if len(values) < 2:
        return None
    ordered = [(name, format(value, number_format)) for name, value in sorted(values, key=lambda row: row[1])]
    low = ordered[0][1]
    high = ordered[-1][1]
    if low == high:
        return f"掲載値は表示桁でいずれも {low}"
    low_names = "・".join(name for name, value in ordered if value == low)
    high_names = "・".join(name for name, value in ordered if value == high)
    return f"{low_names}の {low} から、{high_names}の {high}"


def build_financial_table(html: str, codes: tuple[str, ...], dataset: list[dict]) -> str:
    if html.count(FINANCIAL_TABLE_MARKER) != 1:
        raise RuntimeError(f"財務比較表の差し込み位置が一意ではありません: {codes}")
    companies = {str(row["id"]): row for row in dataset}
    rows = []
    sources = []
    standards = {"JP_GAAP": "日本基準", "IFRS": "IFRS", "US_GAAP": "米国基準"}
    salary_values = []
    margins_by_standard = {standard: [] for standard in standards}

    def number(value):
        return type(value) in (int, float) and math.isfinite(value)

    show_age = any(number(companies.get(code, {}).get("averageAge")) for code in codes)
    for code in codes:
        company = companies.get(code)
        if not company:
            raise RuntimeError(f"比較記事の企業が公開データにありません: {code}")
        doc_id = company.get("sourceDocId") or ""
        if not re.fullmatch(r"S[A-Z0-9]{7,15}", doc_id) or not re.fullmatch(
            r"[0-9a-f]{64}", company.get("sourceSha256") or ""
        ):
            raise RuntimeError(f"比較記事の出典情報を確認できません: {code}")
        name = escape(company["name"])
        revenue = company.get("revenue")
        profit = company.get("operatingProfit")
        salary = company.get("averageSalary")
        age = company.get("averageAge")
        standard = company.get("accountingStandard")
        scope = company.get("scope") or "範囲未記録"
        salary_scope = company.get("salaryScope") or "範囲未記録"
        # Use the vetted operating-profit field only. Never substitute net
        # income, segment profit, adjusted profit, or another definition.
        margin = "未取得"
        if standard in standards and number(revenue) and revenue > 0 and number(profit):
            calculated = 100 * profit / revenue
            margin = f"{calculated:,.2f}%"
            margins_by_standard[standard].append((name, calculated))
        revenue_label = f"{revenue:,.2f}" if number(revenue) else "未取得"
        salary_label = f"{salary:,.1f}" if number(salary) else "未取得"
        if number(salary) and salary_scope == "提出会社単体":
            salary_values.append((name, salary))
        age_label = f"{age:,.1f}" if number(age) else "未取得"
        age_cell = f"<td>{age_label}</td>" if show_age else ""
        period = escape(company.get("period") or "未記録")
        verified = escape(company.get("verifiedAt") or "記録なし")
        rows.append(
            f'<tr><th scope="row">{name}（{code}）</th>'
            f"<td>{salary_label}</td><td>{margin}</td><td>{revenue_label}</td>{age_cell}</tr>"
        )
        sources.append(
            f"<dt>{name}（{code}）</dt><dd>通期：{period} ／ "
            f'{escape(standards.get(standard, "会計基準未記録"))}<br>'
            f"財務：{escape(scope)} ／ 給与：{escape(salary_scope)}<br>"
            f'EDINET書類ID：<a href="https://disclosure2.edinet-fsa.go.jp/">{doc_id}</a> ／ '
            f"照合日：{verified}</dd>"
        )

    headings = ["提出会社（証券コード）", "平均年間給与（万円）", "営業利益率", "売上高・売上収益（億円）"]
    if show_age:
        headings.append("平均年齢（歳）")
    header = "".join(f'<th scope="col">{heading}</th>' for heading in headings)
    age_attr = " data-mcl-average-age" if show_age else ""
    table = (
        '<p class="mcl-table-swipe-hint" id="mcl-financial-scroll-hint">狭い画面では表を横にスクロールできます</p>'
        '<div class="table-scroll" tabindex="0" role="region" aria-labelledby="mcl-financial-caption" '
        'aria-describedby="mcl-financial-scroll-hint">'
        f'<table class="mcl-financial-table"{age_attr}>'
        '<caption id="mcl-financial-caption">有価証券報告書に基づく4社の通期比較</caption>'
        f"<thead><tr>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
        '<details class="mcl-financial-sources"><summary>決算期・会計基準・EDINETの出典を確認</summary>'
        f"<dl>{''.join(sources)}</dl></details>"
    )

    findings = []
    salary_range = financial_range(salary_values, ",.1f")
    if salary_range:
        findings.append(f"<li>提出会社単体の平均年間給与は {salary_range} 万円です。</li>")
    for standard, margins in margins_by_standard.items():
        margin_range = financial_range(margins, ",.2f")
        if margin_range:
            findings.append(f"<li>{standards[standard]}の{len(margins)}社では、営業利益率は {margin_range}％です。</li>")
    comparison = ""
    if findings:
        comparison = (
            '<div class="keypoint" id="mcl-financial-findings">'
            '<strong>表から読み取れる差</strong>'
            f"<ul>{''.join(findings)}</ul>"
            "<p>利益率の比較は会計基準が同じ企業に絞っています。"
            "決算期や事業構成、給与集計に含まれる社員の構成は企業ごとに異なります。</p></div>"
        )
    return html.replace(FINANCIAL_TABLE_MARKER, table + comparison)


def add_article_dates(html: str, published: str | None, revised: str) -> str:
    heading = re.search(r"<h1\b[^>]*>.*?</h1>", html, re.S)
    if heading is None:
        raise RuntimeError("公開記事の見出しがありません")
    revised_label = f'最終更新日 <time datetime="{revised}">{revised}</time>'
    if published:
        dates = f'公開日 <time datetime="{published}">{published}</time> ／ ' + revised_label
    else:
        dates = f'最終編集日 <time datetime="{revised}">{revised}</time>'
    dates = f'\n<p class="muted" id="mcl-article-dates">{dates}</p>'
    html = html[:heading.end()] + dates + html[heading.end():]

    def stamp_article(match):
        data = json.loads(match[2])
        if data.get("@type") != "Article":
            return match[0]
        data["dateModified"] = revised
        if published:
            data["datePublished"] = published
        return match[1] + json.dumps(data, ensure_ascii=False) + match[3]

    return re.sub(r'(<script type="application/ld\+json">)(.*?)(</script>)',
                  stamp_article, html, flags=re.S)


def phase1_affiliate_creative(comparison: bool, preview: bool) -> str:
    if preview:
        return '<p class="mcl-phase1-ad-preview">プレビューでは広告リンクと計測を停止しています。</p>'

    if comparison:
        # The compact One Career creative is also used by the existing widget.
        source = (ROOT / "onecareer-ads.js").read_text(encoding="utf-8")
        pattern = r'class="mcl-onecareer-floating__ad">\s*(<a\b[^>]*>\s*<img\b[^>]*></a>\s*<img\b[^>]*>)\s*</div>'
        program = "onecareer"
    else:
        source = (ROOT / "articles" / "manufacturer-engineer-agent-selection.html").read_text(encoding="utf-8")
        pattern = r'class="mcl-makersjob-action">\s*(<a\b[^>]*>[^<]+</a>)\s*</p>\s*(<img\b[^>]*>)'
        program = "makersjob"
    matches = list(re.finditer(pattern, source))
    if len(matches) != 1 or 'href="https://px.a8.net/svt/ejp?' not in matches[0][1]:
        raise RuntimeError(f"Phase 1広告の既存素材を一意に確認できません: {program}")
    # Keep the complete anchor, banner (if present), and impression image intact.
    return f'<div class="mcl-phase1-ad-direct mcl-phase1-ad-{program}">' + "\n".join(matches[0].groups()) + "</div>"


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
    # Canonical and structured metadata must describe the same *published* URL.
    # Only normalize a JSON-LD mainEntityOfPage URL on our own domain;
    # never rewrite partner links, publisher metadata, or A8 creative markup.
    html = re.sub(
        r'("mainEntityOfPage"\s*:\s*")https://maker-career-lab\.com/[^"\s]+("\s*)',
        lambda m: m.group(1) + expected + m.group(2),
        html,
    )
    # Likewise, normalise an explicit Open Graph article URL when present.
    html = re.sub(
        r'(<meta\s+property=["\']og:url["\']\s+content=["\'])https://maker-career-lab\.com/[^"\']+(["\'])',
        lambda m: m.group(1) + expected + m.group(2),
        html,
        flags=re.I,
    )
    # Render the short featured rail in HTML so it also works without JavaScript.
    if path.relative_to(ROOT).as_posix() == "index.html":
        html = add_featured_articles(html)
    # The published correlation report includes a sample of early-stage firms
    # with tiny revenue denominators. Show a transparent sensitivity check,
    # without deleting or silently excluding any source records.
    if path.relative_to(ROOT).as_posix() == "articles/salary-correlation.html":
        html = add_margin_sensitivity_note(html, ROOT / "company-data.js")
    return html



def add_featured_articles(html: str) -> str:
    pattern = r'(<div class="article-list">)(.*?)(</div>)'
    matches = list(re.finditer(pattern, html, re.S))
    if len(matches) != 1:
        raise RuntimeError(f"記事一覧コンテナが想定外です: {len(matches)}")
    match = matches[0]
    existing = {
        card[2]: card[1] for card in re.finditer(
            r'(<a class="article-tile" href="articles/([^"/]+)">.*?</a>)', match[2], re.S
        )
    }
    cards = [
        '<a class="article-tile" href="articles/manufacturer-inhouse-se-career">'
        '<span class="tag">製造業IT・転職</span><h3>メーカー社内SE・工場DXへの転職</h3>'
        '<p>運用、ERP、MES、DX企画の担当範囲と求人票の見方。</p></a>',
        '<a class="article-tile" href="articles/fa-robotics-maker-comparison">'
        '<span class="tag">FA・企業比較</span><h3>FAメーカー4社の年収・利益率を比較</h3>'
        '<p>キーエンス、ファナック、安川電機、オムロンの数字と仕事を比較。</p></a>',
        *(existing[slug] for slug in ("salary-market", "manufacturer-profit", "industry-compare")),
        '<a id="mcl-stage2-article-semi" class="article-tile" '
        'href="articles/semiconductor-equipment-salary-profit">'
        '<span class="tag">半導体関連・企業比較</span>'
        '<h3>半導体製造装置・検査関連9社の平均年収と営業利益率</h3>'
        '<p>ディスコ・東京エレクトロンなどを比較。単体給与と連結利益率の違いも解説。</p></a>',
    ]
    rail = '<div class="article-list" data-mcl-featured>' + "\n".join(cards) + match[3]
    return html[:match.start()] + rail + html[match.end():]


def margin_pearson(dataset: list[dict]) -> tuple[float, float, int, int]:
    """Current margin/salary correlation and transparent <-100% sensitivity."""
    pairs = []
    for row in dataset:
        rev, profit, salary = row.get("revenue"), row.get("operatingProfit"), row.get("averageSalary")
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (rev, profit, salary)):
            continue
        if rev <= 0 or salary <= 0:
            continue
        pairs.append((100 * profit / rev, salary))
    if len(pairs) < 30:
        raise RuntimeError("感度分析の母集団が不足しています")
    kept = [(m, salary) for m, salary in pairs if m >= -100]
    if len(kept) < 30:
        raise RuntimeError("感度分析で残る母集団が不足しています")

    def pearson(vals: list[tuple[float, float]]) -> float:
        n = len(vals)
        mx = sum(x for x, _ in vals) / n
        my = sum(y for _, y in vals) / n
        cov = sum((x-mx)*(y-my) for x,y in vals)
        var_x = sum((x-mx)**2 for x,_ in vals)
        var_y = sum((y-my)**2 for _,y in vals)
        denom = math.sqrt(var_x) * math.sqrt(var_y)
        return cov/denom if denom else 0.0

    return pearson(pairs), pearson(kept), len(pairs), len(kept)


def add_margin_sensitivity_note(html: str, source: Path) -> str:
    """Add a labeled secondary calculation; retain the original primary table."""
    if 'id="mcl-margin-sensitivity"' in html:
        return html
    match = re.search(r"window\.MCL_COMPANIES\s*=\s*(\[[\s\S]*?\])\s*;",source.read_text(encoding="utf-8"))
    if not match:
        raise RuntimeError("相関感度分析に必要な企業データがありません")
    raw = json.loads(match.group(1))
    basic, restricted, count, kept = margin_pearson(raw)
    omitted = count - kept
    note = (
        '<div id="mcl-margin-sensitivity" class="mcl-report-note" role="note">'
        '<strong>補足：営業利益率の相関係数は外れ値の影響に注意</strong>'
        f'<p>公開データ全{count:,}社での営業利益率と平均給与のピアソン相関は '
        f'<strong>{basic:+.2f}</strong>です。一方、営業利益率がマイナス100%未満の'
        f'{omitted}社を除く感度分析では、残り{kept:,}社で '
        f'<strong>{restricted:+.2f}</strong>となります。</p>'
        '<p>売上が非常に小さい研究開発段階の企業では、営業利益率の分母が小さく、'
        '赤字率の絶対値が極端に大きくなる場合があります。'        'ここでの除外は結果の頑健性を確かめるための<strong>比較用の再計算</strong>であり、'
        '元の相関表から企業を削除したものではありません。閾値は営業利益率がマイナス100%未満です。'
        '給与と利益率の因果関係を示すものではありません。</p></div>'
    )
    # Insert directly after the method statement; calculation table remains unchanged.
    needle = '相関は因果関係を意味しません。</p>'
    if html.count(needle) != 1:
        raise RuntimeError("相関記事の注記挿入位置が見つかりません")
    return html.replace(needle, needle + note, 1)


def transform_onecareer(js: str) -> str:
    """Keep A8 creative exactly intact; accept both legacy and clean paths."""
    old = r"\.html$"
    if js.count(old) != 2:
        raise RuntimeError("ワンキャリアの表示条件が想定外です")
    rewritten = js.replace(old, r"(?:\.html)?$")
    # The tracking href/image/pixel strings are not modified by this change.
    if js.count("https://px.a8.net/") != rewritten.count("https://px.a8.net/"):
        raise RuntimeError("広告リンク数が変化しました")
    return rewritten


def configure_production_tag(path: Path, content_group: str | None = None) -> None:
    """Use the linked Google tag and suppress delivery to its legacy destination."""
    html = path.read_text(encoding="utf-8").replace(GA_OLD, GA_NEW)
    loader = f"https://www.googletagmanager.com/gtag/js?id={GA_NEW}"
    if html.count(loader) != 1:
        raise RuntimeError(f"{path}: GA4 loader must appear exactly once")
    html = html.replace(loader, f"https://www.googletagmanager.com/gtag/js?id={GOOGLE_TAG}")
    # The shared tag otherwise sends to both destinations. Disable the old ID
    # before config and skip the legacy script's additional config call.
    config_args = json.dumps(GOOGLE_TAG)
    if content_group:
        config_args += "," + json.dumps({"content_group": content_group}, separators=(",", ":"))
    bootstrap = (
        f'window["ga-disable-{GA_OLD}"]=true;'
        f'gtag("config",{config_args});'
        'window.__mclGa4NewDestinationConfigured=true'
    )
    html, count = re.subn(
        rf"""gtag\s*\(\s*['"]config['"]\s*,\s*['"]{GA_NEW}['"]\s*\)""",
        bootstrap,
        html,
    )
    if count != 1:
        raise RuntimeError(f"{path}: GA4 config must appear exactly once")
    path.write_text(html, encoding="utf-8")


def transform_analytics(js: str) -> str:
    """Normalize location-path checks for extensionless Workers HTML routes.

    The production HTML sets the destination guard before this script runs.
    """
    if GA_NEW not in js:
        raise RuntimeError("analytics-events.js に新GA4の設定がありません")
    if GA_OLD in js:
        raise RuntimeError("analytics-events.js に旧GA4 IDが残っています")
    return js.replace(r"\.html$", r"(?:\.html)?$")


def make_sitemap(raw: str, html_paths: list[str]) -> str:
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ET.fromstring(raw)
    entries = root.findall("s:url", ns)
    if not entries:
        raise RuntimeError("sitemap.xml にURLがありません")
    newlocs = []
    phase1_urls = {NEW + "articles/" + slug for slug in PHASE1_ARTICLES}
    for entry in entries:
        loc = entry.find("s:loc", ns)
        if loc is None or not (loc.text or "").startswith(OLD):
            raise RuntimeError("sitemap.xml に想定外のURLがあります")
        newloc = as_clean_url(NEW + loc.text[len(OLD):])
        loc.text = newloc
        newlocs.append(newloc)
        if newloc in phase1_urls:
            lastmod = entry.find("s:lastmod", ns)
            if lastmod is None:
                lastmod = ET.SubElement(entry, f"{{{ns['s']}}}lastmod")
            lastmod.text = PHASE1_REVISED
    expected = {NEW if p == "index.html" else NEW + p[:-5] for p in html_paths}
    # New editorial pages are included in the published sitemap automatically.
    # Never silently add arbitrary or internal HTML paths.
    additions = expected - set(newlocs)
    batch1_urls = {NEW + "articles/" + slug for slug in BATCH1_ARTICLES}
    allowed = {NEW + p[:-5] for p in REVENUE_ARTICLES} | batch1_urls
    if not additions.issubset(allowed):
        raise RuntimeError(f"sitemap: 未登録ページがあります: {sorted(additions)}")
    for url in sorted(additions):
        node = ET.SubElement(root, f"{{{ns['s']}}}url")
        ET.SubElement(node, f"{{{ns['s']}}}loc").text = url
        ET.SubElement(node, f"{{{ns['s']}}}lastmod").text = BATCH1_LAST_CHANGE if url in batch1_urls else "2026-11-03"
        newlocs.append(url)
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
    required_articles = (*REVENUE_ARTICLES, *(f"articles/{slug}.html" for slug in BATCH1_ARTICLES))
    absent = [p for p in required_articles if not (ROOT / p).is_file()]
    if absent:
        raise RuntimeError("今回の新規記事が不足しています: " + ", ".join(absent))
    dataset = assert_dataset(ROOT / "company-data.js")
    # Workers Builds exposes the checked-out branch. A8 creatives must stay
    # inactive on unregistered preview domains. Local builds support offline tests.
    preview = os.environ.get("WORKERS_CI_BRANCH", "main") != "main"
    # Validate before replacing any previous dist tree.
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    copied_html = []
    financial_articles = COMPARISON_ARTICLES | BATCH1_COMPARISONS
    for item in [ROOT / p for p in ROOT_HTML] + article_files:
        relative = item.relative_to(ROOT)
        dest = OUT / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        html = transform_html(item.read_text(encoding="utf-8"), item)
        if item.parent.name == "articles":
            if item.stem in PHASE1_ARTICLES:
                html = add_article_dates(html, PHASE1_PUBLISHED, PHASE1_REVISED)
                if html.count(AFFILIATE_MARKER) != 1:
                    raise RuntimeError(f"Phase 1広告の配置が一意ではありません: {relative}")
                html = html.replace(AFFILIATE_MARKER, phase1_affiliate_creative(
                    item.stem in COMPARISON_ARTICLES, preview,
                ))
            if item.stem in BATCH1_ARTICLES:
                html = add_article_dates(html, BATCH1_PUBLISHED, BATCH1_LAST_CHANGE)
            if item.stem in financial_articles:
                html = build_financial_table(html, financial_articles[item.stem], dataset)
        dest.write_text(html, encoding="utf-8")
        copied_html.append(relative.as_posix())
    for name in STATIC_ASSETS:
        origin = ROOT / name
        dest = OUT / name
        if name == "analytics-events.js":
            dest.write_text(transform_analytics(origin.read_text(encoding="utf-8")), encoding="utf-8")
        elif name == "onecareer-ads.js":
            dest.write_text(transform_onecareer(origin.read_text(encoding="utf-8")), encoding="utf-8")
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
    augment_output(OUT, copied_html, ROOT)
    # Includes SEO pages generated by augment_output.
    for page in OUT.rglob("*.html"):
        if page.name != "404.html" and page.name not in OTHER_OPTIONAL:
            batch1 = BATCH1_ARTICLES.get(page.stem) if page.parent == OUT / "articles" else None
            configure_production_tag(page, batch1[3] if batch1 else None)
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
