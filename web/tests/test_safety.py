import socket

import pytest

from server import safety
from server.errors import ApiError
from server.ratelimit import Limiter, client_key


def code_of(url, **kw):
    with pytest.raises(ApiError) as caught:
        safety.validate_url(url, **kw)
    assert caught.value.status == 400
    return caught.value.code


# --------------------------------------------------------------------------- which links are accepted
@pytest.mark.parametrize("url,code", [
    ("file:///etc/passwd", "bad_scheme"),
    ("ftp://vimeo.com/x", "bad_scheme"),
    ("javascript:alert(1)", "bad_scheme"),
    ("vimeo.com/123", "bad_scheme"),
    ("ytsearch:cats", "bad_scheme"),
    ("ytsearch50:cats", "bad_scheme"),
    ("http://127.0.0.1/", "ip_literal"),
    ("http://[::1]/", "ip_literal"),
    ("http://169.254.169.254/latest/meta-data/", "ip_literal"),
    ("http://10.0.0.5/", "ip_literal"),
    ("https://2130706433/", "bad_url"),          # 127.0.0.1 written as one number
    ("https://0x7f.1/", "bad_url"),
    ("https://localhost/", "bad_url"),
    ("https://printer.local/", "bad_url"),
    ("https://intranet.corp/", "bad_url"),
    ("https://metadata.internal/", "bad_url"),
    ("https://user:pw@vimeo.com/", "bad_url"),
    ("https://vimeo.com:22/", "bad_port"),
    ("https://vimeo.com:8080/", "bad_port"),
    ("https://vimeo.com:99999999/", "bad_url"),
    ("https://exa mple.com/", "bad_url"),
    ("https://vimeo.com/a\nb", "bad_url"),
    ("", "bad_url"),
    ("   ", "bad_url"),
    ("https://" + "a" * 300 + ".com/", "bad_url"),
    ("https://vimeo.com/" + "x" * 3000, "bad_url"),
])
def test_rejected(url, code):
    assert code_of(url) == code


@pytest.mark.parametrize("url,host", [
    ("https://vimeo.com/123", "vimeo.com"),
    ("http://vimeo.com/123", "vimeo.com"),
    ("https://VIMEO.com/123", "vimeo.com"),
    ("https://vimeo.com:443/123", "vimeo.com"),
    ("https://example.com./x", "example.com"),
    ("  https://soundcloud.com/forss/flickermood  ", "soundcloud.com"),
    ("https://www.dailymotion.com/video/x8", "www.dailymotion.com"),
    ("https://münchen.de/x", "xn--mnchen-3ya.de"),
])
def test_accepted(url, host):
    assert safety.validate_url(url).host == host


# --------------------------------------------------------------------------- what the name resolves to
@pytest.mark.parametrize("address", [
    "10.0.0.5", "127.0.0.1", "169.254.169.254", "192.168.1.1", "172.16.0.9", "100.64.0.1", "0.0.0.0", "224.0.0.1",
    "::1", "fc00::1", "fe80::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1", "64:ff9b::7f00:1", "2002:7f00:1::",
])
def test_private_addresses_rejected(address):
    assert code_of("https://vimeo.com/1", resolver=lambda h, p: {address}) == "bad_url"


def test_one_private_address_among_public_ones_rejects():
    assert code_of("https://vimeo.com/1", resolver=lambda h, p: {"93.184.216.34", "127.0.0.1"}) == "bad_url"


@pytest.mark.parametrize("address", ["93.184.216.34", "151.101.0.1", "2606:2800:220:1:248:1893:25c8:1946"])
def test_public_addresses_accepted(address):
    assert safety.validate_url("https://vimeo.com/1", resolver=lambda h, p: {address}).host == "vimeo.com"


def test_dns_failure():
    def boom(host, port):
        raise socket.gaierror("no such host")
    assert code_of("https://vimeo.com/1", resolver=boom) == "dns_failed"
    assert code_of("https://vimeo.com/1", resolver=lambda h, p: set()) == "dns_failed"


def test_resolver_gets_standard_port():
    seen = []
    safety.validate_url("http://vimeo.com/1", resolver=lambda h, p: seen.append(p) or {"93.184.216.34"})
    safety.validate_url("https://vimeo.com/1", resolver=lambda h, p: seen.append(p) or {"93.184.216.34"})
    assert seen == [80, 443]


# --------------------------------------------------------------------------- operator policy
def test_youtube_off_and_on():
    for url in ("https://www.youtube.com/watch?v=x", "https://youtu.be/x", "https://music.youtube.com/watch?v=x", "https://www.youtube-nocookie.com/embed/x"):
        assert code_of(url, youtube="off") == "youtube_off"
        assert safety.validate_url(url, youtube="on").url == url
    assert safety.validate_url("https://notyoutube.com/x", youtube="off").host == "notyoutube.com"


def test_allow_and_block_lists():
    assert safety.validate_url("https://player.vimeo.com/video/1", allowed=("vimeo.com",)).host == "player.vimeo.com"
    assert code_of("https://soundcloud.com/x", allowed=("vimeo.com",)) == "site_blocked"
    assert code_of("https://vimeo.com/1", blocked=("vimeo.com",)) == "site_blocked"
    assert code_of("https://evilvimeo.com/1", allowed=("vimeo.com",)) == "site_blocked"     # suffix must be a whole label


# --------------------------------------------------------------------------- file names
@pytest.mark.parametrize("title,expected", [
    ('a/b\\c:d*e?f"g<h>i|j', "a b c d e f g h i j"),
    ("evil‮txt.exe", "eviltxt.exe"),                 # a right-to-left override could fake an extension
    ("zero​width", "zerowidth"),
    ("CON", "_CON"),
    ("nul.txt", "_nul.txt"),
    ("   ...   ", "download"),
    ("", "download"),
    (None, "download"),
    ("مرحبا عالم", "مرحبا عالم"),
    ("日本語のタイトル", "日本語のタイトル"),
    ("  spaced   out  ", "spaced out"),
])
def test_safe_stem(title, expected):
    assert safety.safe_stem(title) == expected


def test_safe_stem_length_and_trailing_dots():
    assert len(safety.safe_stem("x" * 500)) == 90
    assert not safety.safe_stem("name." * 40).endswith((".", " "))


# --------------------------------------------------------------------------- rate limiting
def test_limiter_allows_capacity_then_refills():
    lim = Limiter(3, 60)
    assert [lim.hit("a", now=0)[0] for _ in range(4)] == [True, True, True, False]
    allowed, wait = lim.hit("a", now=0)
    assert not allowed and 19 < wait <= 20
    assert lim.hit("a", now=20.1)[0]
    assert not lim.hit("a", now=20.2)[0]
    assert lim.hit("other", now=0)[0]


def test_limiter_memory_is_bounded():
    lim = Limiter(1, 60, max_keys=5)
    for n in range(50):
        lim.hit(f"visitor-{n}", now=float(n))
        assert len(lim._buckets) <= 5


def test_client_key_ignores_forwarded_header_without_trusted_proxy():
    a = client_key({"x-forwarded-for": "1.2.3.4"}, "9.9.9.9", 0)
    b = client_key({"x-forwarded-for": "5.6.7.8"}, "9.9.9.9", 0)
    assert a == b


def test_client_key_uses_the_address_the_proxy_saw():
    spoofed = client_key({"x-forwarded-for": "6.6.6.6, 1.2.3.4"}, "10.0.0.1", 1)
    honest = client_key({"x-forwarded-for": "1.2.3.4"}, "10.0.0.1", 1)
    assert spoofed == honest                                  # the visitor can't pick their own identity
    assert honest != client_key({"x-forwarded-for": "1.2.3.5"}, "10.0.0.1", 1)


def test_client_key_falls_back_to_peer():
    assert client_key({}, "9.9.9.9", 1) == client_key({"x-forwarded-for": "garbage"}, "9.9.9.9", 1)
    assert client_key({"x-forwarded-for": "1.2.3.4"}, "9.9.9.9", 2) == client_key({}, "9.9.9.9", 2)   # fewer entries than proxies


def test_ipv6_visitors_grouped_by_network():
    same = [client_key({}, f"2001:db8:aaaa:1::{n:x}", 0) for n in (1, 2, 0xffff)]
    assert len(set(same)) == 1
    assert client_key({}, "2001:db8:aaaa:2::1", 0) != same[0]
