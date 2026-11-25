"""Batch 1 article discovery, classifications and verified comparison inputs."""

# (category, short title, description, GA4 content group)
BATCH1_ARTICLES = {
    "production-engineering-career": (
        "キャリア・転職", "生産技術からの転職先", "工程立上げ・設備・改善の経験を転職先と照合",
        "batch1_career",
    ),
    "quality-assurance-career": (
        "キャリア・転職", "品質保証・品質管理からの転職", "工程品質・顧客品質・サプライヤー品質を比較",
        "batch1_career",
    ),
    "procurement-career": (
        "キャリア・転職", "調達・購買からの転職先", "発注・原価企画・サプライヤー開拓の経験を整理",
        "batch1_career",
    ),
    "technical-sales-career": (
        "キャリア・転職", "メーカー技術営業の仕事とキャリア", "技術提案・導入支援と求人票の見方",
        "batch1_career",
    ),
    "manufacturer-salary-10m-career": (
        "キャリア・転職", "メーカーで年収1,000万円は可能？", "EDINETの給与分布、公式求人、職責と初年度給与を比較",
        "batch1_career",
    ),
    "electronic-component-makers-comparison": (
        "年収・企業", "電子部品メーカー4社を比較", "村田、TDK、太陽誘電、京セラの給与・利益率・仕事",
        "batch1_comparison",
    ),
    "machine-tool-makers-comparison": (
        "年収・企業", "工作機械メーカー4社を比較", "切削工程・導入支援と給与・利益率を比較",
        "batch1_comparison",
    ),
    "measurement-instrument-makers-comparison": (
        "年収・企業", "計測・分析機器メーカー4社を比較", "研究・品質・製造工程の計測と各社の開示データ",
        "batch1_comparison",
    ),
    "physical-ai-manufacturing-careers": (
        "AI・DX", "フィジカルAIと製造業の仕事", "認識・動作・安全・保全を導入段階ごとに判断",
        "batch1_growth",
    ),
    "data-center-manufacturing-careers": (
        "AI・DX", "データセンター需要と製造業の仕事", "電力・冷却・光通信の部材と職種を比較",
        "batch1_growth",
    ),
}

BATCH1_COMPARISONS = {
    "electronic-component-makers-comparison": ("6981", "6762", "6976", "6971"),
    "machine-tool-makers-comparison": ("6141", "6103", "6135", "6101"),
    "measurement-instrument-makers-comparison": ("7701", "6856", "6866", "6841"),
}

BATCH1_REVISED = "2026-11-26"
# Main d6ea349 was deployed on 2026-11-25 at 22:44 JST.
BATCH1_PUBLISHED = "2026-11-25"

BATCH1_AD_PROGRAMS = dict.fromkeys((
    "production-engineering-career", "quality-assurance-career", "procurement-career",
    "technical-sales-career", "manufacturer-salary-10m-career",
), "makers_job") | dict.fromkeys(BATCH1_COMPARISONS, "onecareer")

# Add only slugs whose program-specific terms and URL submission have been verified.
APPROVED_BATCH1_ADS = frozenset()
