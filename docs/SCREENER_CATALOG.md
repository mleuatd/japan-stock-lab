# 標準スクリーニング項目カタログ (2026-10-09)

## 作成済み・Neon本番反映済み
`sql/006_screener_catalog.sql`:
- `screener_metric_group`: 10分類
- `screener_metric`: 計239項目（主にSBI証券、大和証券、楽天証券の一般的項目を参考に独自設計）
- `screener_saved_rule`: 絞り込み条件をJSONで組み合わせる拡張可能な定義（例4件・全てdisabled）。実際の売買はしない。
- 日足 `daily_bar` をコピーしない。実際の数値を保存する列を239個も追加せず、条件定義だけを軽量に登録。
- `implementation_state` は全239項目「planned」。適切な価格・財務データが揃い、実装と検証が完了したものだけ `tested`, `available` に変えること。**マスター登録 != 計算可能**。
- データ元は `ohlcv`, `external`, `derived`; `value_type` と単位を別管理。

## 機能分類・項目数
| group_code | 名称 | 件数 |
|---|---|---:|
| basic | 基本情報 | 20 |
| valuation | 株価評価・割安性 | 17 |
| dividend | 配当・株主優待 | 21 |
| performance | 業績・収益性 | 35 |
| balance | 財務健全性 | 19 |
| price | 株価・出来高・騰落 | 38 |
| technical | テクニカル分析 | 54 |
| credit | 信用取引・需給 | 13 |
| analyst | アナリスト予想 | 10 |
| custom | 独自戦略・地域 | 12 |
| TOTAL | | 239 |

## 確認した参照元
- SBI証券 公式スクリーナー項目: https://site3.sbisec.co.jp/ETGate/WPLETmgR001Control?OutSide=on&burl=search_domestic&cat1=domestic&cat2=none&dir=info&file=domestic_info190925_01.html
- SBI証券 公式詳細定義: https://search.sbisec.co.jp/v2/popwin/info/trading/pop_domestic_screening_01.html
- 楽天証券スーパースクリーナー: https://www.rakuten-sec.co.jp/ITS/qaJ010102-001.html
- 大和証券スクリーニング解説: https://www.daiwa.jp/seminar/study_brand/equity/terms/

## 実装時の優先順位
1. 保存済みJ-Quantsの日次OHLCVから計算できる前日比・期間騰落率・移動平均・出来高倍率・連続上昇下落・過去高安・RSI・MACD等を先に実装。
2. 財務・優待・アナリストなど価格だけでは計算不能な項目は、¥0で許諾を守って取得できた場合にだけ有効化。欠損は「不明」とし、0・falseと区別する。
3. 期間・閾値・AND/OR/NOT・複数条件組合せのUIと最適化されたSQL生成を実装。現段階では実行エンジン未実装。
4. シグナルバックテストは当時の情報のみ使う（後から発表された財務や株価を過去時点で使う先読みバイアス防止）。株式分割・株価調整に注意。
5. 例示ルールは無効状態で格納し、ユーザーの許可なく売買通知や実注文をしない。
6. Neon Free容量・Compute Unit時間を守り、派生データは必要時に計算するか、狭い集計結果のみキャッシュ。全OHLCVを重複保存しない。

## マスターの役割の整理
- `stock_attribute`: 企業の属性・業種・特徴を示すタグ名。企業との多対多。
- `price_change_band`: 日次騰落率を区分にマッピングする境界マスター。
- `price_streak_rule`: 連続日数に関する条件定義。
- `screener_metric`: PER、RSI、配当利回りなど値を持つ検索指標のメタ情報。
- `screener_saved_rule`: 検索条件の論理式の保存先。
