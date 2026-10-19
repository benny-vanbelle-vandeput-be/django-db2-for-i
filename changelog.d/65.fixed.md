A filter value longer than its column (e.g. `name__in=["nonexistent"]` on a
`CharField(max_length=10)`, or a value with an emoji that counts as two
UTF-16 units) failed with CWB0111 ("Input data is too big to fit into
field"). Such values are sent as typed parameters and simply match nothing;
they are never truncated. Values longer than 16370 characters raise
`NotSupportedError`.
