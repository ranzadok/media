class TerminalError(Exception):
    """Retrying will not help (auth, rejected media, disconnected channel)."""


class RetryableError(Exception):
    """Temporary failure (5xx, rate limit, timeout)."""


def scrub(text: str, *secrets: str) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text
