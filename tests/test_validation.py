import unittest

from utils.validation import is_http_url


class ValidationTests(unittest.TestCase):
    def test_http_links_are_allowed(self):
        self.assertTrue(is_http_url("https://example.com/rules"))
        self.assertTrue(is_http_url("http://localhost:8080"))
        self.assertTrue(is_http_url(""))

    def test_non_http_links_are_rejected(self):
        self.assertFalse(is_http_url("javascript:alert(1)"))
        self.assertFalse(is_http_url("example.com/rules"))


if __name__ == "__main__":
    unittest.main()
