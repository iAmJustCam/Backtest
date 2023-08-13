#Constants/Config/Cache
from bs4 import BeautifulSoup
from pathlib import Path
from selenium import webdriver
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from sklearn.model_selection import train_test_split
from datetime import date, datetime, timedelta
from collections import defaultdict, namedtuple, OrderedDict
from collections.abc import MutableMapping
import aiohttp
from aiohttp import ClientTimeout
import asyncio
from functools import lru_cache
from joblib import load
import configparser
from typing import Dict, List, Tuple, Union, Any, Optional, IO
from urllib.parse import quote_plus
import hashlib
import argparse
import joblib
import re
import os
import pandas as pd
import logging


COLUMNS = [
    "Matchup",
    "Category",
    "Away Rank",
    "Home Rank",
    "Point Awarded To",
    "Away Point Total",
    "Home Point Total",
    "Projected Winner",
]


# Namedtuple for Matchup
Matchup = namedtuple("Matchup", ["home", "away", "date"])

RankDict = Dict[str, int]
Projection = Dict[str, Union[str, int]]

# Environment Configuration
DATE_FORMAT = os.getenv("DATE_FORMAT", default="%Y-%m-%d")
CACHE_SIZE = int(os.getenv("CACHE_SIZE", default=100))
LOG_FILENAME = os.getenv("LOG_FILENAME", default="app.log")

LOG_FILENAME = "log.txt"

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s]: %(message)s',
    handlers=[logging.FileHandler(LOG_FILENAME, "a", "utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class Config:
    """
    Configuration handler class for mapping and validating settings.
    """
    TEAM_BASE_URL = "https://www.teamrankings.com/mlb/team/"

    def __init__(self, config_file: str):
        script_dir = os.path.dirname(__file__)
        config_file_path = os.path.join(script_dir, config_file)
        self.config = configparser.ConfigParser()
        self.config.read(config_file_path)
        self.team_name_mapping = self.map_team_names()
        self.validate_config()

    def map_team_names(self) -> Dict[str, str]:
        """Maps team names to their URL-friendly names."""
        return {
            team_name.strip().lower(): url_friendly_name.strip().lower()
            for team_name, url_friendly_name in self.config["team_name_mapping"].items()
        }

    def get_team_url(self, team_name: str) -> str:
        """
        Generate the team's URL using the given team name.

        Parameters:
            - team_name (str): The name of the team.

        Returns:
            - str: The generated URL.
        """
        normalized_name = team_name.strip().lower()
        slug = self.team_name_mapping.get(
            normalized_name, normalized_name.replace(" ", "-")
        )
        encoded_slug = quote_plus(slug)
        url = f"{self.TEAM_BASE_URL}{encoded_slug}"
        logging.info(f"Generated URL for {team_name}: {url}")
        return url

    def get_categories(self) -> List[str]:
        return [
            category.strip()
            for category in self.config["categories"]["categories"].split(",")
        ]

    def scoring_criteria(self) -> Dict[str, int]:
        return {
            key.strip(): float(value.strip())
            for key, value in self.config.items("scoring_criteria")
        }

    def get_output_format(self) -> str:
        """
        Retrieve the preferred output format.

        Returns:
            - str: The format type, e.g., 'csv', 'xlsx'.
        """
        return self.config.get("Output", "format", fallback="csv")

    def validate_config(self) -> None:
        required_config = {
            "scoring_criteria": [
                "Batting Avg",
                "/Game",
                "Home Runs/9",
                "On Base",
                "Slugging",
                "Earned Run Average",
                "WHIP",
                "Hits/9",
            ],
            "categories": ["categories"],
            "logging": ["level"],
            "team_name_mapping": [],
            "CSV": ["fields"],
        }

        for section, options in required_config.items():
            for option in options:
                if not self.config.get(section, option):
                    raise ValueError(
                        f"{option} must be set in {section} section of the config file."
                    )


# LRU Cache
class LRUCache:
    def __init__(self, capacity: int):
        self.cache = OrderedDict()
        self.capacity = capacity

    def get(self, key: str) -> Any:
        return self.cache.get(key, None)

    def put(self, key: str, value: Any) -> None:
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

# CacheManager definition
class CacheManager:
    def __init__(self, cache: 'Cache'):
        self.cache = cache

    def get_cache(self, key: str) -> Optional[str]:
        return self.cache.backend.get(key)

    async def set_cache(self, key: str, value: str) -> None:
        self.cache.backend.put(key, value)

    def invalidate_cache(self, key: str) -> None:
        if self.cache.backend.get(key):
            del self.cache.backend.cache[key]

# Cache definition
class Cache:
    def __init__(self, backend):
        self.backend = backend
        self.manager = CacheManager(self)

    def _get_cache_key(self, request: str) -> str:
        m = hashlib.md5()
        m.update(request.encode())
        return m.hexdigest()

    async def get(self, key: str) -> Optional[str]:
        return self.manager.get_cache(key)

    async def set(self, key: str, value: str) -> None:
        await self.manager.set_cache(key, value)

    def invalidate(self, key: str) -> None:
        self.manager.invalidate_cache(key)


def validate_data(
    data: List[Dict[str, Union[str, datetime, int]]]
) -> List[Dict[str, Union[str, datetime, int]]]:
    validated = []
    for row in data:
        if not set(row.keys()) >= {
            "team1",
            "team2",
            "date",
            "team1_score",
            "team2_score",
        }:
            raise ValueError(f"Missing keys in data row: {row}")
        if not isinstance(row["date"], datetime):
            raise TypeError(f"Invalid type for date in data row: {row}")
        validated.append(row)
    return validated


def extract_features_and_labels(
    data: List[Dict[str, Union[str, datetime, int]]], features: List[str]
) -> (List[Dict[str, Union[str, datetime, int]]], List[int]):
    X = [{feature: row[feature] for feature in features} for row in data]
    y = [row["outcome"] for row in data]
    return X, y
