import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "energy_check", Path(__file__).resolve().parents[1] / "tools/scc/energy_check.py")
energy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(energy)  # must not need a GPU, torch or pynvml


class FakeMeter:
    """Counter in millijoules that advances by a fixed amount per reading."""

    def __init__(self, step_mj=0, power_mw=60_000):
        self.total, self.step, self.power = 1_000_000, step_mj, power_mw

    def energy_mj(self):
        self.total += self.step
        return self.total

    def power_mw(self):
        return self.power


def test_measure_converts_counter_to_joules_and_per_token_figures():
    meter = FakeMeter()
    times = iter([10.0, 14.0])

    def work():
        meter.total += 800_000  # 800 J during the work
        return {"requests": 4, "output_tokens": 400}

    result = energy.measure(meter, work, clock=lambda: next(times))
    assert result["joules"] == 800 and result["seconds"] == 4 and result["mean_watts"] == 200
    assert result["joules_per_output_token"] == 2 and result["output_tokens_per_second"] == 100
    assert result["joules_per_request"] == 200


def test_measure_rejects_a_counter_that_does_not_advance_time():
    with pytest.raises(ValueError, match="did not advance"):
        energy.measure(FakeMeter(), lambda: {}, clock=lambda: 5.0)


def test_idle_samples_power_without_sleeping_for_real(monkeypatch):
    clock = iter(x * 1.0 for x in range(100))
    monkeypatch.setattr(energy.time, "perf_counter", lambda: next(clock))
    result = energy.idle(FakeMeter(step_mj=1_000, power_mw=55_500), seconds=3, sleep=lambda s: None)
    assert result["power_samples"] >= 1
    assert result["sampled_watts_min_mean_max"] == [55.5, 55.5, 55.5]


def test_committed_smoke_questions_load():
    rows = energy.load_questions()
    assert len(rows) == 10 and all(row["text"] for row in rows)


def test_cli_refuses_to_overwrite_a_report(tmp_path):
    out = tmp_path / "report.json"
    out.write_text(json.dumps({}))
    with pytest.raises(SystemExit) as exc:
        energy.main(["--output", str(out), "--skip-model"])
    assert exc.value.code == 2
