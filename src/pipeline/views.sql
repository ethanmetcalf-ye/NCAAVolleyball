-- Derived layer: views over the raw tables in schema.sql. Computed on read
-- (tens of milliseconds at this data size), so they can't go stale.
--
-- Stat conventions (NCAA):
--   hitting %          (kills - errors) / total_attacks, attempt-weighted
--                      whenever aggregated across matches
--   team blocks        block_solos + 0.5 * block_assists
--   individual blocks  block_solos + block_assists
--   per-set rates      aggregated as sum(stat) / sum(sets), not a mean of
--                      per-match rates

-- One row per team per match (2 rows per match), with opponent and context.
CREATE VIEW team_match_features AS
SELECT
    m.contest_id,
    m.match_date,
    m.season_phase,
    m.is_conference_match,
    m.site_type,
    t.team_id,
    o.team_id AS opponent_team_id,
    CASE WHEN t.team_id = m.home_team_id THEN 'home' ELSE 'away' END AS listed_side,
    -- Where this team actually played: NULL when site_type is unknown.
    CASE
        WHEN m.site_type = 'neutral' THEN 'neutral'
        WHEN m.host_team_id = t.team_id THEN 'home'
        WHEN m.site_type = 'home' THEN 'away'
    END AS location,
    CASE WHEN t.team_id = m.home_team_id
         THEN m.home_sets_won > m.away_sets_won
         ELSE m.away_sets_won > m.home_sets_won END AS won,
    t.sets AS sets_played,
    t.kills, t.errors, t.total_attacks, t.hit_pct, t.assists, t.aces, t.service_errors,
    t.digs, t.reception_attempts, t.reception_errors, t.block_solos, t.block_assists,
    t.block_errors, t.ball_handling_errors, t.points,
    t.block_solos + 0.5 * t.block_assists AS blocks,
    CAST(t.errors AS REAL) / NULLIF(t.total_attacks, 0) AS error_pct,
    CAST(t.kills AS REAL) / t.sets AS kills_per_set,
    CAST(t.digs AS REAL) / t.sets AS digs_per_set,
    (t.block_solos + 0.5 * t.block_assists) / t.sets AS blocks_per_set,
    CAST(t.aces AS REAL) / t.sets AS aces_per_set,
    CAST(t.assists AS REAL) / t.sets AS assists_per_set,
    o.kills AS opponent_kills,
    o.errors AS opponent_errors,
    o.total_attacks AS opponent_total_attacks,
    o.hit_pct AS opponent_hit_pct,
    o.points AS opponent_points,
    t.points - o.points AS point_differential
FROM matches m
JOIN team_match_stats t ON t.contest_id = m.contest_id
JOIN team_match_stats o ON o.contest_id = m.contest_id AND o.team_id <> t.team_id;

-- One row per team (all 282: Power4 teams have full seasons, non-Power4
-- teams only their matches against Power4 opponents -- filter on is_power4).
CREATE VIEW team_season_stats AS
WITH totals AS (
    SELECT
        team_id,
        COUNT(*) AS matches_played,
        SUM(won) AS wins,
        SUM(CASE WHEN is_conference_match = 1 AND season_phase <> 'postseason' THEN won ELSE 0 END) AS conf_wins,
        SUM(CASE WHEN is_conference_match = 1 AND season_phase <> 'postseason' THEN 1 - won ELSE 0 END) AS conf_losses,
        SUM(sets_played) AS sets_played,
        SUM(kills) AS kills, SUM(errors) AS errors, SUM(total_attacks) AS total_attacks,
        SUM(digs) AS digs, SUM(blocks) AS blocks, SUM(aces) AS aces, SUM(assists) AS assists,
        SUM(opponent_kills) AS opponent_kills, SUM(opponent_errors) AS opponent_errors,
        SUM(opponent_total_attacks) AS opponent_total_attacks
    FROM team_match_features
    GROUP BY team_id
),
head_to_head AS (
    SELECT team_id, opponent_team_id, COUNT(*) AS games, SUM(won) AS wins
    FROM team_match_features
    GROUP BY team_id, opponent_team_id
),
-- Mean win % of Power4 opponents faced (once per match), each opponent's
-- record excluding its games against this team (RPI-style). Non-Power4
-- opponents are left out: their records here only cover games against
-- Power4 teams, which would make any schedule with them look weak.
schedule AS (
    SELECT
        f.team_id,
        AVG(CAST(ot.wins - h2h.wins AS REAL) / (ot.matches_played - h2h.games)) AS strength_of_schedule
    FROM team_match_features f
    JOIN teams opp ON opp.team_id = f.opponent_team_id AND opp.is_power4 = 1
    JOIN totals ot ON ot.team_id = f.opponent_team_id
    JOIN head_to_head h2h ON h2h.team_id = f.opponent_team_id AND h2h.opponent_team_id = f.team_id
    GROUP BY f.team_id
)
SELECT
    s.team_id,
    te.name,
    te.conference,
    te.is_power4,
    s.matches_played,
    s.wins,
    s.matches_played - s.wins AS losses,
    CAST(s.wins AS REAL) / s.matches_played AS win_pct,
    s.conf_wins,
    s.conf_losses,
    s.sets_played,
    CAST(s.kills - s.errors AS REAL) / s.total_attacks AS hit_pct,
    CAST(s.errors AS REAL) / s.total_attacks AS error_pct,
    CAST(s.opponent_kills - s.opponent_errors AS REAL) / s.opponent_total_attacks AS opponent_hit_pct,
    CAST(s.kills AS REAL) / s.sets_played AS kills_per_set,
    CAST(s.digs AS REAL) / s.sets_played AS digs_per_set,
    s.blocks / s.sets_played AS blocks_per_set,
    CAST(s.aces AS REAL) / s.sets_played AS aces_per_set,
    CAST(s.assists AS REAL) / s.sets_played AS assists_per_set,
    sch.strength_of_schedule
