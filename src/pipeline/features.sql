-- Feature layer, derived from the raw team_match_stats/matches tables.
-- Kept at two granularities deliberately: per-match features (so any
-- rolling window can be computed downstream without baking one in here)
-- and per-season aggregates (for leaderboards/strength-of-schedule).

CREATE TABLE team_match_features (
    contest_id           TEXT NOT NULL REFERENCES matches(contest_id),
    team_id              TEXT NOT NULL REFERENCES teams(team_id),
    opponent_team_id      TEXT NOT NULL REFERENCES teams(team_id),
    date                 TEXT NOT NULL,
    won                  INTEGER NOT NULL,   -- 0/1
    sets_played           INTEGER NOT NULL,
    hit_pct               REAL,
    error_pct             REAL,               -- errors / total_attacks
    kills_per_set          REAL,
    digs_per_set           REAL,
    blocks_per_set         REAL,               -- (block_solos + block_assists) / sets
    aces_per_set            REAL,
    assists_per_set         REAL,
    points                REAL,
    point_differential      REAL,               -- own points - opponent points
    opponent_hit_pct        REAL,               -- opponent's hit_pct this same match
    PRIMARY KEY (contest_id, team_id)
);

CREATE TABLE team_season_stats (
    team_id              TEXT PRIMARY KEY REFERENCES teams(team_id),
    matches_played         INTEGER NOT NULL,
    wins                  INTEGER NOT NULL,
    losses                INTEGER NOT NULL,
    win_pct                REAL NOT NULL,
    avg_hit_pct             REAL,
    avg_error_pct           REAL,
    kills_per_set           REAL,
    digs_per_set            REAL,
    blocks_per_set          REAL,
    aces_per_set             REAL,
    strength_of_schedule      REAL   -- mean opponent win_pct, opponent's record excluding this matchup
);

CREATE INDEX idx_team_match_features_team ON team_match_features(team_id);
CREATE INDEX idx_team_match_features_date ON team_match_features(date);
