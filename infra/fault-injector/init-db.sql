-- Create fault_flag table
CREATE TABLE IF NOT EXISTS fault_flag (
    id SERIAL PRIMARY KEY,
    fault_name VARCHAR(255) NOT NULL UNIQUE,
    flag BOOLEAN DEFAULT FALSE
);

-- Insert default fault flags (disabled by default)
INSERT INTO fault_flag (fault_name, flag)
VALUES
    ('KAFKA_SCHEMA_MISMATCH_BOOKING_DETAILS', FALSE),
    ('POSTGRES_STATEMENT_TIMEOUT_FAULT', FALSE),
    ('ES_APPLICATION_TIMEOUT', FALSE),
    ('ES_APPLICATION_INDEX', FALSE)
ON CONFLICT (fault_name) DO NOTHING;
