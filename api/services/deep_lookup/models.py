from dataclasses import dataclass


@dataclass
class DeepLookupResult:
    anomaly_found:       bool
    anomaly_type:        str | None      # SIGNED, FIRST_EDITION, VARIANT, ASSOCIATION, MULTIPLE
    anomaly_detail:      str | None
    edition_assessment:  str
    signature_found:     bool
    signature_detail:    str | None
    baseline_value:      float | None
    anomaly_value_low:   float | None
    anomaly_value_high:  float | None
    confidence:          float
    dealer_action:       str
    physical_checks:     list[str]
    sources_used:        list[str]
    needs_more_photos:   bool
    photo_request:       str | None
    # Internal tracking
    stage_reached:       int             # 1, 2, 3, or 4
    tokens_used:         int
    elapsed_seconds:     float
