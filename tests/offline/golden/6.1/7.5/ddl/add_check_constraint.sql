-- golden: ddl/add_check_constraint
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_rating
-- params: [[], []]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-24
ALTER TABLE "TESTAPP_RATING" ADD CONSTRAINT "TESTAPP_RATING_STARS_LTE_5" CHECK ("STARS" <= 5);
ALTER TABLE "TESTAPP_RATING" DROP CONSTRAINT "TESTAPP_RATING_STARS_LTE_5";
