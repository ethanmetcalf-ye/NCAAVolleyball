# Data Dictionary — `data/processed/volleyball.db`

NCAA Division I women's volleyball, 2025 season (matches 2025-08-22 through 2025-12-21), scoped to the Power 4 conferences (ACC, Big 12, Big Ten, SEC) plus every non-Power4 opponent those teams played. SQLite database: **6 raw tables** loaded from scraped `stats.ncaa.org` box scores by `src/pipeline/build.py` (DDL in `src/pipeline/schema.sql`), and **4 derived views** defined in `src/pipeline/views.sql`.

Views are computed on read (tens of milliseconds at this size), so they can never be out of date relative to the raw tables. Query them exactly like tables.

All `*_id` fields (`team_id`, `contest_id`, `player_id`) are opaque text identifiers assigned by `stats.ncaa.org`. Team IDs are season-scoped: the same program has a different `team_id` each season.

Build and check everything with `python3 -m src.pipeline`. Season-specific inputs (calendar, expected row counts, known source anomalies) live in `data/reference/season_2025.json`; Power 4 membership and curated home venues in `data/reference/power4_teams.json`.

## Stat conventions

| Stat | Definition |
|---|---|
| Hitting % | `(kills − errors) / total_attacks`. Whenever aggregated across matches it is **attempt-weighted** (sum over sum), never an average of per-match percentages. Can be negative. |
| Team blocks | `block_solos + 0.5 × block_assists` (NCAA team convention: two players sharing a block count it once). |
| Individual blocks | `block_solos + block_assists` (NCAA individual convention). |
| Points | `kills + aces + block_solos + 0.5 × block_assists`. Fractional because of the half-point block assist; verified on every row. |
| Per-set rates | Aggregated as `sum(stat) / sum(sets)`, not a mean of per-match rates. |

## Raw tables

### `teams` — 282 rows, one per program

