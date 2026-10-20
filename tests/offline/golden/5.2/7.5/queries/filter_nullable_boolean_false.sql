-- golden: queries/filter_nullable_boolean_false
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_switch
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-20
SELECT "TESTAPP_SWITCH"."ID", "TESTAPP_SWITCH"."NAME", "TESTAPP_SWITCH"."FLAG" FROM "TESTAPP_SWITCH" WHERE "TESTAPP_SWITCH"."FLAG" = FALSE;
