# backend_app/db.py
import psycopg2
from psycopg2.extras import RealDictCursor

def get_db_connection():
    conn = psycopg2.connect(
        dbname="Legal_Simplifier_DB",
        user="postgres",
        password="root",
        host="localhost",
        port="5432"
    )
    return conn


