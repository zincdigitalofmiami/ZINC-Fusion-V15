"""  Created on 15/04/2024::
------------- test_with_proxies.py -------------
 
**Authors**: L. Mingarelli
"""
import os
import fredapi

# Load local .env if present (ensures FRED_API_KEY is available for tests).
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

# Ensure SSL trust store is set (macOS Python often lacks system certs).
try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except Exception:
    pass

# Skip if key still missing
if "FRED_API_KEY" not in os.environ:
    import pytest

    pytest.skip("FRED_API_KEY not set", allow_module_level=True)

# Use real proxy settings only if provided (avoid placeholder values).
proxies = {}
http_proxy = os.getenv("FRED_HTTP_PROXY") or os.getenv("HTTP_PROXY")
https_proxy = os.getenv("FRED_HTTPS_PROXY") or os.getenv("HTTPS_PROXY")
if http_proxy:
    proxies["http"] = http_proxy
if https_proxy:
    proxies["https"] = https_proxy

fred = fredapi.Fred(
    api_key=os.environ["FRED_API_KEY"],
    proxies=proxies if proxies else None,
)

data = fred.get_series("SP500")
