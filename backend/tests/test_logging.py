"""I-04: подпись ссылок на файлы (живёт час) не попадает в access-лог."""

import logging

from app.core.logs import RedactSignatures


def test_access_log_hides_signature():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "GET", "/api/v1/files/abc?exp=1&sig=deadbeef01&v=12", "1.1", 200),
        None,
    )
    assert RedactSignatures().filter(record)
    assert "deadbeef01" not in record.getMessage()
    assert "sig=***" in record.getMessage()


def test_other_records_untouched():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "plain %s", ("text",), None)
    assert RedactSignatures().filter(record)
    assert record.getMessage() == "plain text"
