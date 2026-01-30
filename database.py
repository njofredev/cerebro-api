import psycopg2
from psycopg2.extras import RealDictCursor
import os

# Puedes usar variables de entorno de Coolify para esto
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = "db_cotizador"
DB_USER = "tu_usuario"
DB_PASS = "tu_password"

def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        cursor_factory=RealDictCursor # Para retornar diccionarios en vez de tuplas
    )
    return conn