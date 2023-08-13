#Teams

class ScheduleProcessor:
    """Processor for handling schedules."""

    def __init__(self, cache_size: int = CACHE_SIZE):
        self.cache_size = cache_size

    @staticmethod
    def convert_to_date(date_str: str) -> Optional[datetime]:
        try:
            return datetime.strptime(date_str, DATE_FORMAT)
        except ValueError:
            logger.warning(f"Invalid date format: {date_str}")
            return None

    @staticmethod
    def convert_to_string(date_obj: datetime) -> str:
        return date_obj.strftime(DATE_FORMAT)

    def process_schedule(
        self, schedule_data: List[Dict[str, str]]
    ) -> Dict[date, Dict[str, str]]:
        matchups = {}
        for matchup in schedule_data:
            date_value = self.convert_to_date(matchup["date"])
            if date_value:
                matchups[date_value] = matchup
                logger.info(
                    f"Processed matchup for date {date_value}: home - {matchup['home']}, away - {matchup['away']}"
                )
        return matchups

    @lru_cache(maxsize=CACHE_SIZE)
    def group_by_date(
        self, matchups: List[Dict[str, str]]
    ) -> Dict[datetime, List[Dict[str, str]]]:
        grouped = defaultdict(list)
        for matchup in matchups:
            date_value = self.convert_to_date(matchup["date"])
            if date_value:
                grouped[date_value].append(matchup)
        return grouped

    async def fetch_data(self, url: str) -> Dict:
        """Fetch data from a given URL."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"Client error fetching data: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error fetching data: {e}")
            return {}

    async def fetch_schedule_data(
        self, session: aiohttp.ClientSession, date_value: str
    ) -> List[Dict[str, str]]:
        url = f"https://www.teamrankings.com/mlb/schedules/?date={date_value}"
        logger.info("Fetching schedule from: %s", url)
        response = await session.get(url)
        schedule_html = await response.text()
        soup = BeautifulSoup(schedule_html, "html.parser")
        schedule_data = []
        for td in soup.find_all("td", {"class": "text-left nowrap"}):
            for link in td.find_all("a"):
                if "matchup" in link.get("href"):
                    team_names = re.sub(r"#[0-9]*", "", link.string).strip()
                    away_team, home_team = [
                        team.strip() for team in team_names.split(" at ")
                    ]
                    schedule_data.append(
                        {"date": date_value, "home": home_team, "away": away_team}
                    )
        return schedule_data

    async def get_schedule(
        self, backtest_period: int
    ) -> Dict[str, List[Dict[str, str]]]:
        end_date = datetime.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=backtest_period - 1)
        delta = end_date - start_date
        schedule_data = []
        async with aiohttp.ClientSession() as session:
            for i in range(delta.days + 1):
                date_value = (start_date + timedelta(days=i)).strftime(DATE_FORMAT)
                daily_schedule = await self.fetch_schedule_data(session, date_value)
                schedule_data.extend(daily_schedule)
        return {"matchups": schedule_data}


class TeamHelper:
    def __init__(self, config):
        self.config = config

    @lru_cache(maxsize=1000)
    async def group_by_date(self, matchups: List[Dict]) -> Dict[datetime, List[Dict]]:
        grouped = defaultdict(list)
        for matchup in matchups:
            grouped[matchup["date"]].append(matchup)
        return grouped


async def process_data(url: str, categories: List[str]):
    try:
        async with aiohttp.ClientSession() as session:
            extractor = TeamRankingExtractor()
            raw_data = await extractor.fetch_and_extract(session, url, "", categories)
            cleaned_data = clean_data(raw_data)
            logging.info("Processed data successfully")
            return cleaned_data
    except Exception as e:
        logging.error(f"Error processing data: {str(e)}")
        return None


def clean_data(raw_data: List[Matchup]) -> List[Matchup]:
    cleaned_data = []
    for matchup in raw_data:
        if matchup.date and matchup.home and matchup.away:
            cleaned_data.append(matchup)
        else:
            logging.warning("Incomplete matchup data")
    return cleaned_data


def format_results(results: Dict[str, Any]) -> str:
    formatted_results = f"Win Rate: {results['win_rate'] * 100:.2f}%\nProjections: {results['projections']}"
    return formatted_results


def serialize_model(model: Any, filename: str) -> None:
    dump(model, filename)


def get_dynamic_content(url: str) -> str:
    driver = webdriver.Chrome()
    driver.get(url)
    driver.implicitly_wait(10)
    html_content = driver.page_source
    driver.quit()
    return html_content