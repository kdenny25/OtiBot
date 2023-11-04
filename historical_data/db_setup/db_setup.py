import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="crypto_data",
    user="postgres",
    password="admin",
    port='5433'
)

# open a cursor to perform database operations
cur = conn.cursor()

def create_crypto_table():
    table_name = 'crypto_pair'

    # execute a command: this creates a new table
    cur.execute(f"DROP TABLE IF EXISTS {table_name};")
    cur.execute(f"CREATE TABLE {table_name} (ID serial PRIMARY KEY,"
                "Symbol varchar (50),"
                "OpenDateTime date,"
                "Interval integer,"
                "OpenTime bigint NOT NULL,"
                "Open decimal,"
                "High decimal,"
                "Low decimal,"
                "Close decimal,"
                "Volume decimal,"
                "CloseTime bigint NOT NULL,"
                "QuoteAssesVol decimal,"
                "NumTrades integer,"
                "TakerBuyBaseAssetVol decimal,"
                "TakerBuyQuoteAssetVol decimal"
                ");"
                )
    conn.commit()

    cur.close()
    conn.close()

if __name__ == '__main__':
    create_crypto_table()