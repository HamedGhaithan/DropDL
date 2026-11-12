"""Actionable categories; preserve original errors for diagnostics."""
def classify(error):
    text = (error or '').lower()
    groups = (
        ('disk_space', ('no space left', 'disk full', 'not enough space', 'errno 28')),
        ('permissions', ('permission denied', 'access is denied', 'permissionerror')),
        ('dependency', ('ffmpeg is missing', 'ffprobe is missing', 'ffmpeg not found')),
        ('stalled', ('download stalled',)),
        ('rate_limited', ('http error 429', 'too many requests', 'rate-limit', 'rate limit')),
        ('bot_check', ("sign in to confirm you're not a bot", 'sign in to confirm you’re not a bot', 'confirm you are not a bot')),
        ('geo', ('available in your country', 'not available in your region', 'geo restrict', 'geo-restrict', 'blocked it in your country')),
        ('authentication', ('sign in', 'login required', 'cookies', 'http error 401', 'private video', 'members-only', 'members only')),
        ('format', ('requested format is not available', 'no video formats found')),
        ('unavailable', ('video unavailable', 'has been removed', 'not available', 'http error 404', 'does not exist')),
        ('unsupported', ('unsupported url', 'no suitable extractor')),
        ('network', ('timeout', 'timed out', 'connection', 'http error 502', 'http error 503', 'http error 504',
                     'temporary failure', 'remote end closed', 'incompleteread', 'incomplete read', 'ssl', 'eof occurred',
                     'getaddrinfo failed', 'name resolution', 'network is unreachable', 'unable to download video data',
                     'did not get any data blocks', 'fragment', 'http error 500')),
        ('forbidden', ('http error 403', 'forbidden')),
        ('worker_crash', ('worker stopped unexpectedly', 'worker finished without reporting', 'worker exited before finishing')),
    )
    return next((code for code, markers in groups if any(marker in text for marker in markers)), 'unknown' if error else None)
