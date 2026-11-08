"""Execute the real Streamlit homepage (not only syntax/unit tests) with checked-in full DB."""
import sys
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

class EmptyMarketResponse:
    def raise_for_status(self): pass
    def json(self): return []

with patch("requests.get", return_value=EmptyMarketResponse()):
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=110).run()
print("HOME_TEST_EXCEPTION_COUNT", len(app.exception))
for exception in app.exception:
    print(exception.message, file=sys.stderr)
if app.exception:
    sys.exit(1)
print("HOME_TEST_SUCCESS",len(app.title),len(app.metric))

# First paint must not unpack the 240-day history; analysis pages load it on demand.
from runtime_db import MARKER
assert not MARKER.exists(), "Homepage eagerly restored full 240-day archive"
print("HOME_LAZY_DB_OK")
app.button(key="home_scan_start").click().run()
print("HOME_SCAN_EXCEPTION_COUNT", len(app.exception))
for exception in app.exception:
    print(exception.message, file=sys.stderr)
if app.exception:
    sys.exit(1)
print("HOME_SCAN_SUCCESS",len(app.metric))
