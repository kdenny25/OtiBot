import psycopg2

def local_db():
    conn = psycopg2.connect(
        host="localhost",
        database="crypto_data",
        user="postgres",
        password="admin",
        port='5433'
    )

    return conn