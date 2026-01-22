CREATE USER parxpress_user WITH PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE parxpress_db TO parxpress_user;
GRANT USAGE ON SCHEMA public TO parxpress_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO parxpress_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO parxpress_user;
