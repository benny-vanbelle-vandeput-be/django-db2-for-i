-- golden: values/decimal_field
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[{"$decimal": "1.5"}]]
-- verified: unverified
SELECT CAST(%s AS DECIMAL(10, 2)) AS "X" FROM "TESTAPP_AUTHOR";
