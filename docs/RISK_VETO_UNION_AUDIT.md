# TRAIN専用危険パターン除外後の損失監査

Issue #42 に対する歴史データの複合除外（union）監査。個別条件が危険でも、残った銘柄群の損失率が低くなるとは限らないため、同一日時・同一入力品質の基準群、除外群、非該当群を比較する。

## 情報漏洩防止

既存 downside_pattern_run_v2 の学習期間（2026-01-30まで）の統計だけを使い、20日後の下落・終値5%下落・途中5%下落について 500件、100銘柄、欠損3%以下、Z=3.9 Wilson区間、基準との差5ポイント以上で危険ルールを先に固定。評価期間（2026-02-02以後）の成績は選定条件に入力しない。

ただし、設計作業中に2026年2～7月の過去結果の存在や一部集計を既に見ている。したがって本作業は **後から設計した過去検証** であり、真に未知の将来期間での成功の証明ではない。これは最重要な制約。

## 評価方法

- 最新21市場営業日の全データが揃い、調整後OHLCVが検証可能で、既知のJPX注意指定がない銘柄だけを比較母集団とする。欠損は安全と解釈しない。
- 危険ルール1件以上の一致は EXCLUDED、0件は SURVIVOR。UNKNOWNは基準群にも含めず、件数を保存する。
- 当日終値での条件判定後、翌営業日調整後始値で仮想購入し、1～30営業日の調整後終値で仮想決済。片道0.1%のコストを暫定控除。翌始値から各日安値までの-3/-5/-10%も確認。
- 全30営業日分の未来が確定している基準日だけを評価する。経路中にデータ欠損があれば path_unknown として分母から除外。
- daily の日次事例には時間的重複があるため独立試行として扱わない。spaced30 も同じ銘柄を30営業日間隔に間引いた感度分析に過ぎず、銘柄間の相関は残る。
- 実売買の発注、利益確定・損切り約定の成立、上場廃止の全数処理、配当、分割・併合の完全な点検はしていない。買い推奨は常に NOT_APPROVED。

## プライベートNeon出力

sql/010_risk_veto_union_audit.sql で追加する risk_veto_union_run、risk_veto_union_cohort、risk_veto_union_rule、risk_veto_union_snapshot は既存テーブルを改変しない。再実行はコードコミットなどから作る実行キーで区別し、公開GitHubには市場の生データも証券ごとの日次株価も保存しない。

Neonでの確認:

    SELECT sampling,cohort,total,observed,missing,loss_pct,touch_loss5_pct
    FROM risk_veto_union_20day
    ORDER BY run_key DESC,sampling,cohort;

    SELECT status,count(*) FROM risk_veto_union_snapshot
    WHERE run_key=(SELECT run_key FROM risk_veto_union_run ORDER BY created_at DESC LIMIT 1)
    GROUP BY status;

結論に必要な評価は SURVIVOR の loss_pct と同じ日付の ALL の loss_pct の差、途中-5/-10%の差、未知銘柄の件数、残存数。残存群のほうが悪ければそのまま失敗と記録する。