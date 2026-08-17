"""
Oura PHI connector validation package.

Scope of this package is intentionally narrow: prove OAuth2 connectivity and
land ONE bounded raw sample. It contains no normalization, no insight
generation, no webhook code, no scheduler, and no application server beyond
the temporary local OAuth callback listener used during this test.
"""
