-- golden: values/decimal_wider_than_field
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[{"$decimal": "123456.789"}]]
-- verified: unverified
SELECT CAST(%s AS DECIMAL(9, 3)) AS "X" FROM "TESTAPP_AUTHOR";
