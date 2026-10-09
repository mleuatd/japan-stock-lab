# バックテスト障害対応台帳 — 2026-10-10

## 判断基準
**正確性が実証できない高速化は本番採用しない。** 自動注文は行わず、現物買い/保有株売り/現金50万円/夜1回の方針を維持する。価格データ・保有資産は公開GitHubへ記録しない。修正後には「50万円が何円になったか」だけでなく、各売買の現物数量・約定日・価格・税金・株式分割・未約定・残高を再検証する。

## 優先順位と状況
| 優先度 | GitHub Issue | 内容 | 現在の状況 |
|---|---|---|---|
| P0 | #2 | 株式分割、配当、調整後/未調整価格と損益 | **未解決、成績は暫定** |
| P0 | #3 | 先読み禁止、欠損、取引停止、現物のみ | **基本テストあり、全条件未検証** |
| P1 | #4 | 買い銘柄の順位、現金管理、売却選択 | **未解決** |
| P1 | #5 | 指標の正確性を保った高速化 | **回帰テスト追加、全面照合未実施** |
| P1 | #6 | 条件の過剰適合、未来期間からの漏洩 | **時系列の分離済み、全面検証未了** |
| P2 | #7 | 無料データ遅延、当日注文、公開情報 | **データ遅延継続、実注文不可** |

## 今回対応
1. `fast_strategy_grid.py` は出力を `validation_status=PROVISIONAL_UNVERIFIED` と表示。Issue #2–#6 が解決するまで儲けの数字を検証済みと表現しない。
2. 独立した数式を使う `tests/test_accuracy_regression.py` を追加：前日比、5/20日騰落、出来高倍率、移動平均トレンドを計算の再利用結果と突合。評価期間以後の価格を変更しても、以前の約定結果が変わらないことも確認するテスト。
3. `test-walkforward.yml` は軽量な単体・回帰テストを自動実行。無料枠のGitHub Actionsを無駄に消費しないよう、`fast-strategy-grid.yml` の全銘柄Neon評価は **workflow_dispatch** のみ。コード更新のたびに重複した全件バックテストを起動しない。
4. GitHubのIssueごとに修正事項をチェックリスト化。重大P0が解決するまで全件最適化結果は暫定で、実口座に使う指標にはしない。

## 終了判定
- P0: 点検ケースで企業行動前後の株価×株数、入出金、損益が一致する。未来の変化で過去の注文が変わらない。現物制限を保証。
- P1: 正確な基準エンジンと高速版が、同一条件で全約定・資金曲線・選択銘柄・手数料に関して一致。遅延する場合のデータ準備/実行時間をベンチマーク。
- P2: 新鮮な無料データを合法的に扱えることを確認。使用不能なら候補欄は「データ取得対象外」と明記。

参照: https://github.com/mleuatd/japan-stock-lab/issues


## 2026-10-10 通常チャットからの実修正（Issue #4 部分対応）

- 修正コミット: `dde231e68fd967cfb7027f957b40cd0f34a14fc7`。 `february_walkforward.py` の新規買い候補順位を「銘柄コード辞書順」から「当日終値までで計算したlookback期間の調整後騰落率降順（同点コード順）」に変更。未来価格を順位に使わない。
- 回帰テスト追加コミット: `a028e2f612a9d8ab2d53da13abbb39cfa2961fce`。 `tests/test_february_priority.py` で現金制約下の順位と未来価格の変更に対する初回注文の不変性を確認するテストを追加。
- 軽量CI登録コミット: `1b706aa75ff668aea27c45acdf24f5d0de00ae9f`。Neonへの全件読み込みをせずに上記テストを走らせるよう `test-walkforward.yml` を更新。
- 注意: 株式分割・配当・税金・実約定可否・銘柄選択の総合最適性は依然未解決。Issue #4 全体はまだクローズしない。
- 今回確認したNeon `daily_bar`: 1,914,081行、4,714銘柄、2024-10-08から2026-07-17まで。最終評価金額は検証未了のため確定させない。

## 2026-10-10 追加修正: 学習計算量とActions重複起動
- `536da046ddaf9c25e0010c76d27955ffe72b91cc`: `frozen_train` における `bars[:i+1]` の繰り返しコピーを削除。直接の `bars[i-lookback]` / `bars[i]` 参照による同一数式へ置換。企業行動未修正のため収益値は引き続き暫定。
- `6acd9fcf74ba207dd52cf56aa6fa5f852edfec14`: 重い全Neon実データバックテストはworkflow_dispatch限定に変更。変更前に起動された既存ジョブには遡及しない。
- `8d3a7ba4b79ef750d28fe7400044318e23009454`: 全40ルール、3種類の傾向、各prefixについて従来と新判定を比較する同値性テスト追加。
- `90db4119e846627d6056cc6ea11eff35ee4d6d6b`: 軽量CIへ上記テストを組み込み。
- 実株価バックテスト `37992284803` は確認時点で実行中。更新前にトリガーされた `37992849206` もpending。実成績の成功・利益は未確認。

