"""
Utilities not specific to APT repositories.
"""

try:
    from urllib.parse import _ALWAYS_SAFE
except ImportError:
    from urllib import always_safe
    _ALWAYS_SAFE = frozenset(always_safe)


def quote_dotted(orig):
    """
    Escape a string as a URL using dots instead of `%xx` escapes.

    Useful for generating strings that are both URL-safe and human-readable.
    """
    dotted = ''.join([(
        char if char in _ALWAYS_SAFE else '.') for char in orig])
    # Strip duplicate dots
    result = dotted.strip('.').replace('..', '.')
    while result != dotted:
        dotted = result
        result = dotted.replace('..', '.')
    return result
