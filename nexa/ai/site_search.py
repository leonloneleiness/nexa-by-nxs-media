"""Tìm kiếm / hỏi NGAY TRONG một trang web hay dịch vụ (ChatGPT, YouTube, Facebook, Shopee…) thay vì Google.

"Tìm kiếm trong ChatGPT về Nguyễn Xuân Sơn" → mở chatgpt.com/?q=… : trang tự điền và gửi câu hỏi. Dùng địa chỉ tìm
kiếm chính thức của từng trang (tham số trong URL). Riêng trợ lý AI (ask=True): NEXA còn kiểm tra câu hỏi đã được
gửi thật chưa; nếu trang bỏ qua ?q=, NEXA gõ câu hỏi + Enter — CHỈ khi con trỏ đang ở ô soạn thảo trong đúng trang
đó (xem tool_registry._ensure_question_sent).

Thêm trang mới: thêm một dòng vào SITES (tên hiển thị, các cách gọi dạng fold, mẫu URL với {q}).
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass

from nexa.utils.text import fold


@dataclass(frozen=True)
class SearchSite:
    key: str
    name: str
    aliases: tuple[str, ...]      # dạng fold (không dấu, chữ thường)
    url: str                      # mẫu URL, {q} = câu tìm đã mã hóa
    ask: bool = False             # trợ lý AI: "hỏi ChatGPT …" cũng dùng được
    plus: bool = True             # mã hóa khoảng trắng thành "+" (quote_plus) hay "%20" (quote)


SITES: tuple[SearchSite, ...] = (
    # Chỉ ?q= : khi đã đăng nhập, thêm hints=search làm ChatGPT bật "Tìm kiếm trên mạng" nhưng BỎ MẤT câu hỏi
    # (ảnh anh Sơn 23:19: ô nhập trống). ChatGPT tự quyết định tìm trên mạng khi câu hỏi cần.
    SearchSite("chatgpt", "ChatGPT", ("chatgpt", "chat gpt", "chat gi pi ti", "chat gi bi ti", "gpt"),
               "https://chatgpt.com/?q={q}", ask=True, plus=False),
    SearchSite("claude", "Claude", ("claude", "claude ai", "clout", "clau"), "https://claude.ai/new?q={q}", ask=True,
               plus=False),
    SearchSite("perplexity", "Perplexity", ("perplexity", "po ple xi ti"), "https://www.perplexity.ai/search?q={q}",
               ask=True),
    SearchSite("youtube", "YouTube", ("youtube", "you tube"), "https://www.youtube.com/results?search_query={q}"),
    SearchSite("facebook", "Facebook", ("facebook", "fb", "phay buc"), "https://www.facebook.com/search/top?q={q}",
               plus=False),
    SearchSite("tiktok", "TikTok", ("tiktok", "tik tok", "tic tac"), "https://www.tiktok.com/search?q={q}", plus=False),
    SearchSite("wikipedia", "Wikipedia", ("wikipedia", "wiki", "wi ki", "bach khoa toan thu"),
               "https://vi.wikipedia.org/w/index.php?search={q}"),
    SearchSite("maps", "Google Maps", ("google maps", "google map", "ban do", "maps"),
               "https://www.google.com/maps/search/{q}", plus=False),
    SearchSite("images", "Google Hình ảnh", ("google hinh anh", "google anh", "hinh anh google", "google images"),
               "https://www.google.com/search?tbm=isch&q={q}"),
    SearchSite("news", "Google Tin tức", ("google tin tuc", "google news", "tin tuc google"),
               "https://news.google.com/search?q={q}&hl=vi&gl=VN&ceid=VN:vi", plus=False),
    SearchSite("translate", "Google Dịch", ("google dich", "google translate", "dich google"),
               "https://translate.google.com/?sl=auto&tl=vi&op=translate&text={q}", plus=False),
    SearchSite("shopee", "Shopee", ("shopee", "sopi", "so pi"), "https://shopee.vn/search?keyword={q}", plus=False),
    SearchSite("lazada", "Lazada", ("lazada", "la da da"), "https://www.lazada.vn/catalog/?q={q}"),
    SearchSite("tiki", "Tiki", ("tiki", "ti ki"), "https://tiki.vn/search?q={q}"),
    SearchSite("github", "GitHub", ("github", "git hub"), "https://github.com/search?q={q}"),
    SearchSite("spotify", "Spotify", ("spotify",), "https://open.spotify.com/search/{q}", plus=False),
    SearchSite("gmail", "Gmail", ("gmail", "email", "hop thu"), "https://mail.google.com/mail/u/0/#search/{q}",
               plus=False),
    SearchSite("drive", "Google Drive", ("google drive", "drive"), "https://drive.google.com/drive/search?q={q}"),
    SearchSite("bing", "Bing", ("bing",), "https://www.bing.com/search?q={q}"),
)
BY_KEY = {s.key: s for s in SITES}

_ALIAS_TO_SITE: dict[str, SearchSite] = {}
for _s in SITES:
    for _a in _s.aliases:
        _ALIAS_TO_SITE[_a] = _s
# Tên dài khớp trước ("google maps" trước "maps").
_ALIASES = sorted(_ALIAS_TO_SITE, key=len, reverse=True)
SITE_RE = "(?:" + "|".join(re.escape(a) for a in _ALIASES) + ")"


def find_site(name: str) -> SearchSite | None:
    key = re.sub(r"\s+", " ", fold(name or "")).strip(" .,!?")
    if key in BY_KEY:
        return BY_KEY[key]
    return _ALIAS_TO_SITE.get(key)


def search_url(site: SearchSite, query: str) -> str:
    q = urllib.parse.quote_plus(query) if site.plus else urllib.parse.quote(query)
    return site.url.format(q=q)
