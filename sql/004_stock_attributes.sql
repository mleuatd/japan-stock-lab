-- Non-destructive extensible stock attribute taxonomy. Do not infer any issuer membership without evidence.
CREATE TABLE IF NOT EXISTS stock_attribute_category (
 category_code text PRIMARY KEY,
 category_name text NOT NULL,
 sort_order integer NOT NULL
);
CREATE TABLE IF NOT EXISTS stock_attribute (
 attribute_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 category_code text NOT NULL REFERENCES stock_attribute_category(category_code),
 attribute_code text NOT NULL UNIQUE,
 attribute_name text NOT NULL,
 attribute_kind text NOT NULL CHECK (attribute_kind IN ('reference','assessed','computed')),
 description text,
 is_active boolean NOT NULL DEFAULT true,
 UNIQUE(category_code,attribute_name)
);
-- Many-to-many, with dated evidence and no unverified auto-tagging.
CREATE TABLE IF NOT EXISTS stock_attribute_assignment (
 security_code text NOT NULL,
 attribute_id bigint NOT NULL REFERENCES stock_attribute(attribute_id),
 valid_from date NOT NULL,
 valid_to date,
 source text NOT NULL,
 evidence_uri text,
 confidence text NOT NULL DEFAULT 'verified' CHECK (confidence IN ('verified','user','provisional')),
 assigned_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (security_code,attribute_id,valid_from),
 CHECK (valid_to IS NULL OR valid_to>=valid_from)
);
CREATE INDEX IF NOT EXISTS stock_attribute_assignment_attribute_idx
 ON stock_attribute_assignment(attribute_id,valid_from,valid_to,security_code);
CREATE INDEX IF NOT EXISTS stock_attribute_assignment_security_idx
 ON stock_attribute_assignment(security_code,attribute_id);
