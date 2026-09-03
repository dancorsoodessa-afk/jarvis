"""Network utilities and tools."""

import logging
import socket
import subprocess
import sys
from typing import Dict, Any

logger = logging.getLogger("jarvis.tools.network")


def check_internet() -> Dict[str, Any]:
    """
    Check internet connectivity by attempting to reach common DNS servers.
    
    Returns:
        Dict with 'connected' (bool) and 'details' (str)
    """
    dns_servers = [
        ("8.8.8.8", 53),      # Google DNS
        ("1.1.1.1", 53),      # Cloudflare DNS
        ("208.67.222.222", 53),  # OpenDNS
    ]
    
    for host, port in dns_servers:
        try:
            logger.debug(f"Testing DNS server {host}:{port}")
            socket.create_connection((host, port), timeout=2)
            logger.info("Internet connection OK")
            return {
                "connected": True,
                "details": f"Connected to {host}:{port}"
            }
        except (socket.timeout, socket.error):
            continue
    
    logger.warning("No internet connection detected")
    return {
        "connected": False,
        "details": "Unable to reach DNS servers"
    }


def ping(host: str, count: int = 4, timeout: int = 4) -> str:
    """
    Ping a host and return result summary.
    
    Args:
        host: Host to ping
        count: Number of ping packets
        timeout: Timeout in seconds
    
    Returns:
        Summary of ping results
    
    Raises:
        ValueError: If host is invalid
        RuntimeError: If ping command fails
    """
    if not host or not isinstance(host, str):
        raise ValueError(f"Invalid host: {host}")
    
    # Validate host is not dangerous
    if any(c in host for c in [';', '|', '&', '`', '$', '(', ')']):
        raise ValueError(f"Invalid characters in host: {host}")
    
    try:
        logger.debug(f"Pinging {host} ({count} packets)")
        
        if sys.platform == "win32":
            cmd = ["ping", "-n", str(count), "-w", str(timeout * 1000), host]
        else:
            cmd = ["ping", "-c", str(count), "-W", str(timeout * 1000), host]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 10
        )
        
        if result.returncode == 0:
            logger.info(f"Ping to {host} successful")
            # Extract summary line
            lines = result.stdout.strip().split('\n')
            return '\n'.join(lines[-3:])  # Last 3 lines usually contain stats
        else:
            logger.warning(f"Ping to {host} failed")
            return f"Ping failed: {result.stderr or 'No response'}"
    
    except subprocess.TimeoutExpired:
        logger.error(f"Ping to {host} timed out")
        raise RuntimeError(f"Ping timeout for {host}")
    except FileNotFoundError:
        logger.error("ping command not found")
        raise RuntimeError("ping command not available on this system")
    except Exception as e:
        logger.error(f"Ping error: {e}")
        raise RuntimeError(f"Ping failed: {e}")


def get_dns() -> str:
    """
    Get current DNS servers (platform-specific).
    
    Returns:
        String representation of DNS servers
    """
    try:
        logger.debug("Retrieving DNS configuration")
        
        if sys.platform == "win32":
            result = subprocess.run(
                ["ipconfig", "/all"],
                capture_output=True,
                text=True,
                timeout=5
            )
            # Parse DNS servers from output
            dns_servers = []
            for line in result.stdout.split('\n'):
                if 'DNS Servers' in line or 'DNS Server' in line:
                    dns_servers.append(line.strip())
            return '\n'.join(dns_servers) or "Could not retrieve DNS"
        else:
            result = subprocess.run(
                ["cat", "/etc/resolv.conf"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout or "Could not retrieve DNS"
    
    except Exception as e:
        logger.error(f"Failed to get DNS: {e}")
        return f"Error retrieving DNS: {e}"
