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
section:not(.lead) {{ align-content: start !important; align-items: stretch !important; }}
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
}}
/* --- Layout components (reference brand deck) --- */
.cards {{
  display: flex;
  gap: 18px;
  margin-top: 18px;
}}
.card {{
  flex: 1;
  border: 1px solid {BRAND_CYAN};
  border-radius: 8px;
  padding: 20px 18px 16px;
  background: #ffffff;
  min-height: 330px;
  box-sizing: border-box;
}}
.card .num {{
  display: inline-block;
  width: 30px; height: 30px; line-height: 30px;
  border-radius: 50%;
  background: {BRAND_CYAN};
  color: #fff; text-align: center; font-weight: 700;
  margin-bottom: 6px;
}}
.card .ttl {{
  color: {BRAND_NAVY}; font-weight: 700; font-size: 18px; margin: 6px 0;
}}
.card .body {{ font-size: 14px; color: #444; line-height: 1.6; }}
.cmp {{
  display: flex; gap: 16px; margin-top: 12px;
}}
.cmp .col {{
  flex: 1; border-radius: 8px; padding: 12px 14px;
}}
.cmp .col.left {{ background: #eef0f2; }}
.cmp .col.right {{ background: {BRAND_TINT}; }}
.cmp .col .head {{ font-weight: 700; margin-bottom: 6px; color: {BRAND_NAVY}; }}
.cmp .col.right .head {{ color: {BRAND_CYAN}; }}
.ba {{ display: flex; gap: 16px; align-items: stretch; margin-top: 12px; }}
.ba .col {{ flex: 1; border: 1px solid #d6e6f2; border-radius: 8px; padding: 12px; }}
.ba .col .head {{ font-weight: 700; color: {BRAND_NAVY}; margin-bottom: 6px; }}
.ba .col.after {{ border-color: {BRAND_CYAN}; }}
.ba .metric {{ font-size: 13px; color: #444; }}
.principle {{ display: flex; gap: 16px; margin-top: 12px; }}
.principle .col {{ flex: 1; border: 1px solid #d6e6f2; border-radius: 8px; padding: 12px; }}
.principle .col .head {{ background: {BRAND_NAVY}; color: #fff; padding: 6px 10px; border-radius: 6px; font-weight: 700; margin: -12px -12px 10px; }}
ol.agenda {{ list-style: none; padding: 0; margin-top: 16px; }}
ol.agenda li {{ display: flex; align-items: center; gap: 12px; margin: 10px 0; font-size: 17px; color: {BRAND_NAVY}; font-weight: 600; }}
ol.agenda .num {{
  display: inline-block; width: 34px; height: 34px; line-height: 34px;
  border-radius: 50%; background: {BRAND_CYAN}; color: #fff;
  text-align: center; font-weight: 700; font-size: 14px;
}}
/* --- principles 2-col step flow --- */
.cols {{ display: flex; gap: 24px; margin-top: 6px; }}
.cols .col {{ flex: 1; }}
.colhead {{ background: {BRAND_NAVY}; color: #fff; font-weight: 700; padding: 8px 12px; border-radius: 6px; text-align: center; font-size: 15px; }}
.step {{ border: 1px solid #cfe6f4; border-radius: 8px; padding: 9px 12px; margin: 9px 0; }}
.step .t {{ color: {BRAND_NAVY}; font-weight: 700; font-size: 14px; }}
.step .d {{ font-size: 13px; color: #555; }}
.arrow {{ text-align: center; color: {BRAND_CYAN}; font-size: 15px; margin: -3px 0; }}
.concl {{ text-align: center; color: {BRAND_CYAN}; font-weight: 700; border-top: 2px solid {BRAND_CYAN}; margin-top: 8px; padding-top: 6px; }}
/* --- strategy: lead psychology + paradigm + merits + catchcopy --- */
.lead-psy {{ background: #fff; border-left: 6px solid {BRAND_CYAN}; padding: 12px 18px; margin: 16px 0; font-size: 16px; color: {BRAND_NAVY}; box-shadow: 0 1px 4px rgba(0,62,115,0.08); }}
.lead-psy .lbl {{ color: {BRAND_CYAN}; font-weight: 700; margin-right: 8px; }}
.para {{ display: flex; align-items: center; gap: 14px; background: {BRAND_TINT}; border-radius: 8px; padding: 18px; margin: 18px 0; font-size: 17px; }}
.para .old {{ background: #e3e7ea; padding: 12px 18px; border-radius: 6px; font-weight: 700; color: #555; }}
.para .new {{ background: #fff; border: 2px solid {BRAND_CYAN}; padding: 12px 18px; border-radius: 6px; font-weight: 700; color: {BRAND_NAVY}; }}
.para .ar {{ color: {BRAND_CYAN}; font-weight: 700; }}
.merits {{ display: flex; gap: 14px; margin: 18px 0; }}
.merit {{ flex: 1; border: 1px solid {BRAND_CYAN}; border-top: 4px solid {BRAND_CYAN}; border-radius: 8px; text-align: center; padding: 20px 6px; font-weight: 700; color: {BRAND_NAVY}; font-size: 16px; }}
.cc {{ background: {BRAND_TINT}; border-radius: 8px; padding: 18px 22px; margin-top: 18px; }}
.cc .h {{ color: {BRAND_CYAN}; font-weight: 700; margin-bottom: 10px; font-size: 17px; }}
.cc ul {{ margin: 0; }}
.cc li {{ margin: 10px 0; }}
.cc li .ct {{ color: {BRAND_NAVY}; font-weight: 700; }}
.cc li .rs {{ display: block; font-size: 13px; color: #5a6b7a; margin-top: 2px; }}
/* --- target psychology axis rows --- */
.axisrows {{ margin-top: 8px; }}
.axisrow {{ display: flex; align-items: stretch; gap: 14px; margin: 14px 0; }}
.axisrow .axname {{ flex: 0 0 210px; background: {BRAND_NAVY}; color: #fff; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-weight: 700; padding: 14px; text-align: center; font-size: 15px; }}
.axisrow .axdetail {{ flex: 1.2; background: #fff; border: 1px solid #d6e6f2; border-radius: 8px; padding: 12px 16px; font-size: 14px; color: #444; }}
.axisrow .axar {{ display: flex; align-items: center; color: {BRAND_CYAN}; font-weight: 700; font-size: 18px; }}
.axisrow .axappeal {{ flex: 1.2; background: {BRAND_TINT}; border: 1px solid {BRAND_CYAN}; border-radius: 8px; padding: 12px 16px; font-size: 14px; color: {BRAND_NAVY}; font-weight: 600; }}
.axisrow .cap {{ font-size: 11px; font-weight: 700; color: {BRAND_CYAN}; margin-bottom: 4px; }}
/* --- strategy summary card extras --- */
.card .pd {{ margin-top: 10px; font-size: 13px; }}
.card .pd .pold {{ background: #e3e7ea; border-radius: 5px; padding: 3px 8px; color: #555; }}
.card .pd .par {{ color: {BRAND_CYAN}; font-weight: 700; }}
.card .pd .pnew {{ background: #fff; border: 1.5px solid {BRAND_CYAN}; border-radius: 5px; padding: 3px 8px; color: {BRAND_NAVY}; font-weight: 700; }}
.card .chips {{ margin-top: 10px; }}
.card .chip {{ display: inline-block; border: 1px solid {BRAND_CYAN}; border-radius: 12px; padding: 2px 10px; font-size: 12px; color: {BRAND_NAVY}; margin: 2px 3px 2px 0; }}
.card .copyline {{ margin-top: 10px; font-size: 13px; color: {BRAND_RED}; font-weight: 600; }}
/* --- success case: big KPIs / arrow / improvement banner --- */
.ba {{ margin-top: 22px; }}
.ba .col {{ padding: 24px 26px; min-height: 250px; box-sizing: border-box; }}
.ba .col .head {{ font-size: 20px; }}
.ba .col.after .head {{ color: {BRAND_CYAN}; }}
.ba .metric {{ font-size: 15px; color: #444; margin-bottom: 14px; }}
.ba .kpis {{ display: flex; gap: 44px; margin-top: 18px; justify-content: center; }}
.ba .kpi {{ text-align: center; }}
.ba .kv {{ font-size: 44px; font-weight: 700; color: #666; line-height: 1.1; }}
.ba .kv.big {{ font-size: 58px; color: {BRAND_RED}; }}
.ba .col.after .kv {{ color: {BRAND_NAVY}; }}
.ba .col.after .kv.big {{ color: {BRAND_RED}; }}
.ba .kl {{ font-size: 12px; color: #888; margin-top: 2px; }}
.ba-ar {{ display: flex; align-items: center; color: {BRAND_CYAN}; font-weight: 700; font-size: 30px; }}
.improve {{ background: {BRAND_TINT}; border-left: 6px solid {BRAND_RED}; border-radius: 0 8px 8px 0; padding: 18px 22px; margin-top: 24px; font-size: 16px; color: #37506b; }}
.improve .lbl {{ color: {BRAND_RED}; font-weight: 700; margin-right: 10px; }}"""


def preview_scoped_css() -> str:
    """BRAND_MARP_CSS を `.brand-slide` 配下にスコープしたプレビュー用 CSS を返す。

    front-user の SlidePreview はこの CSS を取得して 1280x720 のキャンバスに
    適用する。CSS の実体は BRAND_MARP_CSS 一本のため、エクスポート(PPTX/PDF)と
    プレビューの体裁が乖離しない（手動ミラー brand-slide.css の置き換え）。
    変換規則: `section...` → `.brand-slide...`、その他セレクタは `.brand-slide ` を前置。
    """
    rules = []
    for raw in BRAND_MARP_CSS.split("}"):
        if "{" not in raw:
            continue
        sel_part, body = raw.split("{", 1)
        # コメントはセレクタ部から除去（rule 単位の先頭にのみ現れる想定）
        while "/*" in sel_part and "*/" in sel_part:
            pre, rest = sel_part.split("/*", 1)
            sel_part = pre + rest.split("*/", 1)[1]
        selectors = []
        for s in sel_part.split(","):
            s = s.strip()
            if not s:
                continue
            if s.startswith("section"):
                selectors.append(".brand-slide" + s[len("section"):])
            else:
                selectors.append(".brand-slide " + s)
        if selectors:
            rules.append(", ".join(selectors) + " {" + body + "}")
    # プレビュー専用の補完: Marp 側が暗黙に与えるレイアウト前提を再現する
    rules.append(".brand-slide, .brand-slide * { box-sizing: border-box; }")
    rules.append(".brand-slide { display: block; }")
    rules.append(
        ".brand-slide.lead { display: flex; flex-direction: column; justify-content: center; }"
    )
    return "\n".join(rules)


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
