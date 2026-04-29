-- Datei: migration_add_unresolvable.sql

BEGIN TRANSACTION;

CREATE TABLE ticker_mapping_new (
    isin       TEXT PRIMARY KEY
               REFERENCES instruments(isin) ON DELETE CASCADE,
    ticker     TEXT NOT NULL,
    exchange   TEXT,
    source     TEXT NOT NULL DEFAULT 'unknown',
    verified   INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_source CHECK (
        source IN ('yfinance', 'openfigi', 'manual', 'unknown', 'unresolvable')
    )
);

INSERT INTO ticker_mapping_new
SELECT * FROM ticker_mapping;

DROP TABLE ticker_mapping;

ALTER TABLE ticker_mapping_new RENAME TO ticker_mapping;

CREATE INDEX idx_ticker_mapping_ticker ON ticker_mapping(ticker);

COMMIT;
