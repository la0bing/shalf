import threading
import time
from datetime import timedelta

import pytest

from shalf.pipelines.project import PipelineError, pipeline_lock
from shalf.pipelines.schedule import run_schedule


def test_schedule_runs_in_order_and_respects_intervals():
    now = [0.0]
    calls = []

    def runner(store, repo, name):
        calls.append((now[0], name))
        if name == "flaky" and len(calls) == 2:
            raise RuntimeError("boom")
        return {"features": {}}

    def sleep(seconds):
        now[0] += seconds

    history = run_schedule(
        None,
        ".",
        [("daily", timedelta(hours=24)), ("flaky", timedelta(hours=1))],
        max_runs=5,
        sleep=sleep,
        clock=lambda: now[0],
        runner=runner,
    )
    assert [c[1] for c in calls] == ["daily", "flaky", "flaky", "flaky", "flaky"]
    assert [c[0] for c in calls] == [0, 0, 3600, 7200, 10800]  # all due at start, then hourly
    assert history[1] == ("flaky", "failed") and history[2] == ("flaky", "succeeded")  # keeps going
    with pytest.raises(ValueError):
        run_schedule(None, ".", [])


def test_pipeline_lock_serialises_runs(tmp_path):
    order = []

    def hold():
        with pipeline_lock(str(tmp_path)):
            order.append("first-start")
            time.sleep(0.5)
            order.append("first-end")

    thread = threading.Thread(target=hold)
    thread.start()
    time.sleep(0.1)
    with pipeline_lock(str(tmp_path), poll=0.05):
        order.append("second")
    thread.join()
    assert order == ["first-start", "first-end", "second"]

    with (
        pipeline_lock(str(tmp_path)),
        pytest.raises(PipelineError, match="Timed out"),
        pipeline_lock(str(tmp_path), timeout=0.1, poll=0.02),
    ):
        pass
