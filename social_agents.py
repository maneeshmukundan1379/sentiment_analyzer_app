"""
Backward-compatible re-exports for the refactored Gemini modules.
"""

# Re-export the enrichment symbols so older imports keep working.
from platform_agents.enrichment_agent import (
    EnrichmentBatch,
    MessageEnrichment,
    enrich_records,
)
