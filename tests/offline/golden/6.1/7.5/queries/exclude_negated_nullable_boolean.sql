-- golden: queries/exclude_negated_nullable_boolean
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_switch
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19
SELECT "TESTAPP_SWITCH"."ID", "TESTAPP_SWITCH"."NAME", "TESTAPP_SWITCH"."FLAG" FROM "TESTAPP_SWITCH" WHERE NOT ("TESTAPP_SWITCH"."FLAG" = FALSE);
