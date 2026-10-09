# P0-1 実データ再現ルート

以前の全市場学習実行 #37992284803 は約69分、40ルールから `{"lookback":3,"min_return_pct":-10,"min_volume":0}` を選んだが、最終総資産は `None`。元の実行のコードは古いので本番再現とは別扱い。

## 2026-10-10 実データで否定した仮説
Neonの `daily_bar` で「終値は有効だが始値/調整後終値/出来高が欠損」の行は **0件**。従って不足した売買データを無視して終値だけ抽出しても、欠損評価は解消しない。この仮説に対するコード変更は採用しない。

## 選択した具体策
重い40ルール再学習を省略し、上記履歴で記録済みの候補ルールを固定したまま2026-02-02以後の現物紙上売買だけを再計算するCLI `--fixed-rule-json` を追加。GitHub Actions `February 2026 Frozen Walk-forward` の手動実行入力 `diagnose_fixed_rule=true` でこの経路を使う。テスト結果は外部の過去実行のルールによる**診断再現**であり、新たな学習や最適戦略の検証ではない。

再実行で照合するもの: `valuation_diagnostics.held_positions_without_final_close`、`indicative_missing_price_positions`、`final_equity`、`selection_provenance`。正式な最終資産が未知ならGateが失敗するのが**正しい安全動作**。個別証券番号と非公開株価はActionsログに出さない。市場データの追加ソースがないと価格は復元できない。

このGitHub接続はworkflow_dispatch実行アクションを公開していないため、**この変更が統合されただけでは全件再実行は開始しない**。ユーザー操作なしで偽の実データ結果を作らない。
