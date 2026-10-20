-- golden: values/foreign_key_to_uuid
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["12345678123456781234567812345678"]]
-- verified: unverified
SELECT CAST(%s AS CHAR(32)) AS "X" FROM "TESTAPP_AUTHOR";
