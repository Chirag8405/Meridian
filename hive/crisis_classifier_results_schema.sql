-- Results tables for the ML crisis classifier (spark/crisis_classifier.scala).
-- See hive/crisis_features_schema.sql and FINDINGS.md for the full design
-- (label grounding, feature exclusions, and the leave-one-coin-out split).
--
-- Two LOCO directions, asymmetric by necessity (see FINDINGS.md):
--   - direction = 'TEST_ON_UST': pure single-coin LOCO. Train on USDC
--     (calm minus a chronological holdout, + USDC's own crisis rows).
--     Test on the USDC calm holdout + all of UST (100% CRISIS-labeled,
--     since UST has no calm rows in this dataset at all).
--   - direction = 'TEST_ON_USDC': necessarily coin-blended for the CALM
--     class, since UST has none to offer. Train on USDC calm (same
--     holdout scheme) + all of UST (CRISIS). Test on the USDC calm
--     holdout + USDC's own crisis rows (held out entirely, unseen).
--
-- Two model types per direction (logistic regression, random forest),
-- trained with class weighting (inverse frequency, computed fresh per
-- fold's training set) given ~89%+ CALM imbalance.

CREATE TABLE IF NOT EXISTS meridian.crisis_classifier_predictions (
    direction        STRING    COMMENT 'TEST_ON_UST or TEST_ON_USDC',
    model_type        STRING    COMMENT 'logistic_regression or random_forest',
    pair              STRING,
    project           STRING,
    window_start_ts   TIMESTAMP,
    dt                STRING,
    true_label        INT       COMMENT '1=CRISIS, 0=CALM (ground truth, from meridian.crisis_features)',
    predicted_prob    DOUBLE    COMMENT 'Model''s predicted probability of CRISIS (class 1)',
    predicted_label   INT       COMMENT 'Predicted class at the model''s default 0.5 threshold',
    baseline_risk_score DOUBLE  COMMENT 'meridian.risk_scores_baseline.risk_score for this same row, carried through for direct comparison on identical test rows',
    computed_at       TIMESTAMP
)
STORED AS ORC
TBLPROPERTIES ('orc.compress'='ZLIB');

CREATE TABLE IF NOT EXISTS meridian.crisis_classifier_metrics (
    direction          STRING    COMMENT 'TEST_ON_UST or TEST_ON_USDC',
    scorer              STRING    COMMENT 'logistic_regression, random_forest, or rule_based_baseline (risk_score) — all evaluated on the SAME test rows for direct comparison',
    n_test               BIGINT,
    n_test_crisis         BIGINT,
    n_test_calm            BIGINT,
    precision_crisis        DOUBLE  COMMENT 'Precision on the CRISIS class at the reported threshold (0.5 for models; see threshold_used for the baseline)',
    recall_crisis            DOUBLE  COMMENT 'Recall on the CRISIS class — prioritized per the project''s stated preference (missing a real crisis is worse than a false alarm), but reported alongside precision so a "cries wolf" scorer isn''t hidden',
    f1_crisis                 DOUBLE,
    pr_auc                     DOUBLE  COMMENT 'Area under the precision-recall curve, threshold-independent — the primary apples-to-apples comparison number between models and the baseline',
    threshold_used              DOUBLE  COMMENT 'Decision threshold used for the precision/recall/F1 figures. 0.5 for models; for the baseline, the risk_score value that maximizes F1 on this test set',
    computed_at                  TIMESTAMP
)
STORED AS ORC
TBLPROPERTIES ('orc.compress'='ZLIB');
