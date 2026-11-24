"""The ad hoc interface must remain read only and bound its result size."""
import pymysql
import pytest

from neurodb.custom_sql import MAX_ROWS, run_custom_sql, validate_sql
from neurodb.server import connect, ensure_reader


@pytest.mark.parametrize('sql', [
    'DELETE FROM trials',
    'CREATE TEMPORARY TABLE scratch (n INT)',
    'SELECT 1; DROP TABLE trials',
    'SELECT 1 /* executable comment */',
    'EXPLAIN UPDATE trials SET trial_number=trial_number',
])
def test_rejects_writes_multiple_statements_and_comments(sql):
    with pytest.raises(ValueError):
        validate_sql(sql)


def test_reader_account_has_no_temporary_table_privilege():
    ensure_reader()
    with connect(readonly=True) as conn, conn.cursor() as cursor:
        with pytest.raises(pymysql.err.OperationalError):
            cursor.execute('CREATE TEMPORARY TABLE neurodb_custom_test (n INT)')


def test_custom_queries_stream_a_bounded_preview():
    result = run_custom_sql('SELECT trial_id FROM trials')
    assert result['count'] == MAX_ROWS and result['truncated']
    assert len(result['rows']) == MAX_ROWS
    assert run_custom_sql('SHOW TABLES;')['count'] >= 19
    assert run_custom_sql('EXPLAIN ANALYZE SELECT event_id FROM events LIMIT 1')['is_plan']
