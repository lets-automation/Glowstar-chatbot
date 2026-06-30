"""
Semantic search package - Phase 7 (OPTIONAL).

This adds "fuzzy"/meaning-based search on top of the Text-to-SQL agent,
for questions where exact SQL filtering isn't enough (e.g. "find items
similar to X"). It is OFF by default and only activates when both
VOYAGE_API_KEY and PINECONE_API_KEY are set in .env.

NOTE FOR THIS PROJECT:
The Aastha ERP is mostly STRUCTURED, numeric data (weights, rates, counts,
dates), which Text-to-SQL already answers well. Semantic search is only
worth enabling if the client asks meaning-based questions over free-text
columns (e.g. plan remarks, comments). Enable it only if a real need shows
up - see SEMANTIC.md.
"""
