"""Offline smoke tests for generated Cloudflare Static Assets after build.

These checks validate output contracts, NOT real browser/GA4 event receipt.
"""
from pathlib import Path
from xml.etree import ElementTree as ET
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
DOMAIN = "https://maker-career-lab.com/"


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

    def test_built_analytics_route_compatibility(self):
        js = (DIST / "analytics-events.js").read_text(encoding="utf-8")
        self.assertIn(r"company-check(?:\.html)?$", js)
        self.assertNotIn(r"company-check\.html$", js)
        self.assertIn("G-G3EBC7ZZQ9", js)
        self.assertNotIn("G-GKLVPVKKZ4", js)
        for event in ("company_compare_link_click", "mcl_article_to_tool_click", "company_compare_complete", "affiliate_click"):
            self.assertIn(event, js)

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
