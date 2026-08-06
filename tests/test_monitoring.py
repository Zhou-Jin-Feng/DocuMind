import io
import json
import unittest

from app.observability.logging import reset_logger, setup_logger
from app.utils.monitoring import Timer, track_time


class MonitoringTests(unittest.TestCase):
    def setUp(self):
        self.console = io.StringIO()
        setup_logger(
            log_file_path=None,
            console_sink=self.console,
            console_format="json",
        )
        self.console.seek(0)
        self.console.truncate(0)

    def tearDown(self):
        reset_logger()

    def _records(self):
        return [json.loads(line) for line in self.console.getvalue().splitlines()]

    def test_generator_is_measured_until_iteration_finishes(self):
        @track_time
        def stream():
            yield "a"
            yield "b"

        generator = stream()
        self.assertEqual(self._records(), [])
        self.assertEqual(list(generator), ["a", "b"])
        record = self._records()[-1]
        self.assertEqual(record["event"], "operation_completed")
        self.assertIsInstance(record["duration_ms"], (int, float))

    def test_timer_logs_numeric_milliseconds(self):
        with Timer("test.timer") as timer:
            pass
        record = self._records()[-1]
        self.assertEqual(record["operation"], "test.timer")
        self.assertIsInstance(record["duration_ms"], (int, float))
        self.assertIsNotNone(timer.elapsed)


if __name__ == "__main__":
    unittest.main()
