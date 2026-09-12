---
title: API Authentication Troubleshooting
category: security
service: auth
environment: production
---

# API Authentication Troubleshooting

## 401 Unauthorized: "token signature invalid"

This means the token's signature doesn't verify against the keys the
service is checking against — the token itself may be well-formed but is
either forged, expired-and-reissued-with-a-different-key, or the verifying
service has a stale/incorrect public key (JWKS). Checklist:

1. Check whether the identity provider recently rotated its signing keys —
   if a JWKS cache didn't refresh, every token issued after rotation will
   fail verification service-side until the cache updates.
2. "JWKS refresh failed: connection reset" alongside signature errors
   means the auth-checking service *couldn't* fetch fresh keys — the fix
   is restoring connectivity to the JWKS endpoint, not touching tokens.
3. Confirm client clock skew isn't causing premature `exp`/`nbf` rejection.

## Distinguishing auth failures from authorization failures

A 401 means "I don't know who you are" (bad/missing/expired credentials).
A 403 means "I know who you are, and you're not allowed to do this."
Treating a 403 as an auth-service outage (and paging the identity team) is
a common false alarm — check which status code is actually being returned
before escalating.

## OAuth2 client-credentials flow

Service-to-service calls should use the client-credentials grant: the
calling service authenticates with its own `client_id`/`client_secret`
against the token endpoint and gets back a short-lived access token scoped
to what it needs — never share a human user's token between services.
