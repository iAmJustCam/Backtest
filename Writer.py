#Writer

class DataWriterError(Exception):
    """Custom exception for DataWriter errors."""


class DataWriter:
    supported_extensions = {".csv", ".tsv", ".txt", ".json", ".xlsx"}

    def __init__(
        self,
        compression: Optional[str] = None,
        dialect: Optional[str] = None,
        validate_headers: bool = True,
    ):
        self.compression = compression
        self.dialect = dialect
        self.validate_headers = validate_headers

    @classmethod
    def infer_writer(cls, filename: str) -> "DataWriter":
        ext = Path(filename).suffix
        if ext == ".json":
            return JSONDataWriter()
        elif ext == ".xlsx":
            return ExcelDataWriter()
        else:
            return CSVDataWriter()

    def _validate_data(self, data: List[Dict[str, Any]]) -> None:
        if not data:
            raise ValueError("Data is empty.")
        if self.validate_headers:
            headers = list(data[0].keys())
            for item in data:
                if list(item.keys()) != headers:
                    raise ValueError("Inconsistent data headers.")

    def write_data(self, file: IO, data: List[Dict[str, Any]]) -> None:
        self._validate_data(data)
        self._write_data(file, data)

    def _write_data(self, file: IO, data: List[Dict[str, Any]]) -> None:
        raise NotImplementedError


class CSVDataWriter(DataWriter):
    def _write_data(self, file: IO, data: List[Dict[str, Any]]) -> None:
        df = pd.DataFrame(data)
        df.to_csv(file, index=False, dialect=self.dialect, compression=self.compression)


class JSONDataWriter(DataWriter):
    def _write_data(self, file: IO, data: List[Dict[str, Any]]) -> None:
        df = pd.DataFrame(data)
        df.to_json(file)


class ExcelDataWriter(DataWriter):
    def _write_data(self, file: IO, data: List[Dict[str, Any]]) -> None:
        df = pd.DataFrame(data)
        df.to_excel(file, index=False)


async def fetch_and_extract_team_ranks(session, config, schedule, categories):
    team_ranking_extractor = TeamRankingExtractor()

    semaphore = asyncio.Semaphore(10)
    tasks = [
        asyncio.create_task(
            team_ranking_extractor.fetch_and_extract(
                session,
                config.get_team_url(matchup[team]) + "/stats",
                matchup[team],
                categories,
                semaphore,
            )
        )
        for matchup in schedule["matchups"]
        for team in ["home", "away"]
    ]

    return await asyncio.gather(*tasks)