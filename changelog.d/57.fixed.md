A `timedelta` outside the DurationField range (more than 2**63 - 1
microseconds, e.g. `timedelta.max`) is refused with a clear `ValueError`
before it is sent, instead of a driver `OverflowError`. Known Limitations
now spells out that an update whose date/time result passes year 9999 (or
year 1) writes NULL.