## 2026-10-10 追加: 欠損翌営業日フィルタ (Issue #3 部分対処)
- `4e455c34e87de72b90eb487e6835d73f89665c0b`: 訓練中の銘柄系列の次の記録行を、必ずしも市場全体の翌営業日とみなさない。隣接する市場営業日と一致しない買い/売り時点候補を排除。
- `7c54a67b7130be76726827c0fd8e715aa035acaa`: 隔日欠損の回帰テストを追加。
- `5bd4087f1b2dc3730667df8374e14c9eadf29a93`: テスト更新でも軽量CIが実行されるよう対象パスを追加。
- 欠損銘柄の市場取引停止、上場廃止、企業行動、配当についての完全検証は未完了。Issue #3 はcloseしない。


## 2026-10-10 一括企業行動・会計処理の部分実装（作業ブランチ）
- Explicit dated split and payment-date cash dividend events, positive ratio and integer-share invariant.
- Fee/slippage and positive realized profit tax parameters; negative cash invariant.
- Added tests/test_corporate_accounting.py, unified light CI test discovery.
- **P0 remains OPEN**: Neon daily_bar has adjustment_factor but not complete verified dividend payment records or fractional entitlement cashouts. Do not claim actual portfolio return until external corporate-event ledger is sourced and reconciled.
- Real Neon backtest on existing workflow is not restarted by this patch; full-Neon test is manual only.


## 2026-10-10 続行：暫定会計指標・日付境界（Issue #2/#3/#6 一部）
- Replay must begin exactly the first market session after cutoff; prevents deferred execution of the Jan 30 signal.
- Explicit corporate event dates outside loaded sessions fail closed rather than silently disappear.
- Independent totals added for realized P/L, known net dividends, final mark-to-market equity, and maximum drawdown. If ANY valuation day is unknown, maximum drawdown is unknown, not a deceptively optimistic estimate.
- Missing or invalid final position closing prices prevent final-equity claims.
- New regression cases cover skipped first session, unknown held price, accounting totals, and invalid action date.
- Outstanding: historical corporate event completeness, realistic order liquidity, dividend entitlement and tax-lot correctness, broker-specific tax rounding, survivorship, robust out-of-sample strategy evaluation. All historical investment performance remains PROVISIONAL_UNVERIFIED.

## 2026-10-10 追加修正: 配当権利と疎な価格履歴
- Dividend payout requires explicit entitlement_date earlier than payment date; credit only if same security held at entitlement-date close. No ex-date metadata => fail closed.
- Reject lookback signals based on securities missing an intervening market session.
- Still PROVISIONAL_UNVERIFIED: corporate action ledger and actual dividend payment data unavailable; cash and taxes are simplified.

## 2026-10-10 一括整合性修正 (Issue #2, #3)
- Frozen training now validates the complete lookback history is contiguous in market sessions, not only the next-two trade sessions.
- Invalid split factors fail early even when no position happens to be held. Division/rounding still needs external event validation.
- Per-account realized/unrealized P&L reconciled with cash, net dividends, and final mark-to-market via explicit accounting identity assertion.
- Dividend entitlement ledger only retains explicitly requested entitlement snapshots, not every held day (reduced memory).
- Full historical results remain provisional; no claim of actual strategy profit.

## 2026-10-10 学習の一括評価へ変更（Issue #5）
- 従来は40種類のルールごとに、全銘柄と全履歴を再走査していた。改修後は日付順に株価を1回走査し、観測済み指標を40ルールへ適用する。
- 最終検証期間の価格を学習に入れず、欠損営業日を除外する。
- 独立した遅い基準実装との候補順位・成績・対象件数の一致テストを追加。
- 一括テストが成功しても実データ全件の完走・収益確認を意味しない。Issue #2〜#7は未解決。

## 2026-10-10 出口戦略と同時保有制限 (#4)
- 計算済みの当日終値だけでSTOP_LOSS/TAKE_PROFIT/TRAILING_STOPを判定、実約定は必ず次の市場営業日寄付のみ。
- max_positions を明示し、現物・現金制約を超えた買い付けを防止。
- 分割イベントが指定された時点で、損切り基準・トレーリング高値も株数比率へ調整。
- 出口判定のテストを追加。未提供の企業行動、税務、スリッページは確定できないため引き続き暫定。

## 2026-10-10 継続修正: 企業行動が同日に重なる場合 (#2)
- 権利確定時に保有し支払日までに売却した銘柄について、支払日に別の企業行動が同時登録されても配当処理が早期中断しないよう修正。
- トレーリングストップの当日終値判定／翌営業日注文の回帰テストを追加。
- 実データの企業行動の完全性は未検証、収益額は暫定。