| Column | Type | Description |
|---|---|---|
| `team_id` | TEXT (PK) | NCAA team identifier. |
| `name` | TEXT | Program name, e.g. `"Notre Dame"`. |
| `conference` | TEXT, nullable | `ACC`, `Big 12`, `Big Ten`, `SEC` for the 67 Power 4 teams; **NULL for the 215 non-Power4 opponents** (their real conferences aren't tracked). |
| `is_power4` | INTEGER 0/1 | 1 for the 67 Power 4 programs. |

### `matches` — 1,273 rows, one per contest

| Column | Type | Description |
|---|---|---|
| `contest_id` | TEXT (PK) | NCAA match identifier. |
| `match_date` | TEXT | `YYYY-MM-DD`. |
| `start_time` | TEXT | `HH:MM`, local time as listed by the source (time zone not recorded). |
| `away_team_id` / `home_team_id` | TEXT (FK `teams`) | Home/away **as listed by the source**. At neutral sites the "home" team is only a scorebook designation — use `site_type` / `host_team_id`. |
| `away_sets_won` / `home_sets_won` | INTEGER | Final set score; the winner has 3. |
| `num_sets` | INTEGER | 3, 4, or 5 (610 / 422 / 241 matches). |
| `venue` | TEXT | `"Facility (City, ST)"`, whitespace-normalized. A few are city-only (`"Long Beach, CA"`). |
| `attendance` | INTEGER, nullable | Reported attendance. |
| `site_type` | TEXT, nullable | `home` (946), `neutral` (161), or NULL = unknown (166). See *Site classification* below. |
| `host_team_id` | TEXT (FK `teams`), nullable | The team playing in its own building; set exactly when `site_type = 'home'`. Almost always `home_team_id`; in one match the source lists the host as away. |
| `season_phase` | TEXT | `regular` (1,198), `conference_tournament` (15), or `postseason` (60). |
| `both_power4` | INTEGER 0/1 | Both teams are Power 4 (765 matches). |
| `is_conference_match` | INTEGER 0/1 | Both teams in the same Power 4 conference, **in any phase** (631). Includes the 15 SEC Tournament matches and one same-conference postseason meeting (the NCAA final); filter on `season_phase` too for "conference play". |

**Site classification** (`build.py:classify_site`). Home venues are curated only for Power 4 teams (`power4_teams.json`, most-used home venue plus same-city secondary arenas, reviewed by hand):
- venue is either team's home venue → `home`, hosted by that team;
- venue is a *third* Power 4 team's home venue → `neutral`;
- listed home team is Power 4 but not at one of its venues → `neutral`;
- otherwise (a non-Power4 team listed as home at a venue that isn't tracked) → NULL. These are mostly real home games for mid-major hosts, but invitationals hosted at mid-major gyms can't be told apart.

**Season phase** (`build.py:classify_phase`, driven by `season_2025.json`): `postseason` = on/after 2025-12-04 (NCAA tournament and other December postseason events; the source doesn't distinguish them); `conference_tournament` = same-conference match at the configured tournament venue and dates (2025: SEC Tournament, Enmarket Arena, Savannah, Nov 21–25); everything else `regular`.

### `match_sets` — 4,723 rows, one per set played

| Column | Type | Description |
|---|---|---|
| `contest_id` | TEXT (FK `matches`) | Composite PK with `set_number`. |
| `set_number` | INTEGER | 1–5. |
| `away_points` / `home_points` | INTEGER | Points in that set. Sets 1–4 play to 25, set 5 to 15, win by 2. |

### `team_match_stats` — 2,546 rows, one per team per match

Team box-score line as reported by the source.

| Column | Type | Description |
|---|---|---|
| `contest_id`, `team_id` | TEXT | Composite PK; FKs to `matches` / `teams`. |
| `sets` | INTEGER | Sets played (equals `matches.num_sets`). |
| `kills`, `errors`, `total_attacks` | INTEGER | Attacking; `errors` = hitting errors. |
| `hit_pct` | REAL | Reported hitting % for the match. Observed range −0.114 to 0.618. |
| `assists` | INTEGER | Set assists. |
| `aces`, `service_errors` | INTEGER | Serving. |
| `digs` | INTEGER | Digs. |
| `reception_attempts`, `reception_errors` | INTEGER | Serve receive. **Don't reconcile with player sums** in ~25% of team-matches (see gotchas). |
| `block_solos`, `block_assists`, `block_errors` | INTEGER | Blocking components (see *Stat conventions* for totals). |
| `points` | REAL | See *Stat conventions*. |
| `ball_handling_errors` | INTEGER | Ball-handling errors. |

### `players` — 3,748 rows, one per athlete

| Column | Type | Description |
|---|---|---|
| `player_id` | TEXT (PK) | NCAA player identifier. |
| `name` | TEXT | Most-common spelling across matches (5 players had minor variants). |
| `primary_team_id` | TEXT (FK `teams`) | Team appeared for most (no player appears for more than one team in 2025). |
| `primary_position` | TEXT, nullable | Most-common listed position: `OH` 1,332, `MB` 847, `S` 612, `L/DS` 434, `DS` 192, `L` 176, `OPP` 151, NULL 4. |
| `position_group` | TEXT, nullable | `OH`, `OPP`, `MB`, `S`, or `L/DS` — merges `L`, `DS`, `L/DS`, which the source uses inconsistently for the same back-row role. Use this for filtering. |

### `player_match_stats` — 28,675 rows, one per player per match appearance

Same stat columns as `team_match_stats` (`sets` through `ball_handling_errors`), plus:

| Column | Type | Description |
|---|---|---|
| `contest_id`, `player_id` | TEXT | Composite PK. |
| `team_id` | TEXT (FK `teams`) | Team the player appeared for in this match. |
| `jersey` | TEXT | Jersey number as text. |
| `position` | TEXT, nullable | Listed position this match (raw value, not grouped). |

`hit_pct` is reported as `0`, not NULL, when `total_attacks = 0` (8,455 rows) — never average it directly.

## Derived views

### `team_match_features` — one row per team per match (2,546)

The long-form match table: every team's line with its opponent and context. Feeds the dashboard, the correlation analysis, and any as-of-date modeling features.

| Column | Description |
|---|---|
| `contest_id`, `match_date`, `season_phase`, `is_conference_match`, `site_type` | From `matches`. |
| `team_id`, `opponent_team_id` | This team and the other team. |
| `listed_side` | `home` / `away` as listed by the source. |
| `location` | Where *this team* actually played: `home`, `away`, `neutral`, or NULL when `site_type` is unknown. |
| `won` | 1 if this team won. |
| `sets_played` | Sets in the match. |
| all `team_match_stats` stat columns | This team's raw line. |
| `blocks`, `blocks_per_set` | Team-convention blocks (solos + ½ assists). |
| `error_pct` | `errors / total_attacks`. |
| `kills_per_set`, `digs_per_set`, `aces_per_set`, `assists_per_set` | Match rates. |
| `opponent_kills`, `opponent_errors`, `opponent_total_attacks`, `opponent_hit_pct` | Opponent's attacking line — the raw material for defensive/opponent-adjusted stats. |
| `opponent_points`, `point_differential` | Opponent points; `points − opponent_points`. |

### `team_season_stats` — one row per team (282)

Non-Power4 rows only cover their matches against Power 4 teams — filter on `is_power4 = 1` for real season records.

| Column | Description |
|---|---|
| `team_id`, `name`, `conference`, `is_power4` | From `teams`. |
| `matches_played`, `wins`, `losses`, `win_pct` | Full season, all phases. |
| `conf_wins`, `conf_losses` | Conference matches in the regular season and conference tournament (postseason excluded). |
| `sets_played` | Season total. |
| `hit_pct`, `error_pct` | Attempt-weighted over the season. |
| `opponent_hit_pct` | Attempt-weighted hitting % allowed. |
| `kills_per_set`, `digs_per_set`, `blocks_per_set`, `aces_per_set`, `assists_per_set` | Season sums over season sets; team-convention blocks. |
| `strength_of_schedule` | Mean win % of the **Power 4** opponents faced (weighted by matches played against each), with each opponent's record **excluding its games against this team** (RPI-style). Non-Power4 opponents are left out because their records here only cover games against Power 4 teams (~10% win rate), which previously made SOS mostly a measure of how many non-Power4 teams were scheduled. Still a simple, non-iterative measure — the rating-model work is meant to improve on it. |

### `player_season_stats` — one row per player (3,748)

| Column | Description |
|---|---|
| `player_id`, `name`, `team_id` (primary team), `team_name`, `conference`, `is_power4`, `position` (primary), `position_group` | Identity. |
| `matches_played`, `sets_played` | Season totals. |
| `kills`, `errors`, `total_attacks`, `assists`, `aces`, `service_errors`, `digs`, `reception_attempts`, `reception_errors`, `block_solos`, `block_assists`, `points` | Season sums. |
| `blocks` | Individual-convention blocks (solos + assists). |
| `hit_pct` | Attempt-weighted; NULL with zero attempts. Small-sample values are noisy — the dashboard requires 50+ attempts. |
| `kills_per_set`, `digs_per_set`, `blocks_per_set`, `aces_per_set`, `assists_per_set`, `points_per_set` | Season sums over season sets. |

### `game_spine` — one row per conference match (630)

Wide table for match prediction: both teams' raw lines on one row. Scope: `is_conference_match = 1` and `season_phase IN ('regular', 'conference_tournament')` — i.e. conference play including the SEC Tournament (flagged neutral), excluding the one same-conference postseason meeting. 2025-09-16 through 2025-11-29. ACC 180, Big 12 135, Big Ten 180, SEC 135.

| Column | Description |
|---|---|
| `contest_id`, `match_date`, `start_time`, `venue`, `attendance`, `num_sets`, `season_phase`, `site_type` | From `matches`. 16 rows are `neutral` (15 SEC Tournament + Indiana vs Purdue in Indianapolis). |
| `conference` | Shared conference of both teams. |
| `away_team_id` / `home_team_id`, `away_sets_won` / `home_sets_won` | As listed. Wherever `site_type = 'home'`, the listed home team is the host (validated). |
| `home_won` | 1 if the listed home team won. |
| every `team_match_stats` stat column, suffixed `_home` / `_away` | e.g. `hit_pct_home`, `kills_away`. |

Set-by-set scores are in `match_sets`.

## Known gotchas

- **`home_team_id` is a listing, not a location.** 161 matches are at neutral sites; use `site_type` (match level) or `team_match_features.location` (team level) for home-court questions.
- **`site_type` is NULL for 166 matches** hosted by non-Power4 teams at untracked venues. Treat as unknown, not as home.
- **`is_conference_match` spans all phases.** For conference *play*, also filter `season_phase <> 'postseason'` (or use `game_spine`).
- **Non-Power4 teams have partial seasons** (only games vs Power 4 teams, ~2.4 matches each). Don't compare their records or use them in opponent-strength calculations.
- **Reception stats don't reconcile.** Team `reception_attempts` / `reception_errors` don't equal the sum of player rows in ~25% of team-matches: the source attributes some receptions to an unlisted "TEAM" line inconsistently. All other counting stats reconcile exactly.
- **One source scoring anomaly:** contest `6411406` (Long Beach St. vs UCLA, 2025-09-01) has a set recorded as 24–25. It's allowlisted in `season_2025.json` rather than altered.
- **`player_match_stats.hit_pct` is 0 for zero-attempt rows** — aggregate from kills/errors/attempts instead.
- **`conference` is NULL for non-Power4 teams.**
