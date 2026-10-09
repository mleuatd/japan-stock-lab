# 銘柄属性マスター — 2026-10-09

## 完了した内容
Neon `japan_stock_lab` に `sql/004_stock_attributes.sql` を適用。次の5テーブルを用意：
- `stock_attribute_category` 分類マスター（8分類）
- `stock_attribute` 属性マスター（175属性、重複しないコード）
- `stock_attribute_assignment` 銘柄×属性の多対多リンク（取引日単位の有効期間、根拠、信頼区分）
- `stock_attribute_signal` 日付と計算手法をキーにした売買スクリーニング用の動的判定
- 既存 `security_master` は銘柄の基本情報用であり、別途正規化された属性割当てを管理する

## 考え方
一銘柄に多数の属性、一属性に多数の銘柄。不要な横持ち列や全株価行へのラベル複写をしない。
- 東証33業種は「銘柄ごと1つ」が基本で、各業種は排他的な公式分類。暫定タグのような非公式テーマとは区別する。
- 半導体、AI、飲食、地方出店などは重なってよいタグ。
- 「大型株」「高配当」「1か月上昇」は**測定日によって変わる条件**なので `stock_attribute_signal` に評価日と手法バージョンとともに管理。客観指標・閾値（例：時価総額、配当利回り、直近20営業日騰落率）は今後定義する。根拠なしに自動付与しない。
- 高知から利用可能な店舗属性は企業の本社所在地と別の概念。住所・閉店・店舗をソース付きで記録する仕組みを将来別設計する。
- 証券コードは既存の J-Quants 5桁文字列を保持（例 `72030`）。4桁銘柄コードの表示は別処理。コード変遷・株式の上場廃止など将来の銘柄識別も考慮する。

## SQL例
```sql
-- 正式な裏付けがある「AI」「半導体」の両方に該当する銘柄
SELECT a.security_code
FROM stock_attribute_assignment a
JOIN stock_attribute t ON t.attribute_id=a.attribute_id
WHERE t.attribute_name IN ('AI','半導体')
  AND a.valid_from <= CURRENT_DATE
  AND (a.valid_to IS NULL OR a.valid_to >= CURRENT_DATE)
GROUP BY a.security_code
HAVING COUNT(DISTINCT t.attribute_name)=2;

-- 分類マスターと属性の一覧
SELECT c.category_name,t.attribute_name,t.attribute_kind
FROM stock_attribute t JOIN stock_attribute_category c USING(category_code)
ORDER BY c.sort_order,t.attribute_id;
```

## 今後の作業
1. ライセンス・出典確認済みの銘柄基本情報を無料で取得し、`security_master` と `stock_attribute_assignment` に公式業種・上場区分を登録。
2. テーマ・地域・事業モデルは根拠あるデータのみ分類し、ユーザー編集可能な属性割当UIを後から追加。
3. 動的条件（高配当／低PBR／出来高／直近上昇など）の数値閾値と集計基準日を別途定義、日付別シグナル生成へ。
4. スクリーナーに AND/OR/除外指定の組み合わせを実装。SQL側の絞り込みを優先し、検索結果のサムネイルは候補のみ生成。
5. 今回は既存株価データ1,914,081行を変更せず、銘柄への根拠なし自動分類も行わなかった。割当件数=0、シグナル件数=0（作成時）。

無料枠を前提とし、追加インデックスもリンク・条件判定テーブルに必要なものだけ。属性一覧だけでは企業ごとの自動分類は完成しない。
