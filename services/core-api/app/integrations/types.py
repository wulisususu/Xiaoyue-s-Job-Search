from dataclasses import dataclass


@dataclass(slots=True)
class ImportSummary:
    companies_created: int = 0
    jobs_created: int = 0
    sources_created: int = 0
    relations_created: int = 0
    records_seen: int = 0
    sources_staled: int = 0
    jobs_staled: int = 0
    sources_updated: int = 0
    url_candidates_created: int = 0
