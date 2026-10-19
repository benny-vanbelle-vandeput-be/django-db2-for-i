`supports_slicing_ordering_in_compound` and `supports_parentheses_in_compound`:
the parts of `union()`, `intersection()` and `difference()` can be ordered
and sliced (`qs1.order_by(...)[:2].union(qs2.order_by(...)[:2])`), also when
the compound query is a subquery (`filter(pk__in=<union of sliced parts>)`),
and compound queries can be nested.
