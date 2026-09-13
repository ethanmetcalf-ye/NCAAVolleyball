import pandas as pd

class RatingModel:
    def fit(self, training_games: pd.DataFrame) -> None:
        self.weights = [0.6, 0.4]  # Example weights for home and away teams

    def predict(self, test_games: pd.DataFrame) -> float:
        home_team_win_prob = self.weights[0]
        return home_team_win_prob

    def ratings(self) -> pd.Series:
        """team_id -> rating. Populates ratings_history."""