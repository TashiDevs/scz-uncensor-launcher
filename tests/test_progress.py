from __future__ import annotations

import unittest

import tests.context  # noqa: F401
from snowbreak_launcher.progress import OperationCancelled, WeightedProgress


class ProgressTests(unittest.TestCase):
    def test_weighted_progress_clamps_percentages(self) -> None:
        events = []
        reporter = WeightedProgress(events.append)

        reporter.step("Download", "Working", 1, 4, step_fraction=0.5)
        reporter.step("Done", "Done", 4, 4)

        self.assertAlmostEqual(events[0].fraction, 0.375)
        self.assertEqual(events[1].fraction, 1.0)
        self.assertEqual(events[1].percent, 100.0)

    def test_cancel_check_raises(self) -> None:
        reporter = WeightedProgress(cancel_check=lambda: True)
        with self.assertRaises(OperationCancelled):
            reporter.step("Download", "Working", 0, 1)


if __name__ == "__main__":
    unittest.main()