FROM totals s
JOIN teams te ON te.team_id = s.team_id
LEFT JOIN schedule sch ON sch.team_id = s.team_id;

-- One row per player, season totals and rates.
CREATE VIEW player_season_stats AS
SELECT
    p.player_id,
    p.name,
    p.primary_team_id AS team_id,
    te.name AS team_name,
    te.conference,
    te.is_power4,
    p.primary_position AS position,
    p.position_group,
    COUNT(*) AS matches_played,
    SUM(s.sets) AS sets_played,
    SUM(s.kills) AS kills,
    SUM(s.errors) AS errors,
    SUM(s.total_attacks) AS total_attacks,
    CAST(SUM(s.kills - s.errors) AS REAL) / NULLIF(SUM(s.total_attacks), 0) AS hit_pct,
    SUM(s.assists) AS assists,
    SUM(s.aces) AS aces,
    SUM(s.service_errors) AS service_errors,
    SUM(s.digs) AS digs,
    SUM(s.reception_attempts) AS reception_attempts,
    SUM(s.reception_errors) AS reception_errors,
    SUM(s.block_solos) AS block_solos,
    SUM(s.block_assists) AS block_assists,
    SUM(s.block_solos + s.block_assists) AS blocks,
    SUM(s.points) AS points,
    CAST(SUM(s.kills) AS REAL) / SUM(s.sets) AS kills_per_set,
    CAST(SUM(s.digs) AS REAL) / SUM(s.sets) AS digs_per_set,
    CAST(SUM(s.block_solos + s.block_assists) AS REAL) / SUM(s.sets) AS blocks_per_set,
    CAST(SUM(s.aces) AS REAL) / SUM(s.sets) AS aces_per_set,
    CAST(SUM(s.assists) AS REAL) / SUM(s.sets) AS assists_per_set,
    SUM(s.points) / SUM(s.sets) AS points_per_set
FROM player_match_stats s
JOIN players p ON p.player_id = s.player_id
JOIN teams te ON te.team_id = p.primary_team_id
GROUP BY p.player_id;

-- One row per conference match (regular season + conference tournament;
-- same-conference postseason meetings are excluded), both teams' stat lines
-- side by side for match-prediction modeling. home/away follow the source
-- listing; site_type says whether the home side actually had home court.
CREATE VIEW game_spine AS
SELECT
    m.contest_id,
    m.match_date,
    m.start_time,
    ht.conference,
    m.season_phase,
    m.site_type,
    m.away_team_id,
    m.home_team_id,
    m.away_sets_won,
    m.home_sets_won,
    m.num_sets,
    m.venue,
    m.attendance,
    m.home_sets_won > m.away_sets_won AS home_won,
    h.sets AS sets_home,                                 a.sets AS sets_away,
    h.kills AS kills_home,                               a.kills AS kills_away,
    h.errors AS errors_home,                             a.errors AS errors_away,
    h.total_attacks AS total_attacks_home,               a.total_attacks AS total_attacks_away,
    h.hit_pct AS hit_pct_home,                           a.hit_pct AS hit_pct_away,
    h.assists AS assists_home,                           a.assists AS assists_away,
    h.aces AS aces_home,                                 a.aces AS aces_away,
    h.service_errors AS service_errors_home,             a.service_errors AS service_errors_away,
    h.digs AS digs_home,                                 a.digs AS digs_away,
    h.reception_attempts AS reception_attempts_home,     a.reception_attempts AS reception_attempts_away,
    h.reception_errors AS reception_errors_home,         a.reception_errors AS reception_errors_away,
    h.block_solos AS block_solos_home,                   a.block_solos AS block_solos_away,
    h.block_assists AS block_assists_home,               a.block_assists AS block_assists_away,
    h.block_errors AS block_errors_home,                 a.block_errors AS block_errors_away,
    h.points AS points_home,                             a.points AS points_away,
    h.ball_handling_errors AS ball_handling_errors_home, a.ball_handling_errors AS ball_handling_errors_away
FROM matches m
JOIN teams ht ON ht.team_id = m.home_team_id
JOIN team_match_stats h ON h.contest_id = m.contest_id AND h.team_id = m.home_team_id
JOIN team_match_stats a ON a.contest_id = m.contest_id AND a.team_id = m.away_team_id
WHERE m.is_conference_match = 1
  AND m.season_phase IN ('regular', 'conference_tournament');
