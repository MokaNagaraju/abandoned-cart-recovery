-- Logical schema for the Abandoned Cart Recovery domain
-- (PostgreSQL-flavoured; adapt as needed)

CREATE TABLE customers (
    customer_id     VARCHAR(16) PRIMARY KEY,          -- CUS-000001
    email           VARCHAR(255) NOT NULL UNIQUE,
    phone           VARCHAR(20),
    first_name      VARCHAR(100) NOT NULL,
    last_name       VARCHAR(100) NOT NULL,
    country_code    CHAR(2) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE consents (
    consent_id      VARCHAR(16) PRIMARY KEY,          -- CON-000001
    customer_id     VARCHAR(16) NOT NULL REFERENCES customers(customer_id),
    channel         VARCHAR(10) NOT NULL CHECK (channel IN ('email','sms')),
    status          VARCHAR(10) NOT NULL CHECK (status IN ('opt_in','opt_out')),
    effective_from  TIMESTAMPTZ NOT NULL,
    effective_to    TIMESTAMPTZ,
    source          VARCHAR(50) NOT NULL
);

CREATE TABLE sessions (
    session_id      VARCHAR(16) PRIMARY KEY,
    customer_id     VARCHAR(16) REFERENCES customers(customer_id),
    device_id       VARCHAR(20) NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL,
    ended_at        TIMESTAMPTZ,
    user_agent      TEXT
);

CREATE TABLE carts (
    cart_id         VARCHAR(20) PRIMARY KEY,          -- CART-2026-000001
    customer_id     VARCHAR(16) NOT NULL REFERENCES customers(customer_id),
    session_id      VARCHAR(16) NOT NULL REFERENCES sessions(session_id),
    status          VARCHAR(20) NOT NULL CHECK (status IN ('active','abandoned','recovered','converted')),
    created_at      TIMESTAMPTZ NOT NULL,
    last_updated_at TIMESTAMPTZ NOT NULL,
    abandoned_at    TIMESTAMPTZ,
    currency        CHAR(3) NOT NULL,
    total_amount    NUMERIC(12,2) NOT NULL CHECK (total_amount >= 0)
);

CREATE TABLE cart_lines (
    cart_line_id    VARCHAR(16) PRIMARY KEY,
    cart_id         VARCHAR(20) NOT NULL REFERENCES carts(cart_id),
    product_id      VARCHAR(12) NOT NULL,
    product_name    VARCHAR(200) NOT NULL,
    quantity        INTEGER NOT NULL CHECK (quantity >= 1),
    unit_price      NUMERIC(12,2) NOT NULL,
    line_total      NUMERIC(12,2) NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL
);

CREATE TABLE campaigns (
    campaign_id     VARCHAR(20) PRIMARY KEY,          -- CMP-2026-000001
    name            VARCHAR(200) NOT NULL,
    channel         VARCHAR(10) NOT NULL,
    variant         CHAR(1) NOT NULL,
    start_at        TIMESTAMPTZ NOT NULL,
    end_at          TIMESTAMPTZ NOT NULL,
    status          VARCHAR(20) NOT NULL
);

CREATE TABLE message_templates (
    template_id     VARCHAR(16) PRIMARY KEY,
    campaign_id     VARCHAR(20) NOT NULL REFERENCES campaigns(campaign_id),
    channel         VARCHAR(10) NOT NULL,
    subject         VARCHAR(300),
    body            TEXT NOT NULL,
    variant         CHAR(1) NOT NULL
);

CREATE TABLE send_attempts (
    send_id             VARCHAR(20) PRIMARY KEY,      -- SEND-2026-000001
    cart_id             VARCHAR(20) NOT NULL REFERENCES carts(cart_id),
    campaign_id         VARCHAR(20) NOT NULL REFERENCES campaigns(campaign_id),
    template_id         VARCHAR(16) NOT NULL REFERENCES message_templates(template_id),
    message_id          TEXT NOT NULL,   -- format MSG-<cart_id>-NN (01 first message, 02/03 follow-ups)
    customer_id         VARCHAR(16) NOT NULL REFERENCES customers(customer_id),
    channel             VARCHAR(10) NOT NULL,
    scheduled_at        TIMESTAMPTZ NOT NULL,
    sent_at             TIMESTAMPTZ,
    status              VARCHAR(20) NOT NULL,  -- final status; full history in message_events
    suppression_reason  VARCHAR(50)
);

-- Append-only event history for each non-suppressed send
CREATE TABLE message_events (
    event_id        VARCHAR(16) PRIMARY KEY,          -- EVT-000001
    send_id         VARCHAR(20) NOT NULL REFERENCES send_attempts(send_id),
    event_type      VARCHAR(20) NOT NULL CHECK (event_type IN ('sent','delivered','opened','clicked','bounced')),
    event_at        TIMESTAMPTZ NOT NULL
);

CREATE TABLE orders (
    order_id        VARCHAR(20) PRIMARY KEY,          -- ORD-2026-000001
    customer_id     VARCHAR(16) NOT NULL REFERENCES customers(customer_id),
    cart_id         VARCHAR(20) REFERENCES carts(cart_id),
    order_at        TIMESTAMPTZ NOT NULL,
    total_amount    NUMERIC(12,2) NOT NULL,
    currency        CHAR(3) NOT NULL,
    status          VARCHAR(20) NOT NULL
);

CREATE TABLE attributions (
    attribution_id              VARCHAR(16) PRIMARY KEY,
    order_id                    VARCHAR(20) NOT NULL REFERENCES orders(order_id),
    send_id                     VARCHAR(20) NOT NULL REFERENCES send_attempts(send_id),
    campaign_id                 VARCHAR(20) NOT NULL REFERENCES campaigns(campaign_id),
    attributed_amount           NUMERIC(12,2) NOT NULL,
    attribution_window_hours    INTEGER NOT NULL,
    is_primary                  BOOLEAN NOT NULL
);

-- Ground truth is intentionally kept outside the operational schema
-- as a separate evaluation artefact.
