-- Player-level season aggregates, derived from player_match_stats.
-- hit_pct is weighted (sum(kills-errors)/sum(total_attacks)), not an
-- average of per-match hit_pcts, since matches vary a lot in attack volume.

CREATE TABLE player_season_stats (
    player_id            TEXT PRIMARY KEY REFERENCES players(player_id),
    matches_played         INTEGER NOT NULL,
    sets_played            INTEGER NOT NULL,
    kills                 INTEGER NOT NULL,
    errors                 INTEGER NOT NULL,
    total_attacks           INTEGER NOT NULL,
    hit_pct                REAL,
    assists                INTEGER NOT NULL,
    aces                  INTEGER NOT NULL,
    service_errors           INTEGER NOT NULL,
    digs                  INTEGER NOT NULL,
    block_solos             INTEGER NOT NULL,
    block_assists            INTEGER NOT NULL,
    points                 REAL NOT NULL,
    kills_per_set            REAL,
    digs_per_set             REAL,
    blocks_per_set           REAL,
    aces_per_set              REAL,
    assists_per_set           REAL,
    points_per_set            REAL
);

CREATE INDEX idx_player_season_stats_kills ON player_season_stats(kills);
