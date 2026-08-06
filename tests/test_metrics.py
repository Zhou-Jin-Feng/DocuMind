import unittest
from unittest.mock import patch

from prometheus_client import generate_latest

from app.observability.metrics import (
    RAGMetrics,
    start_metrics_server,
    stop_metrics_server,
)


class FakeServer:
    def __init__(self):
        self.shutdown_calls = 0
        self.close_calls = 0

    def shutdown(self):
        self.shutdown_calls += 1

    def server_close(self):
        self.close_calls += 1


class FakeThread:
    def __init__(self):
        self.join_calls = 0

    def join(self, timeout=None):
        self.join_calls += 1


class MetricsTests(unittest.TestCase):
    def tearDown(self):
        stop_metrics_server()

    @staticmethod
    def _output(metrics):
        return generate_latest(metrics.registry).decode("utf-8")

    def test_success_and_failure_metrics_are_recorded(self):
        metrics = RAGMetrics(enabled=True)
        metrics.record_query("OpenAI", "success", 0.25)
        metrics.record_query("OpenAI", "error", 0.5)
        metrics.record_no_context("OpenAI")
        metrics.record_component_error("vector.search", "RuntimeError")
        metrics.observe_embedding("OpenAI", "embedding.query", "success", 0.1)
        metrics.observe_retrieval(
            "OpenAI", "success", 0.2, result_count=3
        )
        metrics.observe_first_token("OpenAI", "success", 0.15)
        metrics.observe_llm_total("OpenAI", "success", 0.4)

        output = self._output(metrics)
        self.assertIn(
            'rag_queries_total{provider="openai",status="success"} 1.0',
            output,
        )
        self.assertIn(
            'rag_queries_total{provider="openai",status="error"} 1.0',
            output,
        )
        self.assertIn('rag_no_context_total{provider="openai"} 1.0', output)
        self.assertIn(
            'rag_component_errors_total{error_type="runtimeerror",operation="vector.search"} 1.0',
            output,
        )
        self.assertIn(
            'rag_retrieval_result_count_count{provider="openai"} 1.0',
            output,
        )

    def test_metric_labels_do_not_contain_high_cardinality_fields(self):
        metrics = RAGMetrics(enabled=True)
        metrics.record_query("provider", "success", 0.1)
        metrics.record_document_upload("accepted")
        output = self._output(metrics)
        forbidden_label_names = (
            "request_id=",
            "trace_id=",
            "query=",
            "file_name=",
            "document_id=",
            "api_key=",
        )
        for label_name in forbidden_label_names:
            self.assertNotIn(label_name, output.lower())

    def test_disabled_metrics_are_noop_and_do_not_start_server(self):
        metrics = RAGMetrics(enabled=False)
        metrics.record_query("provider", "success", 0.1)
        metrics.record_component_error("operation", "RuntimeError")
        with patch("app.observability.metrics.start_http_server") as starter:
            handle = start_metrics_server("127.0.0.1", 8000, metrics)
        self.assertIsNone(handle)
        starter.assert_not_called()
        self.assertEqual(self._output(metrics), "")

    def test_metrics_server_start_is_explicit_and_idempotent(self):
        metrics = RAGMetrics(enabled=True)
        server = FakeServer()
        thread = FakeThread()
        with patch(
            "app.observability.metrics.start_http_server",
            return_value=(server, thread),
        ) as starter:
            first = start_metrics_server("127.0.0.1", 8000, metrics)
            second = start_metrics_server("127.0.0.1", 8000, metrics)

        self.assertIs(first, second)
        starter.assert_called_once_with(
            port=8000,
            addr="127.0.0.1",
            registry=metrics.registry,
        )


if __name__ == "__main__":
    unittest.main()
