"""Exercise the built comparison screen offline. Requires Playwright Python."""
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


ORIGIN = "https://maker-career-lab.com"
TOOL = ORIGIN + "/company-check"
KEY = "mcl.compare.saved.v1"
EVENTS = {"company_comparison_save", "company_comparison_restore", "company_watchlist_open",
          "company_watchlist_remove"}


def local_assets(context, dist):
    def route(request):
        url = urlsplit(request.request.url)
        if url.hostname != "maker-career-lab.com":
            request.abort()
            return
        asset = dist / (url.path.lstrip("/") or "index.html")
        if not asset.is_file():
            asset = asset.with_suffix(".html")
        if asset.is_file():
            request.fulfill(path=asset)
        else:
            request.fulfill(status=404)
    context.route("**/*", route)


def events(page):
    return page.evaluate("Array.from(window.dataLayer || [], args => [args[0],args[1],args[2]])")


def saved_events(page):
    rows = [(name, data) for kind, name, data in events(page) if kind == "event" and name in EVENTS]
    assert all(data == {"tool": "company_check"} for _, data in rows)
    return [name for name, _ in rows]


def select_pair(page):
    page.locator("#name-a").fill("6861")
    page.locator("#name-b").fill("6954")
    page.locator("#compare-form button[type=submit]").click()
    assert page.locator("#metrics-body tr").count() == 5


def verify_layout(browser, dist, screenshots, engine):
    for width in (320, 375, 390, 430, 768, 1440):
        context = browser.new_context(viewport={"width": width, "height": 850}, service_workers="block")
        local_assets(context, dist)
        page = context.new_page()
        runtime_errors = []
        page.on("pageerror", lambda error: runtime_errors.append(str(error)))
        assert page.goto(TOOL, wait_until="load").ok
        assert saved_events(page) == []
        page.locator("#demo").click()
        assert not page.locator("#compare-save-pair").is_visible()
        select_pair(page)
        page.locator("#compare-save-pair").click()
        page.locator("#compare-save-pair").click()
        assert saved_events(page) == ["company_comparison_save"]
        page.reload(wait_until="load")
        assert saved_events(page) == [] and not page.locator("#results").is_visible()
        summary = page.locator("#compare-saved summary")
        summary.focus()
        summary.press("Enter")
        assert page.locator("#compare-saved-items li").count() == 2
        assert page.locator("#compare-saved-items").get_by_text("保存時と同じ数値です。").count() == 2
        assert page.locator(".mcl-saved-metrics span").evaluate_all(
            "spans => spans.every(span => getComputedStyle(span).whiteSpace === 'nowrap')")
        assert "保存を解除" in page.locator("#compare-saved").aria_snapshot()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        assert min(page.locator(".mcl-saved-button:visible").evaluate_all(
            "list => list.map(button => button.getBoundingClientRect().height)")) >= 44
        if screenshots and width == 390:
            summary.scroll_into_view_if_needed()
            page.locator("#compare-saved").screenshot(path=screenshots / f"saved-comparison-{engine}-390.png")
        page.locator("#compare-saved-restore").click()
        assert saved_events(page) == ["company_watchlist_open", "company_comparison_restore"]
        assert page.locator("#result-label").inner_text() == "公開財務データによる参考比較"
        assert page.locator("#compare-title").evaluate("node => node === document.activeElement")
        assert sum(row[1] == "company_compare_complete" for row in events(page)) == 1
        if width == 390:
            anchor = page.locator("#mcl-onecareer-comparison a[href^='https://px.a8.net/']")
            anchor.evaluate("node => { node.addEventListener('click', event => event.preventDefault(), {once:true}); node.click(); }")
            assert [data for _, name, data in events(page) if name == "affiliate_click"] == [{
                "affiliate_network": "a8", "affiliate_program": "onecareer",
                "affiliate_placement": "compare_page", "source_page": "/company-check",
            }]
        page.locator("#compare-saved-items li").first.get_by_role("button", name="の保存を解除", exact=False).click()
        assert page.locator("#compare-saved-items li").count() == 1
        page.locator("#compare-saved-items li").get_by_role("button", name="比較候補Bに入れる", exact=False).click()
        assert page.locator("#name-b").input_value() == "6954"
        assert not page.locator("#compare-saved-restore").is_visible()
        page.locator("#compare-saved-clear").click()
        assert saved_events(page)[-2:] == ["company_watchlist_remove"] * 2
        assert page.evaluate("key => localStorage.getItem(key)", KEY) is None
        assert not runtime_errors, (width, runtime_errors)
        context.close()
    print(engine, "six widths, keyboard open, save/reload/restore/removal, no overflow or JS error")


