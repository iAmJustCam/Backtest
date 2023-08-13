#Projection
class PointsProjector:
    BASE_URL = "https://www.teamrankings.com/mlb/team/"

    def __init__(self, config_manager: Any, session: aiohttp.ClientSession):
        self.config_manager = config_manager
        self.session = session
        self.rankings_cache = {}  # A simple dictionary to cache team rankings.

    @staticmethod
    def transform_ranks(ranks_dictionary: Dict[str, Any]) -> Dict[str, Any]:
        transformed_ranks = {
            "slugging"
            if key == "Slugging %"
            else "on base"
            if key == "On Base %"
            else key: value  # Use original key
            for key, value in ranks_dictionary.items()
        }
        logging.debug("Original ranks: %s", ranks_dictionary)
        logging.debug("Transformed ranks: %s", transformed_ranks)
        return transformed_ranks

    async def calculate_score(
        self,
        home_ranks: Dict[str, Any],
        away_ranks: Dict[str, Any],
        scoring_criteria: Dict[str, float],  # Change int to float for decimal values
    ) -> int:
        logging.info("Starting to calculate score with PointsProjector")
        logging.info("Received home_ranks: %s, away_ranks: %s", home_ranks, away_ranks)

        score = 0

        for category, weight in scoring_criteria.items():
            home_category_rank = home_ranks.get(category)
            away_category_rank = away_ranks.get(category)

            # Check if both ranks are present and valid
            if home_category_rank is not None and away_category_rank is not None:
                difference = abs(home_category_rank - away_category_rank)
                logging.debug(f"Difference in ranks for {category}: {difference}")

                # Check if the difference exceeds the scoring criteria
                if difference > weight:
                    if away_category_rank < home_category_rank:
                        score -= 1  # award point to away team
                        logging.debug(
                            f"Awarded a point to the away team for {category}"
                        )
                    elif home_category_rank < away_category_rank:
                        score += 1  # award point to home team
                        logging.debug(
                            f"Awarded a point to the home team for {category}"
                        )

        logging.info("Score calculated: %s", score)
        return score


    async def calculate_projections(
        self,
        matchups: List[Dict[str, str]],
        scoring_criteria: Dict[str, float],
    ) -> List[Dict[str, Union[str, int]]]:
        
        logging.info("Starting to calculate projections")
        
        if not (
            isinstance(matchups, list)
            and isinstance(scoring_criteria, dict)
        ):
            logging.error("Invalid data types provided.")
            return []

        projections = []
        team_ranking_extractor = TeamRankingExtractor()

        for matchup in matchups:
            home_team = matchup["home"]
            away_team = matchup["away"]

            # Logic for Home Team
            if home_team not in self.rankings_cache:
                home_ranks = await team_ranking_extractor.fetch_and_extract(
                    self.session, 
                    f"{self.BASE_URL}{home_team.lower().replace(' ', '-')}-stats", 
                    home_team, 
                    self.config_manager.get_scoring_categories()
                )
                sel