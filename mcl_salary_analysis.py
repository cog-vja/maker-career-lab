"""Render the career guide's salary analysis from published EDINET rows."""

from collections import defaultdict
from datetime import date
from html import escape
from math import inf, isfinite
import re
from statistics import median

LEAD_MARKER = "<!-- MCL_BATCH1_SALARY_LEAD -->"
ANALYSIS_MARKER = "<!-- MCL_BATCH1_SALARY_ANALYSIS -->"
TARGET_SALARY = 1000
CONSOLIDATED = "連結（給与のみ提出会社）"
ACCOUNTING_STANDARDS = {"JP_GAAP", "IFRS", "US_GAAP"}

# Classify these editorial examples using the issuer's own business descriptions.
# The dataset has no general company-type field. Never classify names by suffix.
OPERATING_EXAMPLES = (
    ("6861", "https://www.keyence.co.jp/company/profile.jsp"),
    ("6920", "https://www.lasertec.co.jp/company/business.html"),
    ("6146", "https://www.disco.co.jp/jp/corporate/outline/index.html"),
    ("8035", "https://www.tel.co.jp/about/summary/"),
)
HOLDING_EXAMPLES = (
    ("3608", "https://www.tsi-holdings.com/company.html"),
    ("2502", "https://www.asahigroup-holdings.com/company/profile/"),
    ("285A", "https://www.kioxia-holdings.com/ja-jp/about/company.html"),
    ("5411", "https://www.jfe-holdings.co.jp/sustainability/governance/governance/index.html"),
)

SALARY_BANDS = (
    ("800万円未満", -inf, 800),
    ("800万円以上・1,000万円未満", 800, 1000),
    ("1,000万円以上・1,200万円未満", 1000, 1200),
    ("1,200万円以上", 1200, inf),
)
REVENUE_BANDS = (
    ("100億円未満", -inf, 100),
    ("100億円以上・1,000億円未満", 100, 1000),
    ("1,000億円以上・1兆円未満", 1000, 10_000),
    ("1兆円以上", 10_000, inf),
)
MARGIN_BANDS = (
    ("0%未満", -inf, 0),
    ("0%以上・10%未満", 0, 10),
    ("10%以上・20%未満", 10, 20),
    ("20%以上", 20, inf),
)


def finite_number(value):
    return type(value) in (int, float) and isfinite(value)


def positive_number(value):
    return finite_number(value) and value > 0


def at_least(salaries, threshold=TARGET_SALARY):
    return sum(salary >= threshold for salary in salaries)


def share(count, total):
    return f"{count * 100 / total:.1f}%" if total else "—"


def count_share(count, total):
    return f"{count:,}社（{share(count, total)}）" if total else f"{count:,}社"


def salary_distribution(salaries):
    items = []
    for label, low, high in SALARY_BANDS:
        count = sum(low <= salary < high for salary in salaries)
        percent = share(count, len(salaries))
        items.append(
            f'<li><div><span>{label}</span><strong>{count:,}社（{percent}）</strong></div>'
            '<span class="mcl-salary-track" aria-hidden="true">'
            f'<span style="width:{percent}"></span></span></li>'
        )
    return (
        '<h3 id="salary-distribution-heading">提出会社の平均年間給与の分布</h3>'
        '<ul class="mcl-salary-distribution" role="list" aria-labelledby="salary-distribution-heading">'
        + "".join(items) + "</ul>"
    )


def table(caption, columns, rows):
    head = "".join(f'<th scope="col">{escape(column)}</th>' for column in columns)
    rendered = []
    for label, *cells in rows:
        data = "".join(f"<td>{cell}</td>" for cell in cells)
        rendered.append(f'<tr><th scope="row">{escape(label)}</th>{data}</tr>')
    safe_caption = escape(caption)
    return (
        f'<div class="table-scroll" role="region" tabindex="0" aria-label="{safe_caption}">'
        f"<table><caption>{safe_caption}</caption>"
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(rendered)}</tbody></table></div>"
    )


