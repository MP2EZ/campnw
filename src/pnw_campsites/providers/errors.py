"""Provider-specific exceptions."""


class FacilityNotFoundError(Exception):
    """Campground facility doesn't exist on the availability API (404)."""


class RateLimitedError(Exception):
    """API rate limit hit (429)."""


class WAFBlockedError(Exception):
    """WAF is blocking requests (403 from GoingToCamp)."""
