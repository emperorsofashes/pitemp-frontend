import ipaddress
import logging
import socket
from urllib.parse import urlparse

LOG = logging.getLogger(__name__)

# Maximum download size for remote images (10 MB)
MAX_REMOTE_IMAGE_SIZE = 10 * 1024 * 1024

# Request timeout in seconds (connect, read)
REQUEST_TIMEOUT = (10, 20)

# Allowed ports for HTTP/HTTPS
ALLOWED_PORTS = {80, 443}


class SSRFValidationError(Exception):
    """Raised when a URL fails SSRF validation."""
    pass


def _is_ip_restricted(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """
    Check if an IP address is restricted (private, loopback, link-local, reserved, etc.).
    
    Args:
        ip: The IP address to check
        
    Returns:
        True if restricted, False otherwise
    """
    # Use ipaddress module's built-in methods
    if ip.is_private:
        return True
    if ip.is_loopback:
        return True
    if ip.is_link_local:
        return True
    if ip.is_reserved:
        return True
    if ip.is_multicast:
        return True
    if ip.is_unspecified:
        return True
    
    # Additional checks for IPv4
    if isinstance(ip, ipaddress.IPv4Address):
        # Block 0.0.0.0/8 (current network)
        if ip in ipaddress.IPv4Network("0.0.0.0/8"):
            return True
    
    return False


def _normalize_and_validate_ip(ip_str: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """
    Normalize and validate an IP address string.
    
    Handles IPv4-mapped IPv6 addresses by converting them to IPv4.
    
    Args:
        ip_str: The IP address string
        
    Returns:
        Normalized IP address object
        
    Raises:
        SSRFValidationError: If the IP is invalid or restricted
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        raise SSRFValidationError(f"Invalid IP address: {ip_str}")
    
    # Handle IPv4-mapped IPv6 addresses (::ffff:x.x.x.x)
    if ip.version == 6 and isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            # Convert to IPv4 for validation
            ip = ip.ipv4_mapped
            LOG.debug(f"Converted IPv4-mapped IPv6 to IPv4: {ip}")
    
    # Check if restricted
    if _is_ip_restricted(ip):
        raise SSRFValidationError(f"Restricted IP address: {ip_str}")
    
    return ip


def validate_url_for_ssrf(url: str) -> str:
    """
    Validate a URL to prevent SSRF attacks.
    
    This function validates:
    - URL scheme (only http/https allowed)
    - Hostname presence
    - Absence of credentials (username/password)
    - Port restrictions (only 80, 443, or default for scheme)
    - Hostname resolves to non-restricted IPs
    - IPv4-mapped IPv6 addresses are properly handled
    
    Args:
        url: The URL to validate
        
    Returns:
        The validated URL
        
    Raises:
        SSRFValidationError: If the URL is invalid or points to a restricted address
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise SSRFValidationError(f"Invalid URL format: {e}")

    # Only allow http and https
    if parsed.scheme not in ("http", "https"):
        raise SSRFValidationError(f"Unsupported URL scheme: {parsed.scheme}")

    # Must have a hostname
    if not parsed.hostname:
        raise SSRFValidationError("URL must have a hostname")

    # Reject URLs with credentials
    if parsed.username or parsed.password:
        raise SSRFValidationError("URLs with credentials are not allowed")

    # Validate port
    if parsed.port is not None:
        if parsed.port not in ALLOWED_PORTS:
            raise SSRFValidationError(f"Port {parsed.port} is not allowed (only 80 and 443)")
    else:
        # Default ports are fine (80 for http, 443 for https)
        pass

    # Normalize hostname (lowercase, strip trailing dot)
    hostname = parsed.hostname.lower().rstrip('.')
    
    # Check for localhost variants
    localhost_variants = ["localhost"]
    if hostname in localhost_variants:
        raise SSRFValidationError("Localhost addresses are not allowed")

    # Resolve hostname to IP addresses
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
        ips = [addr[4][0] for addr in addr_infos]
    except socket.gaierror as e:
        raise SSRFValidationError(f"Failed to resolve hostname: {e}")

    if not ips:
        raise SSRFValidationError("Hostname resolved to no IP addresses")

    # Validate each resolved IP
    for ip_str in ips:
        _normalize_and_validate_ip(ip_str)

    LOG.info(f"SSRF validation passed for URL: {url} (resolved to {len(ips)} IP(s))")
    return url


def validate_redirect_url(url: str) -> bool:
    """
    Validate a redirect URL for SSRF protection.
    
    This is used during manual redirect handling to ensure each redirect
    destination is also safe.
    
    Args:
        url: The redirect URL to validate
        
    Returns:
        True if safe, False otherwise
    """
    try:
        validate_url_for_ssrf(url)
        return True
    except SSRFValidationError as e:
        LOG.warning(f"Redirect URL rejected: {e}")
        return False
