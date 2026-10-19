Durations: `timedelta` values (typed as BIGINT microseconds) and
`DurationField` arithmetic with dates, times and datetimes
(`F("start") + F("length")`), exact over the whole timestamp range through
`DAYS` + `MICROSECONDS` labeled durations (a single `MICROSECONDS` duration
silently gives NULL from about 31.7 years on). See
docs/user/Known-Limitations.md.
