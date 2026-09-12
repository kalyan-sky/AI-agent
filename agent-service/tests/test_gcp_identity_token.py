"""GCP identity-token attachment (app/tools/http.py's _auth_headers).

No real GCP metadata server exists in this sandbox (or in normal local
dev/CI) — google-auth's own DefaultCredentialsError on that absence is
exactly the "no audience configured" local-dev path this exercises for
real, live, without mocking google-auth itself. The "audience is set and
a token IS obtained" path is mocked, since it needs a real metadata
server to happen for real (only true on an actual GCP instance).
"""

from unittest.mock import patch

import pytest

from app.tools.http import _auth_headers


@pytest.mark.asyncio
async def test_no_audience_means_no_auth_header():
    assert await _auth_headers("") == {}


@pytest.mark.asyncio
async def test_unset_audience_never_even_tries_to_reach_a_metadata_server():
    with patch("app.tools.http.fetch_id_token") as mock_fetch:
        await _auth_headers("")
    mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_audience_set_but_no_metadata_server_degrades_to_no_header():
    # Live, unmocked: this sandbox (like any non-GCP machine) has no
    # metadata server, so google-auth genuinely raises
    # DefaultCredentialsError here — not a simulated failure.
    headers = await _auth_headers("https://mock-enterprise-abc123.a.run.app")
    assert headers == {}


@pytest.mark.asyncio
async def test_audience_set_and_token_obtained_attaches_bearer_header():
    with patch("app.tools.http.fetch_id_token", return_value="fake.jwt.token"):
        headers = await _auth_headers("https://mock-enterprise-abc123.a.run.app")
    assert headers == {"Authorization": "Bearer fake.jwt.token"}
