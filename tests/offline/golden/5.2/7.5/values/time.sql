-- golden: values/time
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[{"$time": "01:02:03"}]]
-- verified: unverified
SELECT CAST(%s AS TIME) AS "X" FROM "TESTAPP_AUTHOR";
