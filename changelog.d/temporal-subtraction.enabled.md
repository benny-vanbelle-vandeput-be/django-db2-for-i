`supports_temporal_subtraction`: subtracting dates, times and datetimes
(`F("end") - F("start")`) gives a duration, computed in exact microseconds
with `DAYS()`, `MIDNIGHT_SECONDS()` and `MICROSECOND()` (never
`TIMESTAMPDIFF`, which assumes 30-day months). The duration skips are gone.
