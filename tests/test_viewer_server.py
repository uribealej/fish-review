import sys
import tempfile
import unittest
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fish_review.viewer_server import ViewerServer


class ViewerServerTests(unittest.TestCase):
    def test_registered_html_is_served_and_replacements_are_fresh(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fish_raw_fluorescence.html"
            path.write_bytes(b"<html>original</html>")
            server = ViewerServer()
            try:
                url = server.register(path)
                with urlopen(url) as response:
                    self.assertEqual(response.read(), path.read_bytes())
                    self.assertIn("text/html", response.headers["Content-Type"])
                path.write_bytes(b"<html>replacement</html>")
                with urlopen(url) as response:
                    self.assertEqual(response.read(), path.read_bytes())
                with urlopen(Request(url, method="HEAD")) as response:
                    self.assertEqual(int(response.headers["Content-Length"]), path.stat().st_size)
                    self.assertEqual(response.read(), b"")
                base = url.split("/viewer/")[0]
                for route in ("/", "/viewer/unknown", "/../secret.txt"):
                    with self.assertRaises(HTTPError) as error:
                        urlopen(base + route)
                    self.assertEqual(error.exception.code, 404)
                path.unlink()
                with self.assertRaises(HTTPError) as error:
                    urlopen(url)
                self.assertEqual(error.exception.code, 404)
            finally:
                server.close()
