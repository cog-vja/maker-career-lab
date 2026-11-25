"""Offline smoke tests for generated Cloudflare Static Assets after build.

These checks validate output contracts, NOT real browser/GA4 event receipt.
"""
from pathlib import Path
from xml.etree import ElementTree as ET
import json
import os
import re
import runpy
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
DOMAIN = "https://maker-career-lab.com/"
sys.path.insert(0, str(ROOT))
PHASE1_SLUGS = (
    "production-management-career",
    "manufacturer-inhouse-se-career",
    "fa-robotics-maker-comparison",
    "semiconductor-materials-comparison",
)


class PublicBuildSmoke(unittest.TestCase):
    def test_required_files_exist(self):
        for path in ("index.html", "company-check.html", "analytics-events.js", "company-data.js"):
            with self.subTest(path=path):
                self.assertTrue((DIST / path).is_file())

    def test_canonical_urls(self):
        for path, expected in (("index.html", DOMAIN), ("company-check.html", DOMAIN + "company-check")):
            with self.subTest(path=path):
                html = (DIST / path).read_text(encoding="utf-8")
                links = re.findall(r'<link[^>]*\brel=["\']canonical["\'][^>]*\bhref=["\']([^"\']+)', html, flags=re.I)
                self.assertEqual(links, [expected])
                self.assertNotIn("cog-vja.github.io/maker-career-lab/", html)

    def test_sitemap(self):
        tree = ET.parse(DIST / "sitemap.xml")
        urls = [node.text for node in tree.findall(".//{*}loc")]
        self.assertGreaterEqual(len(urls), 20)
        self.assertEqual(len(urls), len(set(urls)))
        self.assertTrue(all(url and url.startswith(DOMAIN) for url in urls))
        for slug in PHASE1_SLUGS:
            self.assertIn(DOMAIN + "articles/" + slug, urls)

    def test_phase1_article_metadata_and_discovery(self):
        home = (DIST / "index.html").read_text(encoding="utf-8")
        catalog = (DIST / "mcl-revenue.js").read_text(encoding="utf-8")
        sitemap = ET.parse(DIST / "sitemap.xml")
        lastmods = {node.findtext("{*}loc"): node.findtext("{*}lastmod")
                    for node in sitemap.findall("{*}url")}
        featured = re.search(r'<div class="article-list" data-mcl-featured>(.*?)</div>', home, re.S)[1]
        featured_slugs = re.findall(r'href="articles/([^"]+)"', featured)
        self.assertEqual(len(featured_slugs), 6)
        self.assertTrue({
            "manufacturer-salary-10m-career", "manufacturer-inhouse-se-career",
            "manufacturer-salary-ranking-2026", "physical-ai-manufacturing-careers",
            "data-center-manufacturing-careers",
        } <= set(featured_slugs))
        fallback = re.search(r'<div class="mcl-home-directory-fallback">(.*?)</div>', home, re.S)[1]
        fallback_slugs = re.findall(r'href="articles/([a-z0-9-]+)"', fallback)
        catalog_body = re.search(r'const catalog=\[(.*?)\n \];', catalog, re.S)[1]
        catalog_slugs = re.findall(r"""^\s*\[\s*['"]([a-z0-9-]+)['"]""", catalog_body, re.M)
        sitemap_slugs = {url.split("/")[-1] for url in lastmods if url.startswith(DOMAIN + "articles/")}
        self.assertEqual(len(fallback_slugs), len(sitemap_slugs))
        self.assertEqual(len(catalog_slugs), len(sitemap_slugs))
        self.assertEqual(set(fallback_slugs), sitemap_slugs)
        self.assertEqual(set(catalog_slugs), sitemap_slugs)
        titles, descriptions = set(), set()
        for slug in PHASE1_SLUGS:
            with self.subTest(slug=slug):
                html = (DIST / "articles" / (slug + ".html")).read_text(encoding="utf-8")
                url = DOMAIN + "articles/" + slug
                self.assertIn(f'<link rel="canonical" href="{url}"/>', html)
                self.assertIn(f'href="articles/{slug}"', fallback)
                self.assertIn(f"'{slug}'", catalog)
                structured = [json.loads(block) for block in re.findall(
                    r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
                article = next(item for item in structured if item["@type"] == "Article")
                breadcrumb = next(item for item in structured if item["@type"] == "BreadcrumbList")
                entity = article["mainEntityOfPage"]
                self.assertEqual(entity["@id"] if isinstance(entity, dict) else entity, url)
                self.assertEqual(breadcrumb["itemListElement"][-1]["item"], url)
                self.assertEqual(article["datePublished"], "2026-11-24")
                self.assertEqual(article["dateModified"], lastmods[url])
                displayed = re.search(r'id="mcl-article-dates">(.*?)</p>', html, re.S)[1]
                self.assertEqual(re.findall(r'<time datetime="([^"]+)">', displayed),
                                 [article["datePublished"], article["dateModified"]])
                self.assertIn(f'<meta property="og:url" content="{url}">', html)
                self.assertRegex(html, r'<meta property="og:image" content="https://')
                self.assertEqual(len(re.findall(r"<h1\b", html)), 1)
                title = re.search(r"<title>([^<]+)</title>", html)[1]
                description = re.search(r'<meta name="description" content="([^"]+)"', html)[1]
                self.assertNotIn(title, titles)
                self.assertNotIn(description, descriptions)
                titles.add(title)
                descriptions.add(description)

    def test_phase1_comparison_tables_use_published_dataset(self):
        js = (DIST / "company-data.js").read_text(encoding="utf-8")
        dataset = json.loads(re.search(r"window\.MCL_COMPANIES\s*=\s*(\[[\s\S]*?\])\s*;", js)[1])
        companies = {str(row["id"]): row for row in dataset}
        for slug, codes in (
            (PHASE1_SLUGS[2], ("6861", "6954", "6506", "6645")),
            (PHASE1_SLUGS[3], ("4063", "3436", "4186", "5384")),
        ):
            html = (DIST / "articles" / (slug + ".html")).read_text(encoding="utf-8")
            self.assertNotIn("MCL_PHASE1_FINANCIAL_TABLE", html)
            self.assertIn('scope="col">平均年間給与（万円）', html)
            self.assertIn('id="mcl-financial-findings"', html)
            self.assertIn('class="mcl-financial-sources"', html)
            self.assertEqual(
                "平均年齢（歳）</th>" in html,
                any(companies[code].get("averageAge") is not None for code in codes),
            )
            for code in codes:
                with self.subTest(slug=slug, code=code):
                    row = companies[code]
                    self.assertIn("（" + code + "）</th>", html)
                    self.assertIn(row["sourceDocId"], html)
                    self.assertIn(row["period"], html)
                    salary = row.get("averageSalary")
                    expected = f"{salary:,.1f}" if salary is not None else "未取得"
                    self.assertIn(f"<td>{expected}</td>", html)

    def test_phase1_affiliate_reuses_intact_creative(self):
        makers = (ROOT / "articles" / "manufacturer-engineer-agent-selection.html").read_text(encoding="utf-8")
        onecareer = (ROOT / "onecareer-ads.js").read_text(encoding="utf-8")
        preview = os.environ.get("WORKERS_CI_BRANCH", "main") != "main"
        for index, slug in enumerate(PHASE1_SLUGS):
            with self.subTest(slug=slug):
                html = (DIST / "articles" / (slug + ".html")).read_text(encoding="utf-8")
                self.assertNotIn("MCL_PHASE1_AFFILIATE", html)
                self.assertEqual(html.count('class="cta mcl-phase1-ad"'), 1)
                self.assertIn("PR｜アフィリエイト広告", html)
                self.assertIn('data-mcl-cta="service_guide"', html)
                self.assertNotIn("onecareer-ads.js", html)
                if preview:
                    self.assertIn('class="mcl-phase1-ad-preview"', html)
                    self.assertNotIn(".a8.net", html)
                    continue
                ads = re.findall(r'<a href="https://px\.a8\.net/[^"]+"[^>]*>.*?</a>', html, re.S)
                self.assertEqual(len(ads), 1)
                images = re.findall(r'<img\b[^>]*\.a8\.net[^>]*>', html)
                self.assertEqual(len(images), 1 if index < 2 else 2)
                source = makers if index < 2 else onecareer
                for tag in (*ads, *images):
                    self.assertIn(tag, source)

    def test_batch1_metadata_and_routes(self):
        batch = runpy.run_path(str(ROOT / "mcl_growth_batch.py"))
        catalog = batch["BATCH1_ARTICLES"]
        sitemap = ET.parse(DIST / "sitemap.xml")
        lastmods = {node.findtext("{*}loc"): node.findtext("{*}lastmod")
                    for node in sitemap.findall("{*}url")}
        home = (DIST / "index.html").read_text(encoding="utf-8")
        directory = re.search(r'<div class="mcl-home-directory-fallback">(.*?)</div>', home, re.S)[1]
        script = (DIST / "mcl-revenue.js").read_text(encoding="utf-8")
        self.assertNotIn("MCL_BATCH1_CATALOG", script)
        for slug, (category, _, _, content_group) in catalog.items():
            with self.subTest(slug=slug):
                url = DOMAIN + "articles/" + slug
                html = (DIST / "articles" / (slug + ".html")).read_text(encoding="utf-8")
                self.assertIn(f'<link rel="canonical" href="{url}"/>', html)
                self.assertIn(f'<meta property="og:url" content="{url}">', html)
                self.assertIn(f'href="articles/{slug}"', directory)
                self.assertIn(json.dumps((slug, category), ensure_ascii=False)[:-1] + ",", script)
                self.assertEqual(len(re.findall(r"<h1\b", html)), 1)
                options = json.dumps({"content_group": content_group}, separators=(",", ":"))
                self.assertIn(f'gtag("config","GT-KT5GGMBR",{options});', html)
                structured = [json.loads(block) for block in re.findall(
                    r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
                article = next(item for item in structured if item["@type"] == "Article")
                breadcrumbs = next(item for item in structured if item["@type"] == "BreadcrumbList")
                entity = article["mainEntityOfPage"]
                self.assertEqual(entity["@id"] if isinstance(entity, dict) else entity, url)
                self.assertEqual(breadcrumbs["itemListElement"][-1]["item"], url)
                self.assertEqual(article.get("datePublished"), batch["BATCH1_PUBLISHED"])
                self.assertEqual(article["dateModified"], lastmods[url])
                self.assertIn('data-mcl-cta="service_guide"', html)
                self.assertIn('data-mcl-cta="compare_tool"', html)
                enabled = (slug in batch["APPROVED_BATCH1_ADS"]
                           and os.environ.get("WORKERS_CI_BRANCH", "main") == "main")
                self.assertEqual(html.count('href="https://px.a8.net/'), int(enabled))
                if not enabled:
                    self.assertNotIn(".a8.net", html)
                self.assertNotIn("MCL_BATCH1_AFFILIATE", html)
                self.assertNotIn("MCL_COMPARISON_LEAD", html)
                if slug in batch["BATCH1_COMPARISONS"]:
                    self.assertIn('id="mcl-financial-findings"', html)
                    self.assertLess(html.index('id="mcl-financial-findings"'), html.index('class="mcl-financial-table"'))
                    for code in batch["BATCH1_COMPARISONS"][slug]:
                        self.assertIn(f"（{code}）</th>", html)
                self.assertNotIn("MCL_PHASE1_FINANCIAL_TABLE", html)

    def test_batch1_ad_approval_per_route_and_preview(self):
        build = runpy.run_path(str(ROOT / "cloudflare-build.py"))
        programs = build["BATCH1_AD_PROGRAMS"]
        render = build["render_batch1_affiliate"]
        for slug, program in programs.items():
            with self.subTest(slug=slug):
                source = (ROOT / "articles" / (slug + ".html")).read_text(encoding="utf-8")
                enabled = render(source, slug, frozenset({slug}), False)
                source_name = ("articles/manufacturer-engineer-agent-selection.html"
                               if program == "makers_job" else "onecareer-ads.js")
                creative = (ROOT / source_name).read_text(encoding="utf-8")
                ads = re.findall(r'<a href="https://px\.a8\.net/[^"]+"[^>]*>.*?</a>', enabled, re.S)
                images = re.findall(r'<img\b[^>]*\.a8\.net[^>]*>', enabled)
                self.assertEqual(len(ads), 1)
                self.assertEqual(len(images), 1 if program == "makers_job" else 2)
                self.assertTrue(all(tag in creative for tag in ads + images))
                self.assertIn("PR｜この記事にはアフィリエイト広告が含まれます。", enabled)
                self.assertIn("PR｜アフィリエイト広告", enabled)
                self.assertIn('data-mcl-cta="service_guide"', enabled)
                for approved, preview in ((frozenset(), False), (frozenset({slug}), True)):
                    suppressed = render(source, slug, approved, preview)
                    self.assertNotIn(".a8.net", suppressed)
                    self.assertIn('data-mcl-cta="service_guide"', suppressed)

    def test_salary_analysis_matches_published_dataset(self):
        js = (DIST / "company-data.js").read_text(encoding="utf-8")
        dataset = json.loads(re.search(r"window\.MCL_COMPANIES\s*=\s*(\[[\s\S]*?\])\s*;", js)[1])
        salaries = [row["averageSalary"] for row in dataset
                    if row.get("salaryScope") == "提出会社単体"
                    and isinstance(row.get("averageSalary"), (float, int)) and row["averageSalary"] > 0
                    and re.fullmatch(r"S[A-Z0-9]{7,15}", row.get("sourceDocId") or "")
                    and re.fullmatch(r"[0-9a-f]{64}", row.get("sourceSha256") or "")]
        html = (DIST / "articles/manufacturer-salary-10m-career.html").read_text(encoding="utf-8")
        count = sum(value >= 1000 for value in salaries)
        self.assertIn(f"1,000万円以上は{count:,}社／{len(salaries):,}社（{count / len(salaries):.1%}）", html)
        self.assertNotIn("MCL_BATCH1_SALARY", html)
        chart = re.search(r'<ul class="mcl-salary-distribution"[^>]+>(.*?)</ul>', html, re.S)[1]
        bars = re.findall(r'<strong>([\d,]+)社（([\d.]+%)）</strong>', chart)
        intervals = ((0, 800), (800, 1000), (1000, 1200), (1200, float("inf")))
        expected = [sum(lo <= value < hi for value in salaries) for lo, hi in intervals]
        self.assertEqual(bars, [(f"{n:,}", f"{n / len(salaries):.1%}") for n in expected])

    def test_built_analytics_route_compatibility(self):
        js = (DIST / "analytics-events.js").read_text(encoding="utf-8")
        self.assertIn(r"company-check(?:\.html)?$", js)
        self.assertNotIn(r"company-check\.html$", js)
        self.assertIn("G-G3EBC7ZZQ9", js)
        self.assertNotIn("G-GKLVPVKKZ4", js)
        for event in ("company_compare_link_click", "mcl_article_to_tool_click", "company_compare_complete", "affiliate_click"):
            self.assertIn(event, js)

    def test_built_analytics_event_behavior(self):
        result = subprocess.run(
            ["node", "--test", str(ROOT / "tests" / "analytics-events.test.cjs")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_google_tag_bootstrap(self):
        for path in DIST.rglob("*.html"):
            if path.name in ("404.html", "google551bf0fb86f23e67.html"):
                continue
            with self.subTest(path=path):
                html = path.read_text(encoding="utf-8")
                self.assertEqual(html.count("gtag/js?id=GT-KT5GGMBR"), 1)
                self.assertNotIn("gtag/js?id=G-", html)
                self.assertRegex(
                    html,
                    r'window\["ga-disable-G-GKLVPVKKZ4"\]=true;gtag\("config","GT-KT5GGMBR"'
                    r'(?:,\{"content_group":"batch1_(?:career|comparison|growth)"\})?\);'
                    r'window\.__mclGa4NewDestinationConfigured=true',
                )

    def test_no_internal_release_files(self):
        forbidden = {".git", ".github", ".env", "AGENTS.md", "README-PDCA.md"}
        for path in DIST.rglob("*"):
            if path.is_file():
                relative = path.relative_to(DIST).as_posix()
                self.assertNotIn(relative.split("/")[0], forbidden, relative)
                self.assertFalse(relative.endswith((".py", ".yml", ".yaml")), relative)
        self.assertIn("X-Robots-Tag: noindex", (DIST / "_headers").read_text())

    def test_monthly_update_is_pr_only(self):
        yaml_text = (ROOT / ".github/workflows/edinet-v325-monthly-review.yml").read_text()
        self.assertNotIn("git push origin HEAD:main", yaml_text)
        self.assertIn("peter-evans/create-pull-request", yaml_text)
        self.assertIn("MCL_PDCA_PR_TOKEN", yaml_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