def salary_stats(label, salaries):
    return (
        label, f"{len(salaries):,}社", f"{median(salaries):,.1f}万円" if salaries else "—",
        count_share(at_least(salaries), len(salaries)),
    )


def group_columns(label="区分"):
    return (label, "集計企業", "各社平均の中央値", "1,000万円以上（区分内）")


def filing_period_sample(rows):
    ends = []
    for row in rows:
        period = row.get("period")
        if not isinstance(period, str):
            continue
        try:
            ends.append(date.fromisoformat(period.rsplit("〜", 1)[-1]))
        except ValueError:
            continue
    if not ends:
        return ""
    start, end = min(ends), max(ends)
    period_summary = f"{start}から{end}" if start != end else str(start)
    covered = "決算期末を確認できる" if len(ends) < len(rows) else "集計対象の"
    return f"{covered}{len(ends):,}社の決算期末は{period_summary}です。"


def example_rows(examples, issuer_by_id):
    rows = []
    for code, source in examples:
        issuer = issuer_by_id.get(code)
        if issuer is None or issuer["averageSalary"] < TARGET_SALARY:
            continue
        name = issuer.get("name") or code
        document = escape(issuer.get("sourceDocId") or "未記録")
        period = escape(issuer.get("period") or "未記録")
        edinet = f'<a href="https://disclosure2.edinet-fsa.go.jp/">{document}</a>'
        company_profile = f'<a href="{source}">{escape(name)}の公式情報</a>'
        rows.append((
            f"{name}（{code}）", f'{issuer["averageSalary"]:,.1f}万円',
            f"{period}<br>書類ID {edinet}", company_profile,
        ))
    return rows


def render_examples(issuers):
    by_id = {str(issuer["id"]): issuer for issuer in issuers}
    columns = ("提出会社（証券コード）", "平均年間給与", "対象期間・出典", "会社形態の出典")
    examples = []
    for label, companies in (
        ("事業会社", OPERATING_EXAMPLES), ("持株会社", HOLDING_EXAMPLES),
    ):
        if rows := example_rows(companies, by_id):
            examples.append(table(f"平均年間給与が1,000万円以上の{label}の例", columns, rows))
    if not examples:
        return ""
    return (
        "<h3>事業会社と持株会社で、給与の集計対象を確認する</h3>"
        "<p>会社形態は、各社の製品・事業内容やグループ経営管理の説明で確認できた例を掲載しています。"
        "いずれも提出会社単体の平均です。持株会社の提出書類を見たら、応募先の事業会社が別法人かを"
        "求人票の雇用元欄で確認してください。</p>"
        + "\n".join(examples)
    )


def render_industries(issuers):
    groups = defaultdict(list)
    uncategorized = []
    for issuer in issuers:
        industry = issuer.get("industry")
        if isinstance(industry, str) and industry.strip():
            groups[industry.strip()].append(issuer["averageSalary"])
        else:
            uncategorized.append(issuer["averageSalary"])
    missing = len(uncategorized)
    if not groups:
        return "<h3>業種別に比較する</h3><p>業種を収録した集計対象がありません。</p>"
    rows = [
        salary_stats(industry, salaries)
        for industry, salaries in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    ]
    if missing:
        rows.append(salary_stats("業種未記録", uncategorized))
    return (
        "<h3>収録企業の業種別に比較する</h3>"
        f"<p>業種はデータの記録に従い、{len(issuers) - missing:,}社に業種があり、{missing:,}社は業種未記録です。"
        "各行の割合はその区分に収録された会社の割合です。件数が少ない区分では少数の会社で数値が動きます。</p>"
        "<details><summary>業種別の社数・中央値・1,000万円以上の割合を表示</summary>"
        + table("収録企業の業種別の平均年間給与", group_columns("業種"), rows)
        + "</details>"
    )


