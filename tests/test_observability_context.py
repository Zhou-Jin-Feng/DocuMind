import unittest

from app.observability.context import (
    get_request_id,
    get_trace_id,
    request_context,
)


class RequestContextTests(unittest.TestCase):
    def test_same_request_uses_same_ids(self):
        with request_context() as context:
            self.assertEqual(get_request_id(), context.request_id)
            self.assertEqual(get_trace_id(), context.trace_id)
            self.assertEqual(get_request_id(), get_request_id())

    def test_different_requests_use_different_ids(self):
        with request_context() as first:
            first_ids = (first.request_id, first.trace_id)
        with request_context() as second:
            second_ids = (second.request_id, second.trace_id)
        self.assertNotEqual(first_ids, second_ids)

    def test_context_is_cleaned_after_exception(self):
        with self.assertRaisesRegex(RuntimeError, "boom"):
            with request_context(request_id="request-1", trace_id="trace-1"):
                self.assertEqual(get_request_id(), "request-1")
                raise RuntimeError("boom")
        self.assertIsNone(get_request_id())
        self.assertIsNone(get_trace_id())

    def test_nested_context_restores_outer_context(self):
        with request_context(request_id="outer", trace_id="outer-trace"):
            with request_context(request_id="inner", trace_id="inner-trace"):
                self.assertEqual(get_request_id(), "inner")
            self.assertEqual(get_request_id(), "outer")
            self.assertEqual(get_trace_id(), "outer-trace")


if __name__ == "__main__":
    unittest.main()
