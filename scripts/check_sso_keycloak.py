"""Smoke test SSO local via Keycloak.

Preconditions:
- app running with OIDC_* configured against local Keycloak
- Keycloak running on http://localhost:8080 with realm fdr imported

This script checks:
1) OIDC metadata is reachable
2) login page exposes the SSO button
3) /auth/sso redirects to the Keycloak authorization endpoint

It does not complete the browser login form or callback exchange.
"""

from __future__ import annotations

import argparse
import sys
from urllib.parse import urlparse

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-url", default="http://keycloak.localhost:8001")
    parser.add_argument("--issuer", default="http://localhost:8080/realms/fdr")
    args = parser.parse_args()

    app_url = args.app_url.rstrip("/")
    issuer = args.issuer.rstrip("/")
    metadata_url = f"{issuer}/.well-known/openid-configuration"

    try:
        with httpx.Client(timeout=10.0, follow_redirects=False) as client:
            metadata = client.get(metadata_url)
            metadata.raise_for_status()
            data = metadata.json()
            auth_endpoint = str(data.get("authorization_endpoint") or "")
            if not auth_endpoint:
                print("ERROR: authorization_endpoint missing in metadata")
                return 1

            login = client.get(f"{app_url}/login")
            if login.status_code != 200:
                print(f"ERROR: /login returned {login.status_code}")
                return 1
            if "/auth/sso" not in login.text:
                print("ERROR: SSO button not found on /login")
                return 1

            redirect = client.get(f"{app_url}/auth/sso")
            if redirect.status_code != 303:
                print(f"ERROR: /auth/sso returned {redirect.status_code}, expected 303")
                return 1

            location = redirect.headers.get("location", "")
            if not location:
                print("ERROR: /auth/sso did not return a Location header")
                return 1

            expected_host = urlparse(auth_endpoint).netloc
            actual_host = urlparse(location).netloc
            if expected_host != actual_host:
                print(
                    "ERROR: /auth/sso redirects to unexpected host: "
                    f"{actual_host} (expected {expected_host})"
                )
                return 1

            print("OK: metadata reachable")
            print("OK: login page exposes SSO button")
            print(f"OK: /auth/sso redirects to {actual_host}")
            print("Next manual step: authenticate in Keycloak and verify callback session.")
            return 0
    except httpx.HTTPError as exc:
        print(f"ERROR: network/http failure: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
