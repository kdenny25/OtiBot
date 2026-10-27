-- Runs once when the postgres volume is first created.
-- Same table as historical_data/db_setup/db_setup.py, without the DROP.
CREATE TABLE IF NOT EXISTS crypto_pair (
    ID serial PRIMARY KEY,
    Symbol varchar (50),
    OpenDateTime date,
    Interval integer,
    OpenTime bigint NOT NULL,
    Open decimal,
    High decimal,
    Low decimal,
    Close decimal,
    Volume decimal,
    CloseTime bigint NOT NULL,
    QuoteAssesVol decimal,
    NumTrades integer,
    TakerBuyBaseAssetVol decimal,
    TakerBuyQuoteAssetVol decimal
);
CREATE INDEX IF NOT EXISTS crypto_pair_lookup ON crypto_pair (Symbol, Interval, OpenDateTime);
