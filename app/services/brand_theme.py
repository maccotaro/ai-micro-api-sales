"""マイナビバイト ブランド・スライドテーマ (PoC).

リファレンス: user-docs/【サンエス警備保障株式会社御中】採用強化に向けて_20251222.pdf

固定 1 テーマのブランド CSS を提供する。出力経路は Marp(api-export 経由 PPTX/PDF)
を維持しつつ、見た目をブランドに合わせる:
- ヘッダー帯 = シアン (#00A0E9) 白文字
- 見出し/濃色 = 濃紺 (#003E73)
- 強調語 = 赤 (#E60012)
- 表紙 = 白背景＋シアンのアクセントバー
- 淡背景 = 水色 (#EAF6FC)

将来、テナント別テーマや HTML レンダラへ差し替える際もこの定数を起点にする。
"""

# Brand palette
BRAND_CYAN = "#00A0E9"
BRAND_NAVY = "#003E73"
BRAND_RED = "#E60012"
BRAND_TINT = "#EAF6FC"

# Marp `style:` block body (no leading "style: |"; caller indents/embeds).
# Header bar is absolutely positioned so each content slide gets the cyan band;
# section padding-top clears it. Cover slide uses `.lead`.
BRAND_MARP_CSS = f"""section {{
  font-family: 'Hiragino Kaku Gothic ProN', 'Noto Sans JP', 'YuGothic', sans-serif;
  font-size: 15px;
  line-height: 1.5;
  padding: 70px 48px 44px 48px;
  color: #222222;
  background: #ffffff;
  overflow: hidden;
}}
section:not(.lead) h1 {{
  position: absolute;
  top: 0; left: 0; right: 0;
  margin: 0;
  padding: 14px 48px;
  background: {BRAND_CYAN};
  color: #ffffff;
  font-size: 24px;
  font-weight: 700;
  border: none;
  letter-spacing: 0.02em;
}}
section.lead {{
  background: #ffffff;
  justify-content: center;
}}
section.lead h1 {{
  color: {BRAND_NAVY};
  font-size: 40px;
  border-left: 10px solid {BRAND_CYAN};
  padding-left: 24px;
  margin-bottom: 0.3em;
}}
section.lead h2 {{
  color: {BRAND_CYAN};
  font-size: 22px;
  border: none;
  padding-left: 24px;
}}
section.lead p {{
  color: #555555;
  padding-left: 24px;
}}
h2 {{
  color: {BRAND_NAVY};
  font-size: 20px;
  border-bottom: 2px solid {BRAND_CYAN};
  padding-bottom: 4px;
  margin-top: 10px;
  margin-bottom: 8px;
}}
h3 {{
  font-size: 16px;
  color: {BRAND_NAVY};
}}
strong {{
  color: {BRAND_RED};
}}
table {{
  font-size: 13px;
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
}}
th {{
  background: {BRAND_NAVY};
  color: #ffffff;
  padding: 6px 10px;
  text-align: left;
  font-weight: 600;
}}
td {{
  padding: 5px 10px;
  border-bottom: 1px solid #d6e6f2;
}}
section:not(.lead) tr:nth-child(even) td {{
  background: {BRAND_TINT};
}}
ul, ol {{
  font-size: 15px;
  line-height: 1.6;
  margin: 6px 0;
}}
blockquote {{
  border-left: 4px solid {BRAND_CYAN};
  background: {BRAND_TINT};
  padding: 8px 14px;
  margin: 8px 0;
  font-size: 14px;
  border-radius: 0 6px 6px 0;
  color: #37506b;
}}
code {{
  background: #eef4f9;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 12px;
}}
footer {{
  font-size: 10px;
  color: #9bb3c7;
}}
section::after {{
  color: {BRAND_NAVY};
  font-size: 11px;
}}"""


def brand_marp_frontmatter(title: str) -> str:
    """Build a Marp frontmatter block with the brand theme embedded.

    Uses the built-in 'default' Marp theme as a base and overrides via `style:`.
    """
    safe_title = (title or "提案書").replace('"', '\\"')
    indented_css = "\n".join("  " + line for line in BRAND_MARP_CSS.split("\n"))
    return (
        "---\n"
        "marp: true\n"
        "html: true\n"
        "theme: default\n"
        "paginate: true\n"
        "size: 16:9\n"
        f'footer: "{safe_title}"\n'
        "style: |\n"
        f"{indented_css}\n"
        "---\n\n"
    )
