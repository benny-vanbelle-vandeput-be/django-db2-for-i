-- golden: queries/filter_boolean_annotation_false
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_switch
-- params: [[]]
-- verified: unverified
SELECT "TESTAPP_SWITCH"."ID", "TESTAPP_SWITCH"."NAME", "TESTAPP_SWITCH"."FLAG", CASE "TESTAPP_SWITCH"."FLAG" WHEN TRUE THEN FALSE WHEN FALSE THEN TRUE END AS "NEG" FROM "TESTAPP_SWITCH" WHERE "TESTAPP_SWITCH"."FLAG" = TRUE;
