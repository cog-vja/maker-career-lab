#!/usr/bin/env python3
# メーカーキャリアラボ: 現行 index.html に相関分析記事への導線を安全に追加。

# 実行: python3 apply_home_navigation.py
# 現行ホームの他の要素は削除・上書きせず、専用IDのセクション・CSSを挿入します。
# 実行前に同階層の index.html をバックアップし、実行後に検証してください。
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
HOME = ROOT / 'index.html'
TARGET = 'articles/salary-correlation.html'
FEATURE_ID = 'mcl-featured-salary-2026'
LIST_ID = 'mcl-salary-list-2026'
STYLE_ID = 'mcl-salary-link-style'

STYLES = '''<style id="mcl-salary-link-style">
/* メーカーキャリアラボ：追加分析記事への導線（他の既存スタイルを変更しない） */
.mcl-salary-feature { max-width: 1100px; margin: 30px auto 40px; padding: 0 20px; box-sizing: border-box; }
.mcl-salary-feature__card { display: block; padding: 24px 25px; border: 1px solid #b6d4ce; border-left: 5px solid #087c72; border-radius: 14px; background: #eff8f5; text-decoration: none; color: #173342; box-shadow: 0 2px 10px rgba(15,50,55,.04); }
.mcl-salary-feature__card:hover, .mcl-salary-feature__card:focus-visible { border-color: #087c72; box-shadow: 0 4px 16px rgba(8,124,114,.14); }
.mcl-salary-feature__tag { font-size: .8rem; letter-spacing: .08em; font-weight: 800; color: #087c72; }
.mcl-salary-feature__title { display: block; margin: 9px 0; font-size: clamp(1.2rem, 3vw, 1.5rem); line-height: 1.55; font-weight: 800; }
.mcl-salary-feature__summary { display: block; margin-bottom: 9px; font-size: .93rem; line-height: 1.75; color: #506871; }
.mcl-salary-feature__link { display: inline-block; margin-top: 2px; font-weight: 800; color: #087c72; }
.mcl-salary-mini { padding: 17px 19px; border: 1px solid #c4ddd7; border-radius: 11px; background: #f4faf8; margin: 15px 0 24px; }
.mcl-salary-mini a { text-decoration: none; font-weight: 800; color: #087c72; display: block; line-height: 1.7; }
.mcl-salary-mini small { display: block; margin-top: 6px; color: #62777c; line-height: 1.6; }
@media (max-width: 620px) { .mcl-salary-feature { padding: 0 17px; margin: 22px auto 29px; } .mcl-salary-feature__card { padding: 20px 18px; } }
</style>'''

FEATURE = '''<!-- MCL_FEATURE_SALARY_2026_START -->
<section class="mcl-salary-feature" id="mcl-featured-salary-2026" aria-label="新着データ分析">
  <a class="mcl-salary-feature__card" href="articles/salary-correlation.html">
    <span class="mcl-salary-feature__tag">新着データ分析</span>
    <strong class="mcl-salary-feature__title">メーカーの平均年収は、売上高・利益・業種と関係がある？</strong>
    <span class="mcl-salary-feature__summary">メーカー1,000社以上の収録データから、収益力と平均年収の関係を検証。分析の方法と注意点をまとめました。</span>
    <span class="mcl-salary-feature__link">分析記事を読む →</span>
  </a>
</section>
<!-- MCL_FEATURE_SALARY_2026_END -->'''

LIST_CARD = '''<!-- MCL_LIST_SALARY_2026_START -->
<div class="mcl-salary-mini" id="mcl-salary-list-2026">
  <a href="articles/salary-correlation.html">【データ分析】メーカーの平均年収は、売上高・利益・業種と関係する？ →</a>
  <small>収録企業の公開財務情報から、会社の収益力と給与水準を検証します。</small>
</div>
<!-- MCL_LIST_SALARY_2026_END -->'''

def patch(html):
    if FEATURE_ID in html and LIST_ID in html and STYLE_ID in html:
        return html, 'already-applied'
    if '</head>' not in html.lower() or '</main>' not in html.lower():
        raise ValueError('index.html に head/main が見つかりません。現行ファイルを確認してください。')
    if STYLE_ID not in html:
        html = re.sub(r'</head\s*>', STYLES+'\n</head>', html, count=1, flags=re.I)
    # 既存の「記事」セクションの直前に、サイト本来の2つのCTAを維持したまま、特集カードを表示。
    section = re.search(r'<section\b[^>]*\bid\s*=\s*([\"\'])articles\1[^>]*>', html, re.I)
    if not section:
        section = re.search(r'<(?:div|section)\b[^>]*\bid\s*=\s*([\"\'])articles\1[^>]*>', html, re.I)
    if FEATURE_ID not in html:
        if section:
            html = html[:section.start()] + FEATURE + '\n' + html[section.start():]
        else:
            html = re.sub(r'</main\s*>', FEATURE+'\n</main>', html, count=1, flags=re.I)
    if LIST_ID not in html:
        section = re.search(r'<(?:section|div)\b[^>]*\bid\s*=\s*([\"\'])articles\1[^>]*>', html, re.I)
        if section:
            # 見出しの後に追加する（既存のカードやリストは触らない）
            h = re.search(r'</h[1-3]\s*>', html[section.end():section.end()+1200], re.I)
            pos = section.end()+h.end() if h else section.end()
            html = html[:pos] + '\n' + LIST_CARD + '\n' + html[pos:]
    return html, 'patched'

def main():
    if not HOME.is_file():
        print('ERROR: index.html が見つかりません。GitHubリポジトリ直下に、このファイルを置いて実行してください。', file=sys.stderr)
        return 1
    if not (ROOT/TARGET).is_file():
        print('ERROR: articles/salary-correlation.html が見つかりません。先に配置してください。', file=sys.stderr)
        return 1
    original=HOME.read_text(encoding='utf-8')
    updated,status=patch(original)
    if original!=updated:
        backup=HOME.with_suffix('.html.before-salary-link.bak')
        if not backup.exists(): backup.write_text(original,encoding='utf-8')
        HOME.write_text(updated,encoding='utf-8')
    if updated.count('id="mcl-featured-salary-2026"') != 1 or updated.count('id="mcl-salary-link-style"') != 1:
        print('ERROR: 挿入結果が想定と異なります。編集済みファイルを確認してください。',file=sys.stderr)
        return 1
    print('RESULT:',status)
    print('記事リンク数:',updated.count('href="'+TARGET+'"'))
    print('ホームHTML:',HOME)
    print('対象記事:',ROOT/TARGET)
    print('次の操作: GitHubに index.html と articles/salary-correlation.html をコミットしてください。')
    return 0
if __name__=='__main__':
    raise SystemExit(main())
