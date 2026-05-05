"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import json
import pathlib
import re
import os
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.article.io import to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


class Config:
    """
    Class for unpacking and validating configurations.
    """

    def __init__(self, path_to_config: pathlib.Path) -> None:
        """
        Initialize an instance of the Config class.

        Args:
            path_to_config (pathlib.Path): Path to configuration.
        """
        self._path_to_config = path_to_config
        self._config_dto = None
        self._validate_config_content()

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self._path_to_config, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return ConfigDTO(
            seed_urls=data.get('seed_urls', []),
            total_articles_to_find_and_parse=data.get('total_articles_to_find_and_parse', 0),
            headers=data.get('headers', {}),
            encoding=data.get('encoding', 'utf-8'),
            timeout=data.get('timeout', 5),
            should_verify_certificate=data.get('should_verify_certificate', True),
            headless_mode=data.get('headless_mode', False)
        )


    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        dto = self._extract_config_content()

        pattern = re.compile(r'https?://(www\.)?')
        for url in dto.seed_urls:
            if not pattern.match(url):
                raise IncorrectSeedURLError(f"Invalid seed URL: {url}")

        if not isinstance(dto.total_articles_to_find_and_parse, int) or dto.total_articles_to_find_and_parse <= 0:
            raise IncorrectNumberOfArticlesError(
                "total_articles_to_find_and_parse must be a positive integer"
            )
        if not 1 <= dto.total_articles_to_find_and_parse <= 150:
            raise NumberOfArticlesOutOfRangeError(
                "total_articles_to_find_and_parse must be between 1 and 150"
            )

        if not isinstance(dto.headers, dict):
            raise IncorrectHeadersError("Headers must be a dictionary")

        if not isinstance(dto.encoding, str):
            raise IncorrectEncodingError("Encoding must be a string")

        if not isinstance(dto.timeout, int) or dto.timeout <= 0 or dto.timeout > 60:
            raise IncorrectTimeoutError("Timeout must be an integer between 1 and 60")

        if not isinstance(dto.should_verify_certificate, bool):
            raise IncorrectVerifyError("should_verify_certificate must be a boolean")

        if not isinstance(dto.headless_mode, bool):
            raise IncorrectVerifyError("headless_mode must be a boolean")

        self._config_dto = dto

    def get_seed_urls(self) -> list[str]:
        """
        Retrieve seed urls.

        Returns:
            list[str]: Seed urls
        """
        return self._config_dto.seed_urls

    def get_num_articles(self) -> int:
        """
        Retrieve total number of articles to scrape.

        Returns:
            int: Total number of articles to scrape
        """
        return self._config_dto.total_articles_to_find_and_parse

    def get_headers(self) -> dict[str, str]:
        """
        Retrieve headers to use during requesting.

        Returns:
            dict[str, str]: Headers
        """
        return self._config_dto.headers

    def get_encoding(self) -> str:
        """
        Retrieve encoding to use during parsing.

        Returns:
            str: Encoding
        """
        return self._config_dto.encoding

    def get_timeout(self) -> int:
        """
        Retrieve number of seconds to wait for response.

        Returns:
            int: Number of seconds to wait for response
        """
        return self._config_dto.timeout

    def get_verify_certificate(self) -> bool:
        """
        Retrieve whether to verify certificate.

        Returns:
            bool: Whether to verify certificate or not
        """
        return self._config_dto.should_verify_certificate

    def get_headless_mode(self) -> bool:
        """
        Retrieve whether to use headless mode.

        Returns:
            bool: Whether to use headless mode or not
        """
        return self._config_dto.headless_mode

def make_request(url: str, config: Config) -> requests.models.Response:
    """
    Deliver a response from a request with given configuration.

    Args:
        url (str): Site url
        config (Config): Configuration

    Returns:
        requests.models.Response: A response from a request
    """
    response = requests.get(
        url,
        headers=config.get_headers(),
        timeout=config.get_timeout(),
        verify=config.get_verify_certificate()
    )
    response.encoding = config.get_encoding()
    return response

