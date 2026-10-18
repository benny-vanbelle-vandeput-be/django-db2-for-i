Negating a nullable boolean (`filter(~F("flag"))`, `annotate(x=~F("flag"))`)
gave wrong results for NULL: Db2 for i's `NOT <boolean value>` is TRUE when
the value is NULL, also in WHERE. Such negations are written as `CASE
<value> WHEN TRUE THEN FALSE WHEN FALSE THEN TRUE END` everywhere, so NULL
stays NULL and NULL rows do not match.
