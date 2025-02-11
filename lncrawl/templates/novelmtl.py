# -*- coding: utf-8 -*-
import time
from concurrent.futures import Future
from typing import Generator, Iterable, List
from urllib.parse import parse_qs, urlencode, urlparse

from bs4 import BeautifulSoup, Tag

from ..core.exeptions import LNException
from ..models import Chapter, SearchResult
from .soup.paginated_toc import PaginatedSoupTemplate
from .soup.searchable import SearchableSoupTemplate


class NovelMTLTemplate(SearchableSoupTemplate, PaginatedSoupTemplate):
    is_template = True

    def initialize(self) -> None:
        self.cur_time = int(1000 * time.time())

    def get_search_page_soup(self, query: str) -> BeautifulSoup:
        soup = self.get_soup(f"{self.home_url}search.html")
        form = soup.select_one('.search-container form[method="post"]')
        assert isinstance(form, Tag), "No search form"

        action_url = self.absolute_url(form["action"])
        payload = {input["name"]: input["value"] for input in form.select("input")}
        payload["keyboard"] = query
        response = self.submit_form(action_url, payload)
        return self.make_soup(response)

    def select_novel_tags(self, soup: BeautifulSoup) -> Iterable[Tag]:
        return soup.select("ul.novel-list .novel-item a")

    def parse_search_item(self, tag: Tag) -> SearchResult:
        title = tag.select_one(".novel-title").text.strip()
        return SearchResult(
            title=title,
            url=self.absolute_url(tag["href"]),
            info=" | ".join([x.text.strip() for x in tag.select(".novel-stats")]),
        )

    def parse_title(self, soup: BeautifulSoup) -> None:
        tag = soup.select_one(".novel-info .novel-title")
        if not isinstance(tag, Tag):
            raise LNException("No title found")
        self.novel_title = tag.text.strip()

    def parse_cover(self, soup: BeautifulSoup):
        tag = soup.select_one("#novel figure.cover img")
        if isinstance(tag, Tag):
            if tag.has_attr("data-src"):
                self.novel_cover = self.absolute_url(tag["data-src"])
            elif tag.has_attr("src"):
                self.novel_cover = self.absolute_url(tag["src"])

    def parse_authors(self, soup: BeautifulSoup):
        self.novel_author = ", ".join(
            [
                a.text.strip()
                for a in soup.select('.novel-info .author span[itemprop="author"]')
            ]
        )

    def generate_page_soups(
        self, soup: BeautifulSoup
    ) -> Generator[BeautifulSoup, None, None]:
        last_page = soup.select("#chapters .pagination li a")[-1]["href"]
        last_page_qs = parse_qs(urlparse(last_page).query)
        max_page = int(last_page_qs["page"][0])
        wjm = last_page_qs["wjm"][0]

        futures: List[Future] = []
        for i in range(max_page + 1):
            payload = {
                "page": i,
                "wjm": wjm,
                "_": self.cur_time,
                "X-Requested-With": "XMLHttpRequest",
            }
            url = f"{self.home_url}e/extend/fy.php?{urlencode(payload)}"
            f = self.executor.submit(self.get_soup, url)
            futures.append(f)

        self.resolve_futures(futures, desc="TOC", unit="page")
        for i, future in enumerate(futures):
            assert future.done(), f"Failed to get page {i + 1}"
            yield future.result()

    def select_chapter_tags(self, soup: BeautifulSoup) -> Iterable[Tag]:
        return soup.select("ul.chapter-list li a")

    def parse_chapter_item(self, a: Tag, id: int) -> Chapter:
        return Chapter(
            id=id,
            url=self.absolute_url(a["href"]),
            title=a.select_one(".chapter-title").text.strip(),
        )

    def select_chapter_body(self, soup: BeautifulSoup) -> Tag:
        return soup.select_one(".chapter-content")
