-- Health Engine Initial Schema
-- 6 个领域模块 + 多租户设计
-- 所有表均含 tenant_id 实现租户级隔离
-- 软删除: is_deleted 字段

-- ============================================================
-- 1. 健康档案 health_profile
-- ============================================================
CREATE TABLE IF NOT EXISTS health_profile (
    id              VARCHAR(32)  PRIMARY KEY,
    tenant_id       VARCHAR(32)  NOT NULL,

    profile_id      VARCHAR(64)  NOT NULL DEFAULT '',
    name            VARCHAR(100) NOT NULL,
    gender          VARCHAR(16)  NOT NULL DEFAULT 'other',  -- male/female/other
    birth_date      DATE         NOT NULL,
    id_card_no      VARCHAR(32),
    phone           VARCHAR(32),
    email           VARCHAR(100),
    avatar_url      VARCHAR(500),

    height_cm       DECIMAL(5,2),
    weight_kg       DECIMAL(5,2),
    blood_type      VARCHAR(8)   DEFAULT 'unknown',
    rh_factor       VARCHAR(8),

    marital_status  VARCHAR(16)  DEFAULT 'single',
    occupation      VARCHAR(100),
    education       VARCHAR(50),

    smoking_status       VARCHAR(16)  DEFAULT 'never',
    drinking_status      VARCHAR(16)  DEFAULT 'never',
    exercise_hours_week  DECIMAL(4,1) DEFAULT 0,
    sleep_hours_day      DECIMAL(3,1) DEFAULT 7.0,
    dietary_preference   VARCHAR(32)  DEFAULT 'normal',

    allergies       JSON         DEFAULT '[]',
    chronic_diseases JSON        DEFAULT '[]',
    family_history  JSON         DEFAULT '[]',
    past_surgeries  JSON         DEFAULT '[]',

    is_active       BOOLEAN      DEFAULT TRUE,
    tags            JSON         DEFAULT '[]',
    remark          TEXT,

    is_deleted      BOOLEAN      DEFAULT FALSE,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_tenant (tenant_id),
    INDEX idx_profile_id (tenant_id, profile_id),
    INDEX idx_name (tenant_id, name),
    INDEX idx_active (tenant_id, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='个人健康档案';

-- ============================================================
-- 2. 指标记录 metrics_record
-- ============================================================
CREATE TABLE IF NOT EXISTS metrics_record (
    id              VARCHAR(32)  PRIMARY KEY,
    tenant_id       VARCHAR(32)  NOT NULL,

    profile_id      VARCHAR(32)  NOT NULL,
    metrics_type    VARCHAR(32)  NOT NULL,
    value           DECIMAL(12,4) NOT NULL,
    unit            VARCHAR(16)  DEFAULT '',
    measured_at     DATETIME     NOT NULL,
    source          VARCHAR(32)  DEFAULT 'manual',
    device_id       VARCHAR(64),
    location        VARCHAR(100),

    is_abnormal     BOOLEAN      DEFAULT FALSE,
    abnormal_flag   VARCHAR(8),   -- high/low/normal

    note            VARCHAR(500),
    tags            JSON         DEFAULT '[]',

    is_deleted      BOOLEAN      DEFAULT FALSE,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_tenant (tenant_id),
    INDEX idx_profile (tenant_id, profile_id),
    INDEX idx_profile_type (tenant_id, profile_id, metrics_type),
    INDEX idx_measured_at (tenant_id, profile_id, measured_at),
    INDEX idx_abnormal (tenant_id, profile_id, is_abnormal)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='健康指标记录';

-- ============================================================
-- 3. 用药记录 medication_record
-- ============================================================
CREATE TABLE IF NOT EXISTS medication_record (
    id                   VARCHAR(32)  PRIMARY KEY,
    tenant_id            VARCHAR(32)  NOT NULL,

    profile_id           VARCHAR(32)  NOT NULL,

    drug_name            VARCHAR(200) NOT NULL,
    brand_name           VARCHAR(200),
    drug_category        VARCHAR(64),
    dosage               VARCHAR(100) NOT NULL,
    strength             VARCHAR(100),
    form                 VARCHAR(32),

    frequency            VARCHAR(16)  DEFAULT 'qd',
    frequency_detail     VARCHAR(200),
    route                VARCHAR(32)  DEFAULT '口服',
    quantity_per_dose    DECIMAL(8,2),
    duration_days        INT,

    start_date           DATE         NOT NULL,
    end_date             DATE,
    prescription_date    DATE,

    prescriber           VARCHAR(100),
    hospital             VARCHAR(200),
    prescription_no      VARCHAR(64),
    indication           VARCHAR(500),

    status               VARCHAR(16)  DEFAULT 'active',
    refill_count         INT          DEFAULT 0,
    max_refills          INT,

    reminder_enabled     BOOLEAN      DEFAULT FALSE,
    reminder_times       JSON         DEFAULT '[]',
    side_effects         JSON         DEFAULT '[]',

    notes                TEXT,
    tags                 JSON         DEFAULT '[]',

    is_deleted           BOOLEAN      DEFAULT FALSE,
    created_at           TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_tenant (tenant_id),
    INDEX idx_profile (tenant_id, profile_id),
    INDEX idx_status (tenant_id, profile_id, status),
    INDEX idx_prescription (tenant_id, prescription_no),
    INDEX idx_date_range (tenant_id, start_date, end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用药记录';

-- ============================================================
-- 4. 体检记录 checkup_record
-- ============================================================
CREATE TABLE IF NOT EXISTS checkup_record (
    id                     VARCHAR(32)  PRIMARY KEY,
    tenant_id              VARCHAR(32)  NOT NULL,

    profile_id             VARCHAR(32)  NOT NULL,
    checkup_date           DATE         NOT NULL,
    hospital               VARCHAR(200),
    department             VARCHAR(100),
    doctor                 VARCHAR(100),
    package_name           VARCHAR(200),
    checkup_type           VARCHAR(32)  DEFAULT 'annual',

    status                 VARCHAR(20)  DEFAULT 'scheduled',
    report_url             VARCHAR(500),
    overall_summary        TEXT,
    doctor_advice          TEXT,
    follow_up_required     BOOLEAN      DEFAULT FALSE,
    follow_up_date         DATE,

    tags                   JSON         DEFAULT '[]',
    notes                  TEXT,

    is_deleted             BOOLEAN      DEFAULT FALSE,
    created_at             TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at             TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_tenant (tenant_id),
    INDEX idx_profile (tenant_id, profile_id),
    INDEX idx_date (tenant_id, profile_id, checkup_date),
    INDEX idx_status (tenant_id, profile_id, status),
    INDEX idx_hospital (tenant_id, hospital)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='体检记录主表';

-- 4.1 体检项目明细
CREATE TABLE IF NOT EXISTS checkup_item (
    id              VARCHAR(32)  PRIMARY KEY,
    tenant_id       VARCHAR(32)  NOT NULL,
    checkup_id      VARCHAR(32)  NOT NULL,

    item_code       VARCHAR(64)  NOT NULL,
    item_name       VARCHAR(200) NOT NULL,
    category        VARCHAR(64),
    result          VARCHAR(500),
    value           DECIMAL(12,4),
    unit            VARCHAR(32),
    reference_range VARCHAR(200),
    is_abnormal     BOOLEAN      DEFAULT FALSE,
    abnormal_flag   VARCHAR(8),
    method          VARCHAR(100),
    remark          VARCHAR(500),

    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_checkup (tenant_id, checkup_id),
    INDEX idx_item_code (tenant_id, item_code),
    INDEX idx_abnormal (tenant_id, checkup_id, is_abnormal)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='体检项目明细';

-- ============================================================
-- 5. 健康风险评估 risk_assessment
-- ============================================================
CREATE TABLE IF NOT EXISTS risk_assessment (
    id                      VARCHAR(32)  PRIMARY KEY,
    tenant_id               VARCHAR(32)  NOT NULL,

    profile_id              VARCHAR(32)  NOT NULL,
    risk_type               VARCHAR(32)  NOT NULL,
    risk_level              VARCHAR(16)  NOT NULL,  -- low/mild/moderate/high/very_high

    score                   DECIMAL(8,2) DEFAULT 0,
    score_max               DECIMAL(8,2) DEFAULT 100,
    risk_percentage         DECIMAL(5,2),
    reference_group         VARCHAR(100),

    algorithm               VARCHAR(100),
    algorithm_version       VARCHAR(32)  DEFAULT '1.0',
    assessment_date         DATETIME     NOT NULL,

    previous_assessment_id  VARCHAR(32),
    change_from_previous    VARCHAR(16),  -- improved/worsened/stable

    summary                 TEXT,
    severity_note           TEXT,
    next_review_date        DATETIME,

    tags                    JSON         DEFAULT '[]',
    notes                   TEXT,

    is_deleted              BOOLEAN      DEFAULT FALSE,
    created_at              TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_tenant (tenant_id),
    INDEX idx_profile (tenant_id, profile_id),
    INDEX idx_profile_type (tenant_id, profile_id, risk_type),
    INDEX idx_level (tenant_id, risk_level),
    INDEX idx_assessment_date (tenant_id, assessment_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='健康风险评估';

-- 5.1 风险因子
CREATE TABLE IF NOT EXISTS risk_factor (
    id                VARCHAR(32)  PRIMARY KEY,
    tenant_id         VARCHAR(32)  NOT NULL,
    assessment_id     VARCHAR(32)  NOT NULL,

    name              VARCHAR(100) NOT NULL,
    weight            DECIMAL(6,2) DEFAULT 0,
    value             VARCHAR(200),
    is_positive       BOOLEAN      DEFAULT FALSE,
    description       TEXT,
    evidence          VARCHAR(500),

    created_at        TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_assessment (tenant_id, assessment_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风险因子明细';

-- 5.2 风险建议
CREATE TABLE IF NOT EXISTS risk_recommendation (
    id                VARCHAR(32)  PRIMARY KEY,
    tenant_id         VARCHAR(32)  NOT NULL,
    assessment_id     VARCHAR(32)  NOT NULL,

    category          VARCHAR(32)  NOT NULL,
    priority          TINYINT      DEFAULT 3,
    title             VARCHAR(200) NOT NULL,
    description       TEXT,
    target            VARCHAR(200),
    timeline          VARCHAR(100),
    references        JSON         DEFAULT '[]',

    created_at        TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_assessment (tenant_id, assessment_id),
    INDEX idx_priority (tenant_id, assessment_id, priority)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风险干预建议';

-- ============================================================
-- 6. 健康计划 health_plan
-- ============================================================
CREATE TABLE IF NOT EXISTS health_plan (
    id                        VARCHAR(32)  PRIMARY KEY,
    tenant_id                 VARCHAR(32)  NOT NULL,

    profile_id                VARCHAR(32)  NOT NULL,
    plan_name                 VARCHAR(200) NOT NULL,
    plan_type                 VARCHAR(32)  DEFAULT 'custom',

    start_date                DATE         NOT NULL,
    end_date                  DATE,
    duration_days             INT,

    source_risk_assessment_id VARCHAR(32),
    source_checkup_id         VARCHAR(32),
    created_by                VARCHAR(32)  DEFAULT 'system',
    doctor_name               VARCHAR(100),

    overall_goal              TEXT,
    goals                     JSON         DEFAULT '[]',

    status                    VARCHAR(16)  DEFAULT 'draft',

    baseline_metrics          JSON         DEFAULT '{}',
    target_metrics            JSON         DEFAULT '{}',
    current_metrics           JSON         DEFAULT '{}',

    tags                      JSON         DEFAULT '[]',
    notes                     TEXT,

    is_deleted                BOOLEAN      DEFAULT FALSE,
    created_at                TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at                TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_tenant (tenant_id),
    INDEX idx_profile (tenant_id, profile_id),
    INDEX idx_status (tenant_id, profile_id, status),
    INDEX idx_type (tenant_id, profile_id, plan_type),
    INDEX idx_date_range (tenant_id, start_date, end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='健康计划';

-- 6.1 计划任务
CREATE TABLE IF NOT EXISTS plan_task (
    id                  VARCHAR(32)  PRIMARY KEY,
    tenant_id           VARCHAR(32)  NOT NULL,
    plan_id             VARCHAR(32)  NOT NULL,

    task_id             VARCHAR(32)  NOT NULL,
    title               VARCHAR(200) NOT NULL,
    category            VARCHAR(32),
    description         TEXT,
    frequency           VARCHAR(16)  DEFAULT 'daily',
    target_value        DECIMAL(10,2),
    target_unit         VARCHAR(32),
    priority            TINYINT      DEFAULT 3,

    start_date          DATE,
    end_date            DATE,

    status              VARCHAR(16)  DEFAULT 'pending',
    progress            DECIMAL(5,1) DEFAULT 0,
    completion_date     DATE,

    related_risk_type   VARCHAR(32),
    references          JSON         DEFAULT '[]',
    notes               TEXT,

    created_at          TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_plan (tenant_id, plan_id),
    INDEX idx_status (tenant_id, plan_id, status),
    INDEX idx_priority (tenant_id, plan_id, priority)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='健康计划任务';

-- 6.2 计划里程碑
CREATE TABLE IF NOT EXISTS plan_milestone (
    id                 VARCHAR(32)  PRIMARY KEY,
    tenant_id          VARCHAR(32)  NOT NULL,
    plan_id            VARCHAR(32)  NOT NULL,

    milestone_id       VARCHAR(32)  NOT NULL,
    title              VARCHAR(200) NOT NULL,
    target_date        DATE         NOT NULL,
    description        TEXT,
    achieved           BOOLEAN      DEFAULT FALSE,
    achieved_date      DATE,
    evidence           VARCHAR(500),

    created_at         TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_plan (tenant_id, plan_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='健康计划里程碑';
