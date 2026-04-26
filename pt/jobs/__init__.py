"""Background-style jobs that aren't tied to a single API request.

Currently only contains the snapshot generator. As more jobs land
(reconciliation, FX backfill, news pre-fetch) they go here so the API
stays HTTP-handlers-only.
"""
