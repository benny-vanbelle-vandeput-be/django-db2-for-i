-- golden: queries/exclude_negated_nullable_boolean
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_switch
-- params: [[]]
-- verified: unverified
SELECT "TESTAPP_SWITCH"."ID", "TESTAPP_SWITCH"."NAME", "TESTAPP_SWITCH"."FLAG" FROM "TESTAPP_SWITCH" WHERE NOT ("TESTAPP_SWITCH"."FLAG" = FALSE);