class Crawler:
    """
    Crawler implementation.
    """

    #: Url pattern
    url_pattern: re.Pattern | str

    def __init__(self, config: Config) -> None:
        """
        Initialize an instance of the Crawler class.

        Args:
            config (Config): Configuration
        """
        self.config = config
        self.urls = []

    def _extract_url(self, article_bs: Tag) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.Tag): Tag instance

        Returns:
            str: Url from HTML
        """
        href = article_bs.get('href')
        if not href:
            return ""
        full_url = urljoin(article_bs.find_parents()[-1].find_previous().name, href)
        return full_url

    def find_articles(self) -> None:
        """
        Find articles.
        """
        needed = self.config.get_num_articles()
        seed_urls = self.config.get_seed_urls()

        for seed in seed_urls:
            if len(self.urls) >= needed:
                break
            try:
                response = make_request(seed, self.config)
                if response.status_code != 200:
                    continue
                soup = BeautifulSoup(response.text, 'html.parser')
                for link in soup.find_all('a', href=True):
                    if len(self.urls) >= needed:
                        break
                    href = link['href']
                    full_url = urljoin(seed, href)
                    if (full_url.startswith('https://www.netslova.ru/piesy/')
                            and '#' not in full_url
                            and full_url != seed
                            and full_url not in self.urls):
                        self.urls.append(full_url)
            except requests.RequestException:
                continue

    def get_search_urls(self) -> list:
        """
        Get seed_urls param.

        Returns:
            list: seed_urls param
        """
        return self.config.get_seed_urls()

# 10


class CrawlerRecursive(Crawler):
    """
    Recursive implementation.

    Get one URL of the title page and find requested number of articles recursively.
    """

    def __init__(self, config: Config) -> None:
        """
        Initialize an instance of the CrawlerRecursive class.

        Args:
            config (Config): Configuration
        """

    def find_articles(self) -> None:
        """
        Find number of article urls requested.
        """


# 4, 6, 8, 10


class HTMLParser:
    """
    HTMLParser implementation.
    """

    def __init__(self, full_url: str, article_id: int, config: Config) -> None:
        """
        Initialize an instance of the HTMLParser class.

        Args:
            full_url (str): Site url
            article_id (int): Article id
            config (Config): Configuration
        """
        self.full_url = full_url
        self.article_id = article_id
        self.config = config
        self.article = Article(url=full_url, article_id=article_id)

    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        for element in article_soup(['script', 'style', 'nav', 'header', 'footer']):
            element.decompose()

        content_candidates = (
            article_soup.find('div', class_='text'),
            article_soup.find('div', class_='content'),
            article_soup.find('div', id='content'),
            article_soup.find('div', class_='entry-content'),
            article_soup.find('pre'),
            article_soup.find('body')
        )
        main_content = None
        for candidate in content_candidates:
            if candidate:
                main_content = candidate
                break
        if main_content is None:
            main_content = article_soup.body

        paragraphs = main_content.find_all(['p', 'pre', 'div'])
        if paragraphs:
            text = '\n\n'.join(p.get_text(strip=True) for p in paragraphs)
        else:
            text = main_content.get_text(strip=True)

        self.article.text = text

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        pass

    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """
        return datetime.datetime.now()

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """
        try:
            response = make_request(self.full_url, self.config)
            if response.status_code != 200:
                return False
            soup = BeautifulSoup(response.text, 'html.parser')
            self._fill_article_with_text(soup)
            return self.article
        except requests.RequestException:
            return False


def prepare_environment(base_path: pathlib.Path | str) -> None:
    """
    Create ASSETS_PATH folder if no created and remove existing folder.

    Args:
        base_path (pathlib.Path | str): Path where articles stores
    """
    path = pathlib.Path(base_path)
    if path.exists():
        for item in path.glob('*'):
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                for subitem in item.glob('*'):
                    if subitem.is_file():
                        subitem.unlink()
                    else:
                        subitem.rmdir()
                item.rmdir()
        path.rmdir()
    path.mkdir(parents=True)

def main() -> None:
    """
    Entrypoint for scraper module.
    """
    config = Config(CRAWLER_CONFIG_PATH)

    prepare_environment(ASSETS_PATH)

    crawler = Crawler(config)
    crawler.find_articles()
    article_urls = crawler.urls

    for idx, url in enumerate(article_urls, start=1):
        parser = HTMLParser(full_url=url, article_id=idx, config=config)
        article = parser.parse()
        if article and article.text:
            to_raw(article, ASSETS_PATH)

if __name__ == "__main__":
    main()
