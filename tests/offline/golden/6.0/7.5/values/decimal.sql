-- golden: values/decimal
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[{"$decimal": "12.345"}]]
-- verified: unverified
SELECT CAST(%s AS DECIMAL(5, 3)) AS "X" FROM "TESTAPP_AUTHOR";
