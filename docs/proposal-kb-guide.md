# 提案書KB運用ガイド

## 1. KB構成

提案パイプライン（Stage 6-10）では3種類のKBを使用します。

### 提案書リファレンスKB（proposal_reference）

| 項目 | 内容 |
|------|------|
| 目的 | 優秀な提案書をストーリー構成の手本として使用 |
| 登録者 | 営業担当（アップロード） → マネージャー（精査・承認） |
| 形式 | PPT / PDF |
| 承認フラグ | `proposal_quality:approved` タグ |

#### アップロード手順

1. 管理画面（front-admin）でKBを作成（名前例: 「提案書リファレンス」）
2. ドキュメントをアップロード
3. タグを付与:
   - `industry:<業界名>` 例: `industry:警備`
   - `job_type:<職種名>` 例: `job_type:施設警備`
   - `area:<エリア名>` 例: `area:東京`
4. マネージャーが内容を確認後、`proposal_quality:approved` タグを追加

#### 注意事項

- `proposal_quality:approved` タグがないドキュメントはパイプラインの検索対象になりません
- 業界タグは必須です（検索フィルタに使用）

### 心理パターンKB（target_psychology）

| 項目 | 内容 |
|------|------|
| 目的 | エンドユーザーと担当者の心理パターンを蓄積・検索 |
| 登録者 | マネージャー |
| 形式 | Markdown |

#### ドキュメントテンプレート

**エンドユーザー心理（type:end_user）:**

```markdown
# 警備業界 × 施設警備 × シニア層 の求職者心理

## 心理軸

### 1. 体力への不安
- **詳細**: 年齢を重ねても無理なく続けられるか
- **対応する訴求**: 施設警備は座り仕事も多く体力負担が少ない

### 2. 人間関係の不安
- **詳細**: 若い人ばかりの職場で馴染めるか
- **対応する訴求**: 同年代の同僚が多い職場環境

### 3. 社会貢献への欲求
- **詳細**: まだ社会の役に立ちたい
- **対応する訴求**: 地域の安全を守る社会的意義

## 時期による変動
- **年始**: 新年の新生活欲求が強い
- **夏**: 体力面の不安が増す
```

タグ: `type:end_user`, `industry:警備`, `job_type:施設警備`, `target:シニア`

**担当者心理（type:decision_maker）:**

```markdown
# 警備業界 × 人事担当 の意思決定心理

## 判断基準
1. 費用対効果（いくらかけたら何名採れるか）
2. 応募数の予測可能性

## よくある懸念
- 前の媒体では応募が来なかった
- 上に説明できる根拠がほしい
- 競合他社の採用動向が気になる

## 必要なエビデンス
- 同業界の成功事例（Before/After + 数値）
- PV・応募数の実績データ
```

タグ: `type:decision_maker`, `industry:警備`, `role:人事担当`, `concern:採用コスト`

## 2. パイプライン設定（kb_mapping）

管理画面（front-admin）の提案パイプライン設定画面で、各KBカテゴリにKB IDを登録します。

| カテゴリ名 | 使用Stage | 検索クエリ例 |
|-----------|----------|-------------|
| `proposal_reference` | 6 | `{industry} {area} 提案書 成功事例 戦略` |
| `target_psychology_end_user` | 7 | `{industry} エンドユーザー 心理 不安 動機` |
| `target_psychology_decision_maker` | 7, 8 | `{industry} 担当者 意思決定 懸念 判断軸` |

## 3. タグ一覧

| プレフィックス | 用途 | 例 |
|--------------|------|---|
| `industry:` | 業界 | `industry:警備`, `industry:飲食` |
| `job_type:` | 職種 | `job_type:施設警備`, `job_type:ホールスタッフ` |
| `area:` | エリア | `area:東京`, `area:大阪` |
| `type:` | 心理タイプ | `type:end_user`, `type:decision_maker` |
| `target:` | ターゲット層 | `target:シニア`, `target:主婦` |
| `role:` | 担当者役職 | `role:人事担当`, `role:店長` |
| `concern:` | 担当者関心事 | `concern:採用コスト` |
| `season:` | 時期 | `season:年始`, `season:新年度` |
| `proposal_quality:` | 品質フラグ | `proposal_quality:approved` |
