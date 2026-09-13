-- Raw layer: one row per team-match / per player-match, straight from the scrape.
-- Column names mirror stats.ncaa.org's own labels (see src/scraper/parse.py).

CREATE TABLE teams (
    team_id     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    conference  TEXT,              -- NULL for non-Power4 opponents
    is_power4   INTEGER NOT NULL   -- 0/1
);

CREATE TABLE matches (
    contest_id          TEXT PRIMARY KEY,
    date                TEXT NOT NULL,   -- ISO 8601, e.g. 2025-12-13 19:30:00
    away_team_id         TEXT NOT NULL REFERENCES teams(team_id),
    home_team_id         TEXT NOT NULL REFERENCES teams(team_id),
    away_sets_won        INTEGER NOT NULL,
    home_sets_won        INTEGER NOT NULL,
    num_sets             INTEGER NOT NULL,
    away_set_scores       TEXT NOT NULL,   -- JSON array of ints, e.g. "[22,21,25,17]"
    home_set_scores       TEXT NOT NULL,
    venue                TEXT,
    attendance           INTEGER,
    both_power4          INTEGER NOT NULL,  -- 0/1
    is_conference_match  INTEGER NOT NULL   -- 0/1: both Power4 AND same conference
);

CREATE TABLE team_match_stats (
    contest_id           TEXT NOT NULL REFERENCES matches(contest_id),
    team_id              TEXT NOT NULL REFERENCES teams(team_id),
    sets                 INTEGER,
    kills                INTEGER,
    errors                INTEGER,
    total_attacks         INTEGER,
    hit_pct               REAL,
    assists               INTEGER,
    aces                  INTEGER,
    service_errors         INTEGER,
    digs                  INTEGER,
    reception_attempts     INTEGER,
    reception_errors       INTEGER,
    block_solos            INTEGER,
    block_assists           INTEGER,
    block_errors            INTEGER,
    points                REAL,
    ball_handling_errors    INTEGER,
    PRIMARY KEY (contest_id, team_id)
);

CREATE TABLE players (
    player_id           TEXT PRIMARY KEY,
    name                TEXT NOT NULL,     -- most-common observed name (see build.py)
    primary_team_id      TEXT REFERENCES teams(team_id),
    primary_position     TEXT
);

CREATE TABLE player_match_stats (
    contest_id           TEXT NOT NULL REFERENCES matches(contest_id),
    player_id            TEXT NOT NULL REFERENCES players(player_id),
    team_id              TEXT NOT NULL REFERENCES teams(team_id),
    jersey               TEXT,
    position             TEXT,
    sets                 INTEGER,
    kills                INTEGER,
    errors                INTEGER,
    total_attacks         INTEGER,
    hit_pct               REAL,
    assists               INTEGER,
    aces                  INTEGER,
    service_errors         INTEGER,
    digs                  INTEGER,
    reception_attempts     INTEGER,
    reception_errors       INTEGER,
    block_solos            INTEGER,
    block_assists           INTEGER,
    block_errors            INTEGER,
    points                REAL,
    ball_handling_errors    INTEGER,
    PRIMARY KEY (contest_id, player_id)
);

CREATE INDEX idx_matches_away ON matches(away_team_id);
CREATE INDEX idx_matches_home ON matches(home_team_id);
CREATE INDEX idx_team_match_stats_team ON team_match_stats(team_id);
CREATE INDEX idx_player_match_stats_player ON player_match_stats(player_id);
CREATE INDEX idx_player_match_stats_team ON player_match_stats(team_id);
CREATE INDEX idx_players_team ON players(primary_team_id);
