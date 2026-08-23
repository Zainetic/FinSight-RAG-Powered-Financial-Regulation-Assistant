"""
FinSight RegTech - Centralized Rate Limiter (SlowAPI)
Provides IP-based and user-based request rate limiting across critical API endpoints.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Default limiter tracking client IP address with standard baseline
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120/minute"]
)
