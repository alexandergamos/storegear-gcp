import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sql"))
import apply  # noqa: E402


def test_admin_email_comes_from_the_environment():
    sql = 'GRANT SELECT ON catalog_chunks TO "{{ADMIN_EMAIL}}";'
    assert apply.render(sql, {"STOREGEAR_ADMIN_EMAIL": "admin@example.test"}) == 'GRANT SELECT ON catalog_chunks TO "admin@example.test";'


def test_missing_admin_email_stops_before_any_statement():
    with pytest.raises(SystemExit):
        apply.render('GRANT USAGE ON SCHEMA public TO "{{ADMIN_EMAIL}}";', {})


def test_sql_without_placeholder_needs_nothing():
    assert apply.render("SELECT 1;", {}) == "SELECT 1;"


def test_no_sql_file_carries_a_personal_email():
    import glob
    import re
    for path in glob.glob(os.path.join(os.path.dirname(__file__), "..", "sql", "*.sql")):
        assert not re.search(r"@gmail\.com", open(path, encoding="utf-8").read()), path
