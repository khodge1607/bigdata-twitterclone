CREATE TABLE users_deduped AS
SELECT DISTINCT ON (id_users) *
FROM users
ORDER BY id_users;

ALTER TABLE users RENAME TO users_old;
ALTER TABLE users_deduped RENAME TO users;
DROP TABLE users_old CASCADE;
