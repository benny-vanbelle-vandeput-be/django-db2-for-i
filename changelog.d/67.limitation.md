Known Limitations now also covers `extra(select=..., select_params=...)`: a
bare `%s` there is an untyped parameter marker too (SQL0418); cast it, e.g.
`extra(select={"foo": "CAST(%s AS INTEGER)"}, select_params=(1,))`.
