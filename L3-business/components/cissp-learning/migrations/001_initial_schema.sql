-- Learning Management Initial Schema
-- 5 个聚合根 + 多租户设计
-- 所有表均含 tenant_id 实现租户级隔离
-- 软删除: is_deleted 字段

-- ============================================================
-- 1. 学习计划 learning_plan
-- ============================================================
CREATE TABLE IF NOT EXISTS learning_plan (
    id                  VARCHAR(32)  PRIMARY KEY,
    tenant_id           VARCHAR(32)  NOT NULL,

    plan_name           VARCHAR(200) NOT NULL,
    description         TEXT         DEFAULT '',
    category            VARCHAR(50)  DEFAULT 'certification',
    certification       VARCHAR(100),

    start_date          DATE         NOT NULL,
    end_date            DATE,

    created_by          VARCHAR(50)  DEFAULT 'self',
    owner_id            VARCHAR(32)  NOT NULL DEFAULT '',

    status              VARCHAR(20)  DEFAULT 'draft',
    -- draft / active / paused / completed / archived / cancelled

    total_hours_planned DECIMAL(8,2) DEFAULT 0.0,
    total_hours_spent  DECIMAL(8,2) DEFAULT 0.0,

    tags                TEXT,        -- JSON array
    remark              TEXT         DEFAULT '',

    created_at          DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_deleted          BOOLEAN      DEFAULT FALSE,

    INDEX idx_tenant_owner (tenant_id, owner_id),
    INDEX idx_tenant_status (tenant_id, status),
    INDEX idx_tenant_category (tenant_id, category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 1.1 学习计划里程碑 learning_plan_milestone
-- ============================================================
CREATE TABLE IF NOT EXISTS learning_plan_milestone (
    id              VARCHAR(32)  PRIMARY KEY,
    tenant_id       VARCHAR(32)  NOT NULL,
    plan_id         VARCHAR(32)  NOT NULL,

    milestone_id    VARCHAR(32)  NOT NULL,
    title           VARCHAR(200) NOT NULL,
    description     TEXT         DEFAULT '',
    target_date     DATE         NOT NULL,
    achieved        BOOLEAN      DEFAULT FALSE,
    achieved_date   DATE,

    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_plan (tenant_id, plan_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 1.2 学习计划目标 learning_plan_objective
-- ============================================================
CREATE TABLE IF NOT EXISTS learning_plan_objective (
    id              VARCHAR(32)  PRIMARY KEY,
    tenant_id       VARCHAR(32)  NOT NULL,
    plan_id         VARCHAR(32)  NOT NULL,

    objective_id    VARCHAR(32)  NOT NULL,
    title           VARCHAR(200) NOT NULL,
    description     TEXT         DEFAULT '',
    target_date     DATE,
    achieved        BOOLEAN      DEFAULT FALSE,
    achieved_date   DATE,
    evidence        TEXT         DEFAULT '',

    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_plan (tenant_id, plan_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 2. 知识点 knowledge_point
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge_point (
    id              VARCHAR(32)  PRIMARY KEY,
    tenant_id       VARCHAR(32)  NOT NULL,

    title           VARCHAR(200) NOT NULL,
    description     TEXT         DEFAULT '',
    content         MEDIUMTEXT,

    domain          VARCHAR(50),  -- CISSP domain enum
    category        VARCHAR(50)  DEFAULT 'general',

    parent_id       VARCHAR(32),
    path            VARCHAR(500) DEFAULT '',
    depth           INT          DEFAULT 0,
    sort_order      INT          DEFAULT 0,

    level           VARCHAR(20)  DEFAULT 'not_started',
    -- not_started / familiar / understand / proficient / expert

    view_count      INT          DEFAULT 0,
    note_count      INT          DEFAULT 0,
    quiz_count      INT          DEFAULT 0,

    tags            TEXT,         -- JSON array
    is_leaf         BOOLEAN      DEFAULT TRUE,
    is_deleted      BOOLEAN      DEFAULT FALSE,

    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_tenant_parent (tenant_id, parent_id),
    INDEX idx_tenant_domain (tenant_id, domain),
    INDEX idx_tenant_path (tenant_id, path),
    INDEX idx_tenant_level (tenant_id, level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 3. 笔记 note
-- ============================================================
CREATE TABLE IF NOT EXISTS note (
    id              VARCHAR(32)  PRIMARY KEY,
    tenant_id       VARCHAR(32)  NOT NULL,

    title           VARCHAR(200) NOT NULL,
    content         MEDIUMTEXT,
    summary         TEXT         DEFAULT '',

    knowledge_point_id VARCHAR(32),
    plan_id         VARCHAR(32),
    owner_id        VARCHAR(32)  NOT NULL DEFAULT '',

    is_draft        BOOLEAN      DEFAULT TRUE,
    is_public       BOOLEAN      DEFAULT FALSE,

    format          VARCHAR(20)  DEFAULT 'markdown',
    word_count      INT          DEFAULT 0,
    char_count      INT          DEFAULT 0,
    line_count      INT          DEFAULT 0,

    tags            TEXT,         -- JSON array

    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_deleted      BOOLEAN      DEFAULT FALSE,

    INDEX idx_tenant_owner (tenant_id, owner_id),
    INDEX idx_tenant_kp (tenant_id, knowledge_point_id),
    INDEX idx_tenant_plan (tenant_id, plan_id),
    INDEX idx_tenant_draft (tenant_id, is_draft)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 4. 测验 quiz
-- ============================================================
CREATE TABLE IF NOT EXISTS quiz (
    id              VARCHAR(32)  PRIMARY KEY,
    tenant_id       VARCHAR(32)  NOT NULL,

    title           VARCHAR(200) NOT NULL,
    description     TEXT         DEFAULT '',
    category        VARCHAR(50)  DEFAULT 'practice',

    plan_id         VARCHAR(32),
    creator_id      VARCHAR(32)  NOT NULL DEFAULT '',

    passing_score   DECIMAL(6,2) DEFAULT 60.0,
    time_limit_minutes INT       DEFAULT 0,
    shuffle_questions BOOLEAN    DEFAULT FALSE,
    shuffle_options  BOOLEAN    DEFAULT FALSE,
    max_attempts    INT          DEFAULT 0,

    attempt_count   INT          DEFAULT 0,
    average_score   DECIMAL(6,2) DEFAULT 0.0,
    pass_count      INT          DEFAULT 0,

    is_published    BOOLEAN      DEFAULT FALSE,
    tags            TEXT,         -- JSON array

    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_deleted      BOOLEAN      DEFAULT FALSE,

    INDEX idx_tenant_creator (tenant_id, creator_id),
    INDEX idx_tenant_plan (tenant_id, plan_id),
    INDEX idx_tenant_published (tenant_id, is_published)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 4.1 测验题目 quiz_question
-- ============================================================
CREATE TABLE IF NOT EXISTS quiz_question (
    id              VARCHAR(32)  PRIMARY KEY,
    tenant_id       VARCHAR(32)  NOT NULL,
    quiz_id         VARCHAR(32)  NOT NULL,

    question_id     VARCHAR(32)  NOT NULL,
    type            VARCHAR(20)  DEFAULT 'single_choice',
    -- single_choice / multiple_choice / true_false

    content         TEXT         NOT NULL,
    options         TEXT,         -- JSON array of strings
    correct_answer  TEXT,         -- JSON array of answer indices/values
    explanation     TEXT         DEFAULT '',

    score           DECIMAL(6,2) DEFAULT 1.0,
    difficulty      TINYINT      DEFAULT 2,
    knowledge_point_id VARCHAR(32),
    sort_order      INT          DEFAULT 0,

    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_quiz (tenant_id, quiz_id),
    INDEX idx_kp (tenant_id, knowledge_point_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 4.2 测验答题记录 quiz_attempt
-- ============================================================
CREATE TABLE IF NOT EXISTS quiz_attempt (
    id              VARCHAR(32)  PRIMARY KEY,
    tenant_id       VARCHAR(32)  NOT NULL,
    quiz_id         VARCHAR(32)  NOT NULL,

    attempt_id      VARCHAR(32)  NOT NULL,
    user_id         VARCHAR(32)  NOT NULL,
    started_at      DATETIME,
    submitted_at    DATETIME,

    score           DECIMAL(8,2) DEFAULT 0.0,
    total_score     DECIMAL(8,2) DEFAULT 0.0,
    correct_count   INT          DEFAULT 0,
    total_count     INT          DEFAULT 0,
    is_passed       BOOLEAN      DEFAULT FALSE,
    time_spent_seconds INT       DEFAULT 0,

    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_quiz_user (tenant_id, quiz_id, user_id),
    INDEX idx_user (tenant_id, user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 5. 学习进度 learning_progress
-- ============================================================
CREATE TABLE IF NOT EXISTS learning_progress (
    id              VARCHAR(32)  PRIMARY KEY,
    tenant_id       VARCHAR(32)  NOT NULL,

    user_id         VARCHAR(32)  NOT NULL,
    knowledge_point_id VARCHAR(32) NOT NULL,
    plan_id         VARCHAR(32),

    total_study_time_minutes INT  DEFAULT 0,
    study_sessions  INT          DEFAULT 0,
    first_study_at  DATETIME,
    last_study_at   DATETIME,

    -- 间隔重复参数
    ease_factor     DECIMAL(6,3) DEFAULT 2.5,
    interval_days   INT          DEFAULT 0,
    repetitions     INT          DEFAULT 0,
    next_review_at  DATETIME,
    last_review_result VARCHAR(20),
    total_reviews   INT          DEFAULT 0,
    correct_reviews INT          DEFAULT 0,

    mastery         DECIMAL(5,3) DEFAULT 0.0,
    is_completed    BOOLEAN      DEFAULT FALSE,
    is_mastered     BOOLEAN      DEFAULT FALSE,

    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_deleted      BOOLEAN      DEFAULT FALSE,

    UNIQUE KEY uk_tenant_user_kp (tenant_id, user_id, knowledge_point_id),
    INDEX idx_user (tenant_id, user_id),
    INDEX idx_user_plan (tenant_id, user_id, plan_id),
    INDEX idx_next_review (tenant_id, user_id, next_review_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
