"""Real downloads from real sites. Skipped unless RUN_NETWORK_TESTS=1 (they need internet and take about a minute)."""
import os
import threading

import pytest

from server import runner
from server.engine import Engine
from server.errors import ApiError

pytestmark = pytest.mark.skipif(os.getenv("RUN_NETWORK_TESTS") != "1", reason="set RUN_NETWORK_TESTS=1 to run tests that use the internet")
ARCHIVE = "https://archive.org/details/BigBuckBunny_124"


def test_link_lookup_and_unsupported_sites(settings):
    env = Engine(settings).env()
    info = runner.fetch_info(ARCHIVE, settings, env)
    assert info["title"] == "Big Buck Bunny" and info["has_video"] and info["heights"] and "@" not in info["uploader"]
    with pytest.raises(ApiError) as caught:
        runner.fetch_info("https://example.com/some/video.mp4", settings, env)      # the "fetch any URL" extractor is off
    assert caught.value.code == "unsupported"


def test_trimmed_download_is_small_and_complete(settings, tmp_path):
    sp = runner.normalise_spec(ARCHIVE, "video", 720, "mp4", 30, 38, settings)
    updates = []
    result = runner.run_download(sp, tmp_path / "job", settings, Engine(settings).env(), threading.Event(), updates.append)
    assert result.ext == "mp4" and 50_000 < result.size < 5_000_000 and result.title == "Big Buck Bunny"
    assert [p.name for p in result.path.parent.iterdir()] == ["media.mp4"]            # nothing but the finished file is left
    assert updates and updates[-1]["progress"] >= 0.95
