-- golden: values/ip_address
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["2001::1"]]
-- verified: unverified
SELECT CAST(%s AS VARCHAR(39)) AS "X" FROM "TESTAPP_AUTHOR";
