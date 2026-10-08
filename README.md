# japan-stock-lab

日本株の過去株価データ収集・分析・300万円の仮想売買研究。**実際の証券注文は行いません。**

## 初期設定
1. J-Quantsで無料アカウントを作成し、APIキーを発行する。
2. GitHub `Settings → Secrets and variables → Actions` に `JQUANTS_API_KEY` として登録する（キーをファイルに書かない）。
3. `Actions → Collect delayed J-Quants history → Run workflow` で初回実行する。
4. 成功すると過去の日足を日付単位の圧縮CSVで保存します。既存取得分をスキップして次の実行時に続けます。

## 保存について
出力: `archive/daily/YYYY/MM/YYYY-MM-DD.csv.gz`。公開リポジトリにはAPIデータをコミットしません。Actions cache・artifactは**一時保存**であり永続保管ではありません。重要な履歴は、利用規約を確認した上で別途非公開の保存先にバックアップしてください。無料プランの12週間遅延に注意してください。

## 注意点
Secretsの存在はワークフロー実行時に値を表示せず検証できます。全銘柄の完全な価格履歴を保証するものではありません。欠損や取引停止日・株式分割等の検証はバックテスト前に別途必要です。自動実行は平日（GitHub側の遅延あり）で、発注機能はありません。
