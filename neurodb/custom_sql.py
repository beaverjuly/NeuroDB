"""Bounded, read-only ad hoc SQL for the classroom explorer and playground."""
from __future__ import annotations

import re
import time

import pymysql

from .server import connect

MAX_SQL_CHARS = 12000
MAX_ROWS = 200
MAX_EXECUTION_MS = 5000


def validate_sql(sql: str) -> str:
    """Accept one read-only statement; the reader account enforces the boundary."""
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError('Enter a SQL statement')
    if len(sql) > MAX_SQL_CHARS:
        raise ValueError(f'SQL must be at most {MAX_SQL_CHARS} characters')
    statement = sql.strip()
    quote = None
    semicolons = []
    index = 0
    while index < len(statement):
        char = statement[index]
        next_char = statement[index + 1] if index + 1 < len(statement) else ''
        if quote:
            if char == '\\':
                index += 2
                continue
            if char == quote:
                if next_char == quote:
                    index += 2
                    continue
                quote = None
        elif char in ("'", '"', '`'):
            quote = char
        elif char == ';':
            semicolons.append(index)
        elif char == '#' or (char == '/' and next_char == '*') or (char == '-' and next_char == '-'):
            raise ValueError('Comments are not supported in the classroom SQL editor')
        index += 1
    if quote:
        raise ValueError('Close the quoted SQL value or identifier')
    if semicolons:
        if len(semicolons) != 1 or statement[semicolons[0] + 1:].strip():
            raise ValueError('Run one SQL statement at a time')
        statement = statement[:semicolons[0]].rstrip()
    first = re.match(r'[A-Za-z]+', statement)
    keyword = first.group().upper() if first else ''
    if keyword in ('SELECT', 'WITH'):
        return statement
    if keyword == 'EXPLAIN' and re.match(r'(?is)^EXPLAIN\s+(?:ANALYZE\s+)?(?:SELECT|WITH)\b', statement):
        return statement
    if keyword == 'SHOW' and re.match(
        r'(?is)^SHOW\s+(?:FULL\s+)?(?:TABLES|COLUMNS|FIELDS|INDEX|INDEXES|KEYS|CREATE\s+(?:TABLE|VIEW))\b',
        statement,
    ):
        return statement
    if keyword in ('DESCRIBE', 'DESC'):
        return statement
    raise ValueError('Use SELECT, WITH, EXPLAIN SELECT, SHOW, or DESCRIBE only')


def run_custom_sql(sql: str, params=None) -> dict:
    statement = validate_sql(sql)
    conn = connect(readonly=True)
    cursor = None
    try:
        with conn.cursor() as cursor:
            cursor.execute(f'SET SESSION max_execution_time={MAX_EXECUTION_MS}')
        cursor = conn.cursor(pymysql.cursors.SSDictCursor)
        started = time.perf_counter()
        cursor.execute(statement, params)
        columns = [column[0] for column in cursor.description or ()]
        fetched = cursor.fetchmany(MAX_ROWS + 1)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return {
            'columns': columns,
            'rows': fetched[:MAX_ROWS],
            'count': min(len(fetched), MAX_ROWS),
            'truncated': len(fetched) > MAX_ROWS,
            'limit': MAX_ROWS,
            'elapsed_ms': round(elapsed_ms, 2),
            'is_plan': bool(re.match(r'(?is)^EXPLAIN\s+ANALYZE\b', statement)),
        }
    finally:
        # Abandon the unread stream before closing this one-use connection.
        # PyMySQL otherwise drains every remaining row during cursor cleanup.
        if cursor is not None and cursor._result is not None and cursor._result.unbuffered_active:
            cursor._result.unbuffered_active = False
            cursor._result.connection = None
            cursor.connection = None
            conn._result = None
        conn.close()


def dataframe(sql: str, params=None):
    """Notebook-friendly form of the same bounded read-only query path."""
    import pandas as pd

    result = run_custom_sql(sql, params)
    frame = pd.DataFrame(result['rows'], columns=result['columns'])
    if result['truncated']:
        print(f'Showing the first {result["limit"]} rows; add a narrower WHERE or LIMIT clause.')
    return frame
