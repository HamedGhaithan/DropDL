import dataclasses
import time

import pytest

from server import runner
from server.errors import ApiError, RunError
from server.jobs import JobManager
from tests.conftest import FakeEngine, Gate, fake_run, spec, wait_for


@pytest.fixture
def make(settings):
    managers = []

    def build(run_fn=fake_run, **overrides):
        manager = JobManager(dataclasses.replace(settings, **overrides), FakeEngine(), run_fn)
        manager.start()
        managers.append(manager)
        return manager
    yield build
    for m in managers:
        m.stop()


def test_a_download_runs_to_the_end(make):
    manager = make()
    job = manager.submit(spec(), "me")
    wait_for(lambda: job.status == "done")
    view = manager.view(job)
    assert view["progress"] == 1.0 and view["stage"] == "done" and view["ext"] == "mp4" and view["size"] == 1000
    assert view["filename"] == "A weird title ok.mp4"                   # the title is made safe for every operating system
    assert 0 < view["expires_in"] <= manager.s.job_ttl_min * 60 and view["error"] is None
    assert job.path.read_bytes() == b"0123456789" * 100


def test_waiting_jobs_get_a_queue_position(make):
    gate = Gate()
    manager = make(gate, max_active=1, per_ip_active=10)
    first, second, third = (manager.submit(spec(), "me") for _ in range(3))
    wait_for(lambda: first.status == "running")
    assert (manager.view(second)["queue_position"], manager.view(third)["queue_position"]) == (1, 2)
    assert manager.stats() == {"queued": 2, "active": 1, "completed": 0}
    gate.release.set()
    wait_for(lambda: third.status == "done")
    assert manager.view(third)["queue_position"] == 0 and manager.stats()["completed"] == 3


def test_one_visitor_cannot_hog_the_server(make):
    manager = make(Gate(), per_ip_active=2)
    manager.submit(spec(), "me")
    manager.submit(spec(), "me")
    with pytest.raises(ApiError) as caught:
        manager.submit(spec(), "me")
    assert (caught.value.status, caught.value.code) == (429, "too_many_active") and caught.value.retry_after
    manager.submit(spec(), "someone-else")                               # other visitors are unaffected


def test_full_queue_and_full_disk_say_so(make, monkeypatch):
    manager = make(Gate(), max_active=1, max_queue=1, per_ip_active=10)
    manager.submit(spec(), "a")
    wait_for(lambda: manager.stats()["active"] == 1)
    manager.submit(spec(), "b")
    with pytest.raises(ApiError) as caught:
        manager.submit(spec(), "c")
    assert (caught.value.status, caught.value.code) == (503, "busy")
    manager = make(Gate())
    monkeypatch.setattr(manager, "_disk_used", lambda: 10 ** 12)
    with pytest.raises(ApiError) as caught:
        manager.submit(spec(), "a")
    assert caught.value.code == "storage_full"


def test_cancelling_a_waiting_job_means_it_never_runs(make):
    gate = Gate()
    manager = make(gate, max_active=1, per_ip_active=10)
    first, second = manager.submit(spec(), "me"), manager.submit(spec(), "me")
    wait_for(lambda: first.status == "running")
    manager.cancel(second)
    assert second.status == "cancelled" and manager.view(second)["error"]["code"] == "cancelled"
    gate.release.set()
    wait_for(lambda: first.status == "done")
    assert gate.started == 1 and not second.dir.exists()


def test_cancelling_a_running_job_stops_it(make):
    manager = make(Gate())
    job = manager.submit(spec(), "me")
    wait_for(lambda: job.status == "running")
    manager.cancel(job)
    wait_for(lambda: job.status == "cancelled")
    assert not job.dir.exists()


def test_failures_are_reported_and_cleaned_up(make):
    def failing(sp, outdir, settings, env, cancel, on_update):
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "media.mp4.part").write_bytes(b"half")
        raise RunError("private", "That video is private or unavailable.")
    manager = make(failing)
    job = manager.submit(spec(), "me")
    wait_for(lambda: job.status == "error")
    view = manager.view(job)
    assert view["error"] == {"code": "private", "message": "That video is private or unavailable."} and view["expires_in"] is None
    assert not job.dir.exists()


def test_a_crash_inside_a_job_does_not_kill_the_worker(make):
    calls = []

    def sometimes_crashes(sp, outdir, settings, env, cancel, on_update):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("bug")
        return fake_run(sp, outdir, settings, env, cancel, on_update)
    manager = make(sometimes_crashes, max_active=1, per_ip_active=5)
    bad, good = manager.submit(spec(), "me"), manager.submit(spec(), "me")
    wait_for(lambda: good.status == "done")
    assert bad.status == "error" and bad.error_code == "failed"


def test_only_well_formed_ids_are_looked_up(make):
    manager = make()
    job = manager.submit(spec(), "me")
    assert manager.get(job.id) is job
    for bad in ("", "x", "../etc/passwd", job.id + "/..", job.id.upper() + "!", None):
        assert manager.get(bad) is None


def test_delete_removes_the_file_immediately(make):
    manager = make()
    job = manager.submit(spec(), "me")
    wait_for(lambda: job.status == "done")
    path = job.dir
    manager.delete(job)
    assert manager.get(job.id) is None and not path.exists()


# --------------------------------------------------------------------------- the janitor
def test_finished_jobs_expire(make):
    manager = make(job_ttl_min=2)
    job = manager.submit(spec(), "me")
    wait_for(lambda: job.status == "done")
    manager.sweep(now=time.time() + 60)
    assert manager.get(job.id) is job
    manager.sweep(now=time.time() + 2 * 60 + 5)
    assert manager.get(job.id) is None and not job.dir.exists()


def test_disk_quota_evicts_the_oldest_finished_files(make):
    def big(sp, outdir, settings, env, cancel, on_update):
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / "media.mp4"
        path.write_bytes(b"x" * 600_000)
        return runner.Result(path=path, title="t", ext="mp4", size=600_000)
    manager = make(big, disk_quota_mb=1, per_ip_active=5, max_active=1)
    old = manager.submit(spec(), "me")
    wait_for(lambda: old.status == "done")
    new = manager.submit(spec(), "me")
    wait_for(lambda: new.status == "done")
    manager.sweep()
    assert manager.get(old.id) is None and manager.get(new.id) is new


def test_strays_and_stuck_jobs(make):
    manager = make(Gate(), job_timeout_sec=60)
    stray = manager.s.jobs_dir / "left-over-from-last-run"
    stray.mkdir(parents=True)
    (stray / "media.mp4").write_bytes(b"x")
    job = manager.submit(spec(), "me")
    wait_for(lambda: job.status == "running")
    manager.sweep(now=time.time() + 30)
    assert not stray.exists() and not job.cancel.is_set()
    manager.sweep(now=time.time() + 60 + 61)
    assert job.cancel.is_set()


def test_start_wipes_what_a_previous_run_left(settings):
    leftover = settings.jobs_dir / "old"
    leftover.mkdir(parents=True)
    (leftover / "media.mp4").write_bytes(b"x")
    manager = JobManager(settings, FakeEngine(), fake_run)
    manager.start()
    try:
        assert not leftover.exists()
    finally:
        manager.stop()
