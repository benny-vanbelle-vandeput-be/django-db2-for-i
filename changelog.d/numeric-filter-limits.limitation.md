An out-of-range integer in an `__in` list, or a `Decimal` with more digits
than its column, raises a driver error instead of matching nothing (never
rounded or truncated); planned fix #69. See docs/user/Known-Limitations.md.
