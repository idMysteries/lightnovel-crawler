import itertools
import re
import sys
import unicodedata
from typing import Dict, Set, Union

from bs4 import Comment, Tag

LINE_SEP = "<br>"

INVISIBLE_CHARS = [
    code
    for code in range(sys.maxunicode)
    if unicodedata.category(chr(code)) in {"Cf", "Cc"}
]
NONPRINTABLE = itertools.chain(range(0x00, 0x20), range(0x7F, 0xA0), INVISIBLE_CHARS)
NONPRINTABLE_MAPPING = {character: None for character in NONPRINTABLE}


class TextCleaner:
    def __init__(self) -> None:
        self.bad_text_regex: Set[Union[str, re.Pattern[str]]] = set(
            [
                # remove entire paragraph containing a string or regex pattern
                # WARNING: dangerous to use. use bad_tag_text_pairs instead
            ]
        )
        self.bad_tag_text_pairs: Dict[str, Union[str, re.Pattern[str]]] = {
            # a { tag-name: string or regex pattern } to remove.
            # the tag will be removed if the text inside contains the pattern
        }

        self.bad_tags: Set[str] = set(
            [
                # tag names to remove
                "noscript",
                "script",
                "style",
                "iframe",
                "ins",
                "header",
                "footer",
                "button",
                "input",
                "amp-auto-ads",
                "pirate",
                "figcaption",
                "address",
                "tfoot",
                "object",
                "video",
                "audio",
                "source",
                "nav",
                "output",
                "select",
                "textarea",
                "form",
                "map",
            ]
        )
        self.bad_css: Set[str] = set(
            [
                # css selector to select and remoe tags
                ".code-block",
                ".adsbygoogle",
                ".sharedaddy",
                ".inline-ad-slot",
                ".ads-middle",
                ".jp-relatedposts",
                ".ezoic-adpicker-ad",
                ".ezoic-ad-adaptive",
                ".ezoic-ad",
                ".cb_p6_patreon_button",
                ".adbox",
                ".googlepublisherads",
                ".adblock-service",
                ".adsense-code",
                ".wp-post-navigation",
                "a[href*='paypal.me']",
                "a[href*='patreon.com']",
            ]
        )
        self.p_block_tags: Set[str] = set(
            [
                # tags that can be used as paragraph break
                "p",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "main",
                "aside",
                "article",
                "div",
                "section",
            ]
        )
        self.unchanged_tags: Set[str] = set(
            [
                # tags to keep unchanged with text and attributes
                "pre",
                "canvas",
                "img",
            ]
        )
        self.plain_text_tags: Set[str] = set(
            [
                # tags that will be joined together in a paragraph
                "span",
                "a",
                "abbr",
                "acronym",
                "label",
                "time",
            ]
        )
        self.substitutions: Dict[str, str] = {
            # replace one string with another one
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            "u003c": "&lt;",
            "u003e": "&gt;",
            # '"s': "'s",
            # "“s": "'s",
            # "”s": "'s",
        }
        self.whitelist_attributes: Set[str] = set(
            [
                # the attributes to keep while cleaning a tag
                "src",
                "style",
            ]
        )
        self.whitelist_css_property: Set[str] = set(
            [
                # the css styles to keep while cleaning style tag
                "font-weight",
                "font-style",
            ]
        )

    def extract_contents(self, tag) -> str:
        self.clean_contents(tag)
        body = self.extract_paragraphs(tag)
        paragraphs = " ".join(body).split(LINE_SEP)
        return "".join(
            [
                f"<p>{p.strip()}</p>"
                for p in paragraphs
                if not self.contains_bad_texts(p)
            ]
        )

    def clean_contents(self, div):
        if not isinstance(div, Tag):
            return div

        if self.bad_css:
            for bad in div.select(",".join(self.bad_css)):
                bad.extract()

        for tag in div.find_all(True):
            if isinstance(tag, Comment):
                tag.extract()  # Remove comments
            elif not isinstance(tag, Tag):
                continue  # Skip elements that are not a Tag
            if tag.name in self.bad_tags:
                tag.extract()  # Remove bad tags
            elif tag.name in ["br", "hr"]:
                self.extract_on_duplicate_sibling(tag)
            elif self.tag_contains_bad_text(tag):
                tag.extract()  # Remove tags containing bad texts
            else:
                self.clean_attributes(tag)

        self.clean_attributes(div)
        return div

    def clean_text(self, text) -> str:
        text = str(text).strip()
        text = text.translate(NONPRINTABLE_MAPPING)
        for k, v in self.substitutions.items():
            text = text.replace(k, v)
        return text

    def extract_on_duplicate_sibling(self, tag: Tag):
        next_tag = tag.next_sibling
        if not isinstance(next_tag, Tag):
            return
        if next_tag.name == tag.name:
            tag.extract()

    def clean_attributes(self, tag: Tag) -> dict:
        attrs = {}
        for name, value in tag.attrs.items():
            if name not in self.whitelist_attributes:
                continue
            if name == "style":
                value = self.clean_style_value(value)
            if value:
                attrs[name] = value
        tag.attrs = attrs

    def tag_contains_bad_text(self, tag: Tag) -> bool:
        if tag.name not in self.bad_tag_text_pairs:
            return False
        return re.search(self.bad_tag_text_pairs, tag.text)

    def clean_style_value(self, style: str) -> str:
        clean_css = []
        css = {
            item[0].strip().lower(): item[1].strip()
            for item in [x.split(":", 1) for x in style.split(";")]
            if len(item) == 2 and item[0].strip()
        }
        for name in self.whitelist_css_property:
            value = css.get(name)
            if value:
                clean_css.append(f"{name}:{value}")
        return ";".join(clean_css)

    def extract_paragraphs(self, tag) -> list:
        if not isinstance(tag, Tag):
            return []

        body = []
        for elem in tag.contents:
            if isinstance(elem, Comment):
                continue
            if not isinstance(elem, Tag):
                body.append(self.clean_text(elem))
                continue
            if elem.name in self.unchanged_tags:
                body.append(str(elem))
                continue
            if elem.name == "hr":
                body.append(LINE_SEP)
                # body.append('-' * 8)
                # body.append(LINE_SEP)
                continue
            if elem.name == "br":
                body.append(LINE_SEP)
                continue
            # if not elem.text.strip():
            #     continue

            is_block = elem.name in self.p_block_tags
            is_plain = elem.name in self.plain_text_tags
            content = " ".join(self.extract_paragraphs(elem))

            if is_block:
                body.append(LINE_SEP)

            for line in content.split(LINE_SEP):
                line = line.strip()
                if not line:
                    continue
                if not (is_plain or is_block):
                    line = "<%s>%s</%s>" % (elem.name, line, elem.name)
                body.append(line)
                body.append(LINE_SEP)

            if body and body[-1] == LINE_SEP and not is_block:
                body.pop()

        return [x.strip() for x in body if x.strip()]

    def contains_bad_texts(self, text: str) -> bool:
        if not text.strip():
            return True
        if not self.bad_text_regex:
            return False
        pattern = getattr(self, "__blacklist__", None)
        if not pattern:
            pattern = re.compile("|".join(["(%s)" % p for p in self.bad_text_regex]))
            setattr(self, "__blacklist__", pattern)
        return True if pattern and pattern.search(text) else False
