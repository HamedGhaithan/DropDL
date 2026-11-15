"""Runtime settings. Everything is an environment variable so a host can be tuned without touching code."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


def _int(name: str, default: int, lo: int = 0, hi: int = 10**9) -> int:
    try:
        value = int(float(os.getenv(name, str(default))))
    except ValueError:
        value = default
    return max(lo, min(hi, value))


def _sites(name: str) -> tuple[str, ...]:
    return tuple(s.strip().lower().lstrip(".") for s in os.getenv(name, "").split(",") if s.strip())


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    max_height: int              # tallest video the server will fetch
    default_height: int
    max_filesize_mb: int         # hard cap per output file
    max_duration_min: int        # longest source video
    max_clip_min: int            # longest trimmed section
    job_ttl_min: int             # how long a finished file stays downloadable
    disk_quota_mb: int           # total space all jobs may use
    max_active: int              # downloads running at once
    max_queue: int               # waiting jobs
    per_ip_active: int           # queued + running jobs per visitor
    info_per_min: int            # link lookups per visitor per minute
    jobs_per_hour: int           # new downloads per visitor per hour
    poll_per_min: int            # status polls per visitor per minute
    job_timeout_sec: int         # wall-clock limit for one download
    trusted_proxy_hops: int      # reverse proxies in front of the app (0 = none)
    allowed_sites: tuple[str, ...]   # if set, ONLY these domains work
    blocked_sites: tuple[str, ...]
    youtube: str                 # "off" (default) or "on": YouTube blocks most datacenter servers
    proxy: str                   # optional outbound proxy for yt-dlp
    engine_update_hours: int     # 0 disables yt-dlp self-updates
    abuse_contact: str           # https:// or mailto: link shown in the footer
    enable_docs: bool
    debug_client_ip: bool        # exposes /api/whoami so an operator can check TRUSTED_PROXY_HOPS

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def max_filesize_bytes(self) -> int:
        return self.max_filesize_mb * 1024 * 1024

    @property
    def disk_quota_bytes(self) -> int:
        return self.disk_quota_mb * 1024 * 1024


def load() -> Settings:
    max_height = _int("MAX_HEIGHT", 1080, 144, 4320)
    proxy = os.getenv("YTDLP_PROXY", "").strip()
    if proxy and not proxy.startswith(("http://", "https://", "socks4://", "socks5://", "socks5h://")):
        proxy = ""
    contact = os.getenv("ABUSE_CONTACT", "").strip()
    if contact and not contact.startswith(("https://", "mailto:")):
        contact = ""
    youtube = os.getenv("YOUTUBE", "off").strip().lower()
    return Settings(
        data_dir=Path(os.getenv("DATA_DIR") or Path(tempfile.gettempdir()) / "dropdl-web"),
        max_height=max_height,
        default_height=min(_int("DEFAULT_HEIGHT", 720, 144, 4320), max_height),
        max_filesize_mb=_int("MAX_FILESIZE_MB", 300, 10, 5000),
        max_duration_min=_int("MAX_DURATION_MIN", 60, 1, 600),
        max_clip_min=_int("MAX_CLIP_MIN", 10, 1, 120),
        job_ttl_min=_int("JOB_TTL_MIN", 20, 2, 1440),
        disk_quota_mb=_int("DISK_QUOTA_MB", 2048, 100, 500000),
        max_active=_int("MAX_ACTIVE", 2, 1, 16),
        max_queue=_int("MAX_QUEUE", 20, 1, 500),
        per_ip_active=_int("PER_IP_ACTIVE", 2, 1, 20),
        info_per_min=_int("INFO_PER_MIN", 15, 1, 600),
        jobs_per_hour=_int("JOBS_PER_HOUR", 20, 1, 2000),
        poll_per_min=_int("POLL_PER_MIN", 240, 20, 6000),
        job_timeout_sec=_int("JOB_TIMEOUT_SEC", 900, 60, 7200),
        trusted_proxy_hops=_int("TRUSTED_PROXY_HOPS", 1, 0, 5),
        allowed_sites=_sites("ALLOWED_SITES"),
        blocked_sites=_sites("BLOCKED_SITES"),
        youtube="on" if youtube == "on" else "off",
        proxy=proxy,
        engine_update_hours=_int("ENGINE_UPDATE_HOURS", 12, 0, 720),
        abuse_contact=contact,
        enable_docs=os.getenv("ENABLE_DOCS", "") == "1",
        debug_client_ip=os.getenv("DEBUG_CLIENT_IP", "") == "1",
    )
