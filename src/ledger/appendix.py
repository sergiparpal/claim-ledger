"""Ledger appendix rendering, collapsed and expanded.

Will render one line when every claim is VERIFIED or NOT_CHECKABLE and nothing
is unreported, and the expanded form otherwise, CONTRADICTED first (R-28,
R-29), capped at 10,000 characters. Build step 8.
"""