def verify_change_and_storage(browser, dist):
    context = browser.new_context(service_workers="block")
    local_assets(context, dist)
    page = context.new_page()
    page.goto(TOOL)
    select_pair(page)
    page.locator("#compare-save-pair").click()
    original = page.evaluate("key => localStorage.getItem(key)", KEY)
    fixtures = (
        ("verification-date-only", "保存時と同じ数値です。"),
        ("new-period", "新しい決算期"),
        ("new-document", "同じ決算期の書類が更新"),
        ("same-document", "同じ決算期・書類の掲載値に差"),
        ("different-scope", "会計基準、対象範囲"),
        ("different-length", "決算期の長さ"),
        ("missing-issuer", "現在の公開データに収録されていません"),
        ("renamed-issuer", "同じ提出会社か確認できません"),
        ("no-salary", "給与は比較不可"),
    )
    for scenario, text in fixtures:
        page.evaluate("""([key, original, type]) => {
            const storage = JSON.parse(original);
            const item = storage.items[0];
            if (type === 'verification-date-only') item.verifiedAt='2020-01-01';
            if (type === 'new-period' || type === 'different-length') {
                const [start,end] = item.period.split('〜');
                const shift = day => String(Number(day.slice(0,4))-1) + day.slice(4);
                item.period = (type === 'different-length' ? shift(start).slice(0,4)+'-09-01' : shift(start))
                    + '〜'+shift(end);
            }
            if (type === 'new-document') item.document='S100ZZA1';
            if (['new-period','new-document','same-document'].includes(type)) item.salary -= 12;
            if (type === 'different-scope') item.gaap = item.gaap === 'IFRS' ? 'JP_GAAP' : 'IFRS';
            if (type === 'missing-issuer') item.id='0000';
            if (type === 'renamed-issuer') item.name='確認用の旧社名';
            if (type === 'no-salary') item.salary=null;
            localStorage.setItem(key,JSON.stringify(storage));
        }""", [KEY, original, scenario])
        page.reload()
        page.locator("#compare-saved summary").click()
        assert text in page.locator("#compare-saved-items li").first.inner_text(), scenario
        if scenario == "no-salary":
            assert "掲載値に差" not in page.locator("#compare-saved-items li").first.inner_text()
        if scenario in ("missing-issuer", "renamed-issuer"):
            assert not page.locator("#compare-saved-restore").is_visible()
    page.evaluate("key => localStorage.setItem(key,'{broken')", KEY)
    page.reload()
    assert saved_events(page) == []
    page.locator("#compare-saved summary").click()
    assert "読み込めません" in page.locator("#compare-saved-status").inner_text()
    page.locator("#compare-saved-clear").click()
    assert page.evaluate("key => localStorage.getItem(key)", KEY) is None
    assert saved_events(page) == []
    context.close()

    for mode, override in (
        ("blocked", "Object.defineProperty(window,'localStorage',{get(){throw new Error('blocked')}});"),
        ("quota", "Storage.prototype.setItem = () => {throw new Error('quota')};"),
    ):
        context = browser.new_context(service_workers="block")
        context.add_init_script(override)
        local_assets(context, dist)
        page = context.new_page()
        page.goto(TOOL)
        select_pair(page)
        if mode == "blocked":
            assert not page.locator("#compare-saved").is_visible()
            assert not page.locator("#compare-save-pair").is_visible()
        else:
            page.locator("#compare-save-pair").click()
            assert "保存できませんでした" in page.locator("#compare-save-message").inner_text()
        assert saved_events(page) == []
        context.close()
    print("Change types, missing/renamed issuers, corruption, blocked storage, storage quota all verified")


def verify_restart(engine, launch_options, dist):
    with TemporaryDirectory() as profile:
        options = {**launch_options, "service_workers": "block"}
        context = engine.launch_persistent_context(profile, **options)
        local_assets(context, dist)
        page = (context.pages or [context.new_page()])[0]
        page.goto(TOOL)
        select_pair(page)
        page.locator("#compare-save-pair").click()
        context.close()
        context = engine.launch_persistent_context(profile, **options)
        local_assets(context, dist)
        page = (context.pages or [context.new_page()])[0]
        page.goto(TOOL)
        page.locator("#compare-saved summary").click()
        assert page.locator("#compare-saved-items li").count() == 2
        assert not page.locator("#results").is_visible()
        assert saved_events(page) == ["company_watchlist_open"]
        context.close()
    print("Saved comparison survived a browser restart")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", choices=("chromium", "webkit"))
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--screenshots", type=Path)
    parser.add_argument("--chromium", type=Path)
    args = parser.parse_args()
    if args.screenshots:
        args.screenshots.mkdir(parents=True, exist_ok=True)
    launch_options = {"executable_path": args.chromium, "args": ["--no-sandbox"]} if args.chromium else {}
    with sync_playwright() as pw:
        engine = getattr(pw, args.engine)
        browser = engine.launch(**launch_options)
        verify_layout(browser, args.dist, args.screenshots, args.engine)
        verify_change_and_storage(browser, args.dist)
        browser.close()
        verify_restart(engine, launch_options, args.dist)


if __name__ == "__main__":
    main()