-- dynamic numerical signals: store separately by as-of date, not permanent issuer labels.
CREATE TABLE IF NOT EXISTS stock_attribute_signal (
 security_code text NOT NULL,
 attribute_id bigint NOT NULL REFERENCES stock_attribute(attribute_id),
 as_of_date date NOT NULL,
 matched boolean NOT NULL,
 method_version text NOT NULL,
 evaluated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(security_code,attribute_id,as_of_date,method_version)
);
INSERT INTO stock_attribute_category(category_code,category_name,sort_order) VALUES ('industry','東証33業種',1) ON CONFLICT(category_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_001','水産・農林業','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_002','鉱業','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_003','建設業','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_004','食料品','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_005','繊維製品','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_006','パルプ・紙','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_007','化学','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_008','医薬品','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_009','石油・石炭製品','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_010','ゴム製品','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_011','ガラス・土石製品','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_012','鉄鋼','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_013','非鉄金属','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_014','金属製品','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_015','機械','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_016','電気機器','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_017','輸送用機器','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_018','精密機器','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_019','その他製品','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_020','電気・ガス業','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_021','陸運業','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_022','海運業','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_023','空運業','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_024','倉庫・運輸関連業','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_025','情報・通信業','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_026','卸売業','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_027','小売業','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_028','銀行業','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_029','証券・商品先物取引業','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_030','保険業','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_031','その他金融業','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_032','不動産業','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('industry','industry_033','サービス業','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute_category(category_code,category_name,sort_order) VALUES ('theme','テーマ・事業領域',2) ON CONFLICT(category_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_001','半導体','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_002','半導体製造装置','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_003','AI','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_004','生成AI','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_005','データセンター','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_006','クラウド','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_007','サイバーセキュリティ','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_008','ロボット','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_009','FA','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_010','DX','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_011','SaaS','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_012','電子部品','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_013','自動車','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_014','EV','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_015','電池','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_016','水素','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_017','再生可能エネルギー','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_018','原子力','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_019','防衛','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_020','宇宙','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_021','インフラ','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_022','建設資材','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_023','物流','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_024','海運','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_025','航空','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_026','医療機器','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_027','バイオ','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_028','創薬','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_029','介護','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_030','教育','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_031','ゲーム','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_032','アニメ','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_033','コンテンツ','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_034','広告','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_035','旅行','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_036','インバウンド','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_037','ホテル','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_038','外食','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_039','食品','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_040','小売','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_041','EC','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_042','ドラッグストア','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_043','化粧品','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_044','アパレル','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_045','住宅','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_046','不動産','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_047','金融','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_048','フィンテック','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_049','保険','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_050','農業','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_051','漁業','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_052','リサイクル','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_053','環境','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_054','脱炭素','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('theme','theme_055','地方創生','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute_category(category_code,category_name,sort_order) VALUES ('business','事業モデル',3) ON CONFLICT(category_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_001','製造業','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_002','ソフトウェア開発','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_003','受託開発','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_004','ITサービス','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_005','商社','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_006','卸売','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_007','直販','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_008','小売店舗運営','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_009','フランチャイズ','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_010','サブスクリプション','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_011','広告収入','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_012','プラットフォーム','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_013','EC運営','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_014','BtoB','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_015','BtoC','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_016','BtoG','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_017','輸出中心','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_018','国内中心','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_019','海外展開','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_020','OEM','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_021','研究開発型','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_022','設備投資型','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_023','労働集約型','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('business','business_024','知的財産型','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute_category(category_code,category_name,sort_order) VALUES ('scale','企業規模・社歴',4) ON CONFLICT(category_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('scale','scale_001','超大型株','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('scale','scale_002','大型株','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('scale','scale_003','中型株','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('scale','scale_004','小型株','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('scale','scale_005','超小型株','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('scale','scale_006','グロース企業','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('scale','scale_007','スタートアップ系上場企業','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('scale','scale_008','老舗企業','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('scale','scale_009','新興上場企業','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('scale','scale_010','上場10年以上','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute_category(category_code,category_name,sort_order) VALUES ('finance','財務・投資特性',5) ON CONFLICT(category_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_001','高配当','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_002','無配','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_003','連続増配','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_004','累進配当','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_005','株主優待あり','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_006','自己株買い活発','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_007','低PER','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_008','低PBR','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_009','高ROE','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_010','高ROIC','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_011','高営業利益率','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_012','高成長売上','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_013','高成長利益','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_014','黒字継続','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_015','赤字継続','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_016','財務健全','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_017','高自己資本比率','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_018','実質無借金','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_019','負債比率高','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_020','キャッシュリッチ','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_021','フリーCF黒字','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_022','景気敏感','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_023','ディフェンシブ','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_024','景気後退耐性','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_025','円安恩恵','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('finance','finance_026','円高恩恵','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute_category(category_code,category_name,sort_order) VALUES ('market','上場区分',6) ON CONFLICT(category_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('market','market_001','東証プライム','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('market','market_002','東証スタンダード','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('market','market_003','東証グロース','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('market','market_004','地方証券取引所','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('market','market_005','上場廃止予定','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('market','market_006','IPOから1年以内','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('market','market_007','監理銘柄','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('market','market_008','整理銘柄','reference') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute_category(category_code,category_name,sort_order) VALUES ('technical','株価・出来高シグナル',7) ON CONFLICT(category_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('technical','technical_001','直近1か月上昇','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('technical','technical_002','直近1か月下落','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('technical','technical_003','52週高値更新','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('technical','technical_004','52週安値更新','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('technical','technical_005','5か月低水準','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('technical','technical_006','出来高急増','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('technical','technical_007','短期上昇トレンド','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('technical','technical_008','長期上昇トレンド','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('technical','technical_009','短期下降トレンド','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('technical','technical_010','ボラティリティ高','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('technical','technical_011','ボラティリティ低','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('technical','technical_012','TOP30連続入り','computed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute_category(category_code,category_name,sort_order) VALUES ('region','地域・店舗',8) ON CONFLICT(category_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('region','region_001','高知県本社','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('region','region_002','四国本社','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('region','region_003','関西本社','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('region','region_004','首都圏本社','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('region','region_005','高知市内店舗あり','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('region','region_006','薊野から自転車圏の店舗あり','assessed') ON CONFLICT(attribute_code) DO NOTHING;
INSERT INTO stock_attribute(category_code,attribute_code,attribute_name,attribute_kind) VALUES ('region','region_007','海外売上比率高','computed') ON CONFLICT(attribute_code) DO NOTHING;
