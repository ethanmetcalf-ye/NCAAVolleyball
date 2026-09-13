-- Raw layer: one row per team / match / set / team-match / player-match,
-- loaded from the scraped box scores by build.py. Stat column names mirror
-- stats.ncaa.org's own labels. Everything derived from these tables is a
-- view (views.sql), so it can never drift out of sync with the raw data.

CREATE TABLE teams (
    team_id     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    conference  TEXT,                  -- NULL for non-Power4 opponents
    is_power4   INTEGER NOT NULL CHECK (is_power4 IN (0, 1))
);

CREATE TABLE matches (
    contest_id           TEXT PRIMARY KEY,
    match_date           TEXT NOT NULL,   -- YYYY-MM-DD
    start_time           TEXT NOT NULL,   -- HH:MM, local time as listed by the source
    away_team_id         TEXT NOT NULL REFERENCES teams(team_id),
    home_team_id         TEXT NOT NULL REFERENCES teams(team_id),  -- as listed by the source; see site_type
    away_sets_won        INTEGER NOT NULL,
    home_sets_won        INTEGER NOT NULL,
    num_sets             INTEGER NOT NULL CHECK (num_sets BETWEEN 3 AND 5),
    venue                TEXT NOT NULL,   -- "Facility (City, ST)", whitespace-normalized
    attendance           INTEGER,
    -- 'home': played at host_team_id's home venue. 'neutral': at neither
    -- team's home venue. NULL: can't tell (non-Power4 host whose home
    -- venues aren't tracked). See build.py:classify_site().
    site_type            TEXT CHECK (site_type IN ('home', 'neutral')),
    host_team_id         TEXT REFERENCES teams(team_id),  -- set iff site_type = 'home'
    season_phase         TEXT NOT NULL CHECK (season_phase IN ('regular', 'conference_tournament', 'postseason')),
    both_power4          INTEGER NOT NULL CHECK (both_power4 IN (0, 1)),
    is_conference_match  INTEGER NOT NULL CHECK (is_conference_match IN (0, 1)),  -- same Power4 conference, any phase
    CHECK ((site_type = 'home') = (host_team_id IS NOT NULL))
);

CREATE TABLE match_sets (
    contest_id    TEXT NOT NULL REFERENCES matches(contest_id),
    set_number    INTEGER NOT NULL CHECK (set_number BETWEEN 1 AND 5),
    away_points   INTEGER NOT NULL,
    home_points   INTEGER NOT NULL,
    PRIMARY KEY (contest_id, set_number)
);

CREATE TABLE team_match_stats (
    contest_id            TEXT NOT NULL REFERENCES matches(contest_id),
    team_id               TEXT NOT NULL REFERENCES teams(team_id),
    sets                  INTEGER,
    kills                 INTEGER,
    errors                INTEGER,
    total_attacks         INTEGER,
    hit_pct               REAL,
    assists               INTEGER,
    aces                  INTEGER,
    service_errors        INTEGER,
    digs                  INTEGER,
    reception_attempts    INTEGER,
    reception_errors      INTEGER,
    block_solos           INTEGER,
    block_assists         INTEGER,
    block_errors          INTEGER,
    points                REAL,          -- kills + aces + block_solos + 0.5 * block_assists
    ball_handling_errors  INTEGER,
    PRIMARY KEY (contest_id, team_id)
);

CREATE TABLE players (
    player_id         TEXT PRIMARY KEY,
    name              TEXT NOT NULL,     -- most-common observed spelling
    primary_team_id   TEXT REFERENCES teams(team_id),
    primary_position  TEXT,              -- most-common observed position
    position_group    TEXT CHECK (position_group IN ('OH', 'OPP', 'MB', 'S', 'L/DS'))
);

CREATE TABLE player_match_stats (
    contest_id            TEXT NOT NULL REFERENCES matches(contest_id),
    player_id             TEXT NOT NULL REFERENCES players(player_id),
    team_id               TEXT NOT NULL REFERENCES teams(team_id),
    jersey                TEXT,
    position              TEXT,
    sets                  INTEGER,
    kills                 INTEGER,
    errors                INTEGER,
    total_attacks         INTEGER,
    hit_pct               REAL,          -- 0 (not NULL) when total_attacks = 0, as reported
    assists               INTEGER,
    aces                  INTEGER,
    service_errors        INTEGER,
    digs                  INTEGER,
    reception_attempts    INTEGER,
    reception_errors      INTEGER,
    block_solos           INTEGER,
    block_assists         INTEGER,
    block_errors          INTEGER,
    points                REAL,
    ball_handling_errors  INTEGER,
    PRIMARY KEY (contest_id, player_id)
);

CREATE INDEX idx_matches_away ON matches(away_team_id);
CREATE INDEX idx_matches_home ON matches(home_team_id);
CREATE INDEX idx_matches_date ON matches(match_date);
CREATE INDEX idx_team_match_stats_team ON team_match_stats(team_id);
CREATE INDEX idx_player_match_stats_player ON player_match_stats(player_id);
CREATE INDEX idx_player_match_stats_team ON player_match_stats(team_id);
CREATE INDEX idx_players_team ON players(primary_team_id);
