"""The durable claims-and-verdicts log.

Will append every claim with its type, verdict and scope to
.claude/claim-ledger/claims.jsonl, and accept later outcome annotations
without rewriting history (R-34, R-35).
"""
