"""Execute the real Streamlit homepage (not only syntax/unit tests) with checked-in full DB."""
import sys
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

class EmptyMarketResponse:
    def raise_for_status(self): pass
    def json(self): return []

with patch("requests.get", return_value=EmptyMarketResponse()):
    app = AppTest.from_file("app.py", default_timeout=110).run()
print("HOME_TEST_EXCEPTION_COUNT", len(app.exception))
for exception in app.exception:
    print(exception.message, file=sys.stderr)
if app.exception:
    sys.exit(1)
print("HOME_TEST_SUCCESS",len(app.title),len(app.metric))
