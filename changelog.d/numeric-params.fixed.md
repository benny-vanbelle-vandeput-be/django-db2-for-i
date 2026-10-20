A filter value that does not fit its column raised a driver error ("Numeric
value out of range", "Character data right truncation"): an integer out of a
`SmallIntegerField`'s (or `IntegerField`'s, `BigIntegerField`'s) range in
`__in` or `__range`, or a `Decimal` with more digits than `max_digits` /
`decimal_places` in any lookup. Such values now get a `DECIMAL` type of their
own and are compared exactly, never rounded or truncated; values that fit
keep their SQL. Values needing more than 63 digits raise `NotSupportedError`.
