CREATE INDEX idx_tweets_text_rum ON tweets USING RUM(to_tsvector('english', text));
