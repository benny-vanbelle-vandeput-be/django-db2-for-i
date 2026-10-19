`allow_sliced_subqueries_with_in`: a sliced queryset in an `__in` filter
(`IN (SELECT ... OFFSET ... FETCH FIRST n ROWS ONLY)`), also in XOR and in
deletes.