def render_financial_groups(issuers):
    revenue_pairs = []
    margin_pairs = []
    for issuer in issuers:
        sales = issuer.get("revenue")
        if issuer.get("scope") != CONSOLIDATED or not positive_number(sales):
            continue
        salary = issuer["averageSalary"]
        revenue_pairs.append((sales, salary))
        profit = issuer.get("operatingProfit")
        if issuer.get("accountingStandard") in ACCOUNTING_STANDARDS and finite_number(profit):
            margin = profit / sales * 100
            if isfinite(margin):
                margin_pairs.append((margin, salary))

    def group(pairs, bands):
        return [
            salary_stats(label, [salary for value, salary in pairs if low <= value < high])
            for label, low, high in bands
        ]

    return (
        "<h3>売上規模・営業利益率とあわせて見る</h3>"
        f"<p>規模では連結売上高・売上収益が正の{len(revenue_pairs):,}社を集計しました。"
        f"営業利益率では、そのうち会計基準と報告営業利益を確認できる{len(margin_pairs):,}社を集計し、"
        "報告営業利益を連結売上高・売上収益で割りました。給与は引き続き提出会社単体です。</p>"
        + table("売上規模別の平均年間給与", group_columns("連結売上高・売上収益"), group(revenue_pairs, REVENUE_BANDS))
        + table("営業利益率別の平均年間給与", group_columns("連結営業利益率"), group(margin_pairs, MARGIN_BANDS))
        + "<p>事業構成、決算期、会計処理、従業員構成が異なる会社を含む記述集計です。"
        "応募先を選ぶ段階では、担当する事業の複数期の業績と、募集法人・職責・等級の条件を確認してください。</p>"
    )


def add_salary_analysis(html, dataset):
    """Insert current salary evidence in the article, without copying source values."""
    for marker in (LEAD_MARKER, ANALYSIS_MARKER):
        if html.count(marker) != 1:
            raise RuntimeError(f"給与分析の差し込み位置が一意ではありません: {marker}")
    issuers = [
        row for row in dataset
        if positive_number(row.get("averageSalary"))
        and row.get("salaryScope") == "提出会社単体"
        and re.fullmatch(r"S[A-Z0-9]{7,15}", row.get("sourceDocId") or "")
        and re.fullmatch(r"[0-9a-f]{64}", row.get("sourceSha256") or "")
    ]
    salaries = [row["averageSalary"] for row in issuers]
    if not salaries:
        raise RuntimeError("給与分析に使える会社がありません")
    denominator = len(salaries)
    target = at_least(salaries)
    lead = (
        f'<p class="intro">メーカーキャリアラボの収録企業で、提出会社単体の平均年間給与が'
        f'<strong>1,000万円以上は{target:,}社／{denominator:,}社（{share(target, denominator)}）</strong>です。'
        "転職でその水準を目指すときは、応募先の法人、職責、等級、基本給・賞与を求人単位で確認しましょう。</p>"
    )
    threshold_summary = "、".join(
        f"{threshold:,}万円以上は{count_share(at_least(salaries, threshold), denominator)}"
        for threshold in (800, 1000, 1200)
    )
    period_sample = filing_period_sample(issuers)
    analysis = (
        f"<p>金融庁EDINETの有価証券報告書を基にしたサイト収録{len(dataset):,}社のうち、"
        f"書類IDと照合情報があり、提出会社単体の正の平均年間給与を収録する{denominator:,}社を集計しました。"
        f"{period_sample}会社ごとの平均を1社1件で集計し、中央値は{median(salaries):,.1f}万円です。"
        "従業員数による重み付けを行わず、同額の会社もそれぞれ数え、区分判定には丸め前の値を使います。"
        "比率の単位は会社で、個人がその水準を得る割合はこの集計から求められません。</p>"
        f"<p>{threshold_summary}です。各しきい値以上の累計で、下のグラフでは給与帯ごとの件数を示しています。</p>"
        + salary_distribution(salaries)
        + render_examples(issuers)
        + render_industries(issuers)
        + render_financial_groups(issuers)
    )
    return html.replace(LEAD_MARKER, lead).replace(ANALYSIS_MARKER, analysis)
