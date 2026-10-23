Introspection maps every column type the backend writes back to a Django
field (`data_types_reverse`, identity columns as `AutoField` /
`BigAutoField` / `SmallAutoField`), reports character lengths and column
defaults, and `can_introspect_default` and `can_introspect_check_constraints`
are on, so `inspectdb` writes fields with the right types and lengths.
