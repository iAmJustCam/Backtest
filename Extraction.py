#extraction
class TeamRankingExtractor:
    def __init__(self, max_cache_size: int = 100, concurrent_limit: int = 10):
        self.max_cache_size = max_cache_size
        self.ranks_cache = LRUCache(max_cache_size)
        self._semaphore = asyncio.Semaphore(concurrent_limit)

    async def _make_request(
        self, session: aiohttp.ClientSession, url: str, **kwargs
    ) -> Optional[str]:
        """Make an HTTP request and return the content."""
        async with session.get(url, **kwargs) as response:
            return await response.text()

    async def _handle_errors(self, content: str, url: str) -> Optional[str]:
        """Handle errors and return the content if valid."""
        if not content or "no data available" in content.lower():
            logging.error(f"No relevant data found in {url}")
            return None
        return content

    async def _fetch(
        self, session: aiohttp.ClientSession, url: str, **kwargs
    ) -> Optional[str]:
        """Fetch content from a URL, handling errors and concurrency."""
        async with self._semaphore:
            logging.debug(f"Starting fetch for URL: {url}")
            try:
                content = await self._make_request(session, url, **kwargs)
                return await self._handle_errors(content, url)
            except (aiohttp.ClientError, asyncio.TimeoutError, Exception) as e:
                logging.error(f"Error fetching data from {url}, due to {str(e)}")
                return None

    def _parse_html(self, html_content: str, categories: List[str]) -> Dict[str, int]:
        soup = BeautifulSoup(html_content, "html.parser")
        data = {}
        for config_category in categories:
            try:
                category_element = soup.find("td", string=config_category)
                if category_element:
                    logging.debug(f"Found category_element for {config_category}")
                    rank_element = category_element.find_next_sibling("td")
                    if rank_element:
                        logging.debug(f"Found rank_element for {config_category}")
                        rank = re.search(r"\(#(\d+)\)", rank_element.text)
                        if rank:
                            data[config_category] = int(rank.group(1))
                        else:
                            logging.warning(f"No rank found for {config_category}")
                    else:
                        logging.warning(f"No rank element found for {config_category}")
                else:
                    logging.warning(f"No category element found for {config_category}")
            except Exception as e:
                logging.error(f"Error processing category {config_category}: {str(e)}")
        return data

    def extract(self, html_content: str, categories: List[str]) -> Dict[str, int]:
        logging.debug(f"Raw HTML content: {html_content[:100]}...")

        cache_key = hash(html_content)
        cached_data = self.ranks_cache.get(cache_key)
        if cached_data:
            logging.debug("Cache hit for key: %s", cache_key)
            return cached_data

        data = self._parse_html(html_content, categories)
        self.ranks_cache.put(cache_key, data)
        return data

    def validate_ranks(
        self, ranks: Dict[str, int], expected_keys: List[str]
    ) -> Dict[str, int]:
        ranks_lower = {
            key.lower().replace("%", "").strip(): value for key, value in ranks.items()
        }
        logging.debug("Before validation: %s", ranks)
        missing_keys = [key for key in expected_keys if key not in ranks_lower]
        if missing_keys:
            logging.warning(f"Missing keys in ranks: {', '.join(missing_keys)}")
            for key in missing_keys:
                ranks_lower[key] = -1
        else:
            logging.info("All ranks successfully scraped.")
            logging.debug("Ranks content: %s", ranks_lower)
        logging.debug("After validation: %s", ranks_lower)
        return ranks_lower

    async def fetch_and_extract(
        self,
        session: aiohttp.ClientSession,
        url: str,
        team_name: str,
        categories: List[str],
    ) -> Dict[str, int]:
        logging.info(
            f"Starting fetch and extraction for team {team_name} and URL {url}"
        )
        html_content = await self._fetch(session, url)

        if not html_content:
            logging.error(f"No HTML content fetched for {url}")
            return {}

        extracted_ranks = self.extract(html_content, categories)
        logging.info(f"Extracted ranks for {team_name}: {extracted_ranks}")

        return extracted_ranks

    def clear_cache(self) -> None:
        self.ranks_cache.cache.clear()
        logging.info("Cache cleared")
