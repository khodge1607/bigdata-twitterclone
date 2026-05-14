CREATE TABLE tweets_deduped AS
SELECT DISTINCT ON (id_users, created_at, text) *
FROM tweets
ORDER BY id_users, created_at, text;

ALTER TABLE tweets RENAME TO tweets_old;
ALTER TABLE tweets_deduped RENAME TO tweets;
DROP TABLE tweets_old;
