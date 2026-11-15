`supports_primitives_in_json_field`: a `JSONField` whose whole value is a
number, a string, `true`, `false` or JSON null can be filtered with `=`,
`__in` and (Django 6.1) `JSONNull()`. Before, it was stored and read back,
but these lookups did not find it.
