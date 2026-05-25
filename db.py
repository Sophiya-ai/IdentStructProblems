import psycopg2
from psycopg2 import pool
from config import DB_CONFIG

# Пул соединений (безопасное использование из нескольких потоков)
connection_pool = pool.SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    **DB_CONFIG
)

def get_connection():
    """Получить соединение из пула."""
    return connection_pool.getconn()

def put_connection(conn):
    """Вернуть соединение в пул."""
    connection_pool.putconn(conn)

def close_all():
    """Закрыть все соединения (вызывать при завершении приложения)."""
    connection_pool.closeall()