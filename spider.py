import requests
from lxml import html
from collections import deque, Counter
from urllib.parse import urljoin  # 用于处理相对链接
from datetime import datetime, timezone
import sqlite3
import re
import os
import sys
import base64
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 网页
class webpage:
    title = ""  # 网页标题
    url = ""  # 网页链接
    date = datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)  # 最后修改时间
    size = 0
    body_keywords = {}  # 正文关键词及其频率
    parent_links = set()  # 父链接
    child_links = set()  # 子链接

    def __init__(self, url="", title="", date=None, size=0, body_keywords=None, parent_links=None, child_links=None):
        self.url = url
        self.title = title
        self.date = date if date else datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        self.size = size
        self.body_keywords = body_keywords if body_keywords else {}
        self.parent_links = parent_links if parent_links else set()
        self.child_links = child_links if child_links else set()

    def __eq__(self, other):
        if isinstance(other, webpage):
            return self.url == other.url
        elif isinstance(other, str):
            return self.url == other
        return False

    def __hash__(self):
        return hash(self.url)

def to_base64(s):
    """将字符串 s 编码成 base64 字符串。"""
    return base64.b64encode(s.encode("utf-8")).decode("utf-8")

def from_base64(b64_str):
    """将 base64 字符串解码成 UTF-8 字符串。"""
    return base64.b64decode(b64_str.encode("utf-8")).decode("utf-8")

def read_database(database_file):
    """
    读取 webpages.db 并返回网页集合和 is_start 为 1 的页面，
    数据库中的每一项均为 base64 编码，读取后进行解码。
    :param database_file: SQLite 数据库文件名。
    :return: (webpage 集合, start_page) 或 (None, None)
    """
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), database_file)
    if not os.path.exists(db_path):
        return None, None

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT url, title, date, size, body_keywords, parent_links, child_links, is_start FROM webpages")
        rows = cursor.fetchall()
        webpages = set()
        start_page = None
        for row in rows:
            # 解码每个字段
            try:
                url = from_base64(row[0])
                title = from_base64(row[1])
                date_str = from_base64(row[2])
                size_str = from_base64(row[3])
                body_keywords_str = from_base64(row[4]) if row[4] else ""
                parent_links_str = from_base64(row[5]) if row[5] else ""
                child_links_str = from_base64(row[6]) if row[6] else ""
                is_start_str = from_base64(row[7]) if row[7] else "0"
            except Exception:
                continue

            date = datetime.fromisoformat(date_str) if date_str else datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            try:
                size = int(size_str)
            except:
                size = 0

            body_keywords = {}
            if body_keywords_str:
                for item in body_keywords_str.split(","):
                    parts = item.split(":")
                    if len(parts) == 2:
                        key = parts[0]
                        try:
                            value = int(parts[1])
                        except:
                            value = 0
                        body_keywords[key] = value

            parent_links = set(parent_links_str.split(",")) if parent_links_str else set()
            child_links = set(child_links_str.split(",")) if child_links_str else set()

            page = webpage(
                url=url,
                title=title,
                date=date,
                size=size,
                body_keywords=body_keywords,
                parent_links=parent_links,
                child_links=child_links
            )
            webpages.add(page)
            if is_start_str == "1":
                start_page = page

        if not start_page:
            return None, None

        return webpages, start_page

    except Exception:
        return None, None

    finally:
        conn.close()

def save_to_database(database_file, visited, start_url):
    """
    Save all visited webpages to a SQLite database.
    存入数据库时，每个字段都以 base64 编码后存储。
    :param database_file: SQLite 数据库文件名。
    :param visited: 一个 webpage 的集合。
    :param start_url: 起始 URL。
    """
    conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), database_file))
    cursor = conn.cursor()

    # 创建表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS webpages (
            url TEXT PRIMARY KEY,
            title TEXT,
            date TEXT,
            size TEXT,
            body_keywords TEXT,
            parent_links TEXT,
            child_links TEXT,
            is_start TEXT
        )
    ''')

    for page in visited:
        parent_links_str = ",".join(page.parent_links)
        child_links_str = ",".join(page.child_links)
        body_keywords_str = ",".join(f"{key}:{value}" for key, value in page.body_keywords.items())
        is_start = "1" if page.url == start_url else "0"

        # 将所有数据转换为字符串，然后分别 Base64 编码
        url_b64 = to_base64(page.url)
        title_b64 = to_base64(page.title)
        date_b64 = to_base64(page.date.isoformat())
        size_b64 = to_base64(str(page.size))
        body_keywords_b64 = to_base64(body_keywords_str)
        parent_links_b64 = to_base64(parent_links_str)
        child_links_b64 = to_base64(child_links_str)
        is_start_b64 = to_base64(is_start)

        cursor.execute('''
            INSERT OR REPLACE INTO webpages (url, title, date, size, body_keywords, parent_links, child_links, is_start)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (url_b64, title_b64, date_b64, size_b64, body_keywords_b64, parent_links_b64, child_links_b64, is_start_b64))

    conn.commit()
    conn.close()

def load_stopwords(stopwords_file):
    """
    从文件中加载停用词。
    :return: 停用词集合。
    """
    try:
        with open(os.path.dirname(os.path.abspath(__file__)) + "/" + stopwords_file, "r", encoding="utf-8") as file:
            stopwords = set(line.strip() for line in file if line.strip())
        return stopwords
    except FileNotFoundError:
        return set()

def tokenize_and_filter(text, stopwords):
    """
    对文本进行分词，并移除停用词。
    :param text: 输入的纯文本。
    :param stopwords: 停用词集合。
    :return: 过滤后的单词列表。
    """
    # 使用正则表达式提取单词（忽略标点符号）
    words = re.findall(r'\b\w+\b', text.lower())

    # 移除停用词
    filtered_words = [word for word in words if word not in stopwords]
    return filtered_words

def spider(start_url, max_pages, bool_save_to_database=True):
    """
    A simple web spider that crawls pages using BFS.

    :param start_url: The starting URL for the spider.
    :param max_pages: The maximum number of pages to crawl.
    :return: A set of visited webpage objects.
    """
    # 加载停用词
    stopwords = load_stopwords("stopwords.txt")

    visited = set()  # 访问过的网页对象集合
    queue = deque([webpage(url=start_url)])  # BFS 队列，初始化时只设置 URL

    # 尝试从数据库读取数据
    webpages, start_page = read_database("webpages.db")

    # 检查数据库是否有效
    valid_old_database = True
    if webpages is None or start_page is None or max_pages != len(webpages) or start_page.url != start_url:
        valid_old_database = False

    while queue and len(visited) < max_pages:
        current_page = queue.popleft()  # 从队列中取出一个 webpage 对象

        try:
            # 抓取当前页面的内容
            response = requests.get(current_page.url, timeout=5)
            response.raise_for_status()  # 出错时抛出异常

            # 获取 Last-Modified 字段
            last_modified = response.headers.get("Last-Modified")
            if last_modified:
                try:
                    # 将 Last-Modified 转换为 datetime 对象
                    last_modified_date = datetime.strptime(last_modified, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
                    current_page.date = last_modified_date  # 更新为 Last-Modified 的值
                except ValueError:
                    # 如果 Last-Modified 不存在
                    if response.status_code != 304 or not valid_old_database:
                        # 将当前时间（UTC）作为日期
                        current_page.date = datetime.now(timezone.utc)
                    else:
                        continue
            else:
                # 如果 Last-Modified 不存在
                if response.status_code != 304 or not valid_old_database:
                    # 将当前时间（UTC）作为日期
                    current_page.date = datetime.now(timezone.utc)
                else:
                    continue

            # 使用 HTML 内容的长度计算网页大小
            html_content = response.content  # 获取网页的二进制内容
            current_page.size = len(html_content)  # 使用内容长度作为字节数

            # 检查当前页面是否已经被访问过
            existing_page = next((page for page in visited if page.url == current_page.url), None)
            if existing_page:
                # 如果 current_page 的最后修改时间更新，则删除 visited 中的项
                if current_page.date > existing_page.date:
                    visited.remove(existing_page)
                else:
                    continue

            # 解析 HTML
            tree = html.fromstring(response.content)

            # 提取网页正文内容
            body_text = " ".join(tree.xpath('//body//text()[not(parent::script) and not(parent::style)]'))

            # 单词统计：先经过 tokenize_and_filter（移除停用词）
            words = tokenize_and_filter(body_text, stopwords)
            single_counter = Counter(words)

            # 提取原始单词列表（不过滤），用于短语提取
            raw_words = re.findall(r'\b\w+\b', body_text.lower())
            phrase_counter = Counter()
            for n in range(2, 6):  # 组合连续2到5个单词为短语
                for i in range(len(raw_words) - n + 1):
                    phrase = " ".join(raw_words[i:i+n])
                    phrase_counter[phrase] += 1

            # 合并单词和短语的统计结果
            combined_counter = single_counter + phrase_counter

            # 更新到当前页面的 body_keywords
            current_page.body_keywords = dict(combined_counter)

            # 更新网页标题
            title = tree.xpath('//title/text()')
            current_page.title = title[0] if title else "Untitled"

            # 将当前页面添加到 visited 集合
            visited.add(current_page)

            # 提取所有链接
            links = tree.xpath('//a/@href')  # 解析所有超链接
            child_pages = []
            for link in links:
                # 将相对链接转换为绝对链接
                absolute_link = urljoin(current_page.url, link)
                # 添加绝对链接为子链接
                current_page.child_links.add(absolute_link)
                # 检查链接是否已经在 visited 中
                existing_child_page = next((page for page in visited if page.url == absolute_link), None)
                if existing_child_page:
                    last_modified_date = datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
                    try:
                        # 发送 HEAD 请求
                        response = requests.head(absolute_link, timeout=5)
                        response.raise_for_status()  # 如果状态码不是 2xx，抛出异常

                        # 获取 Last-Modified 字段
                        last_modified = response.headers.get("Last-Modified")
                        if last_modified:
                            try:
                                # 将 Last-Modified 转换为 datetime 对象
                                last_modified_date = datetime.strptime(last_modified, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
                            except ValueError:
                                # 如果 Last-Modified 不存在
                                if last_modified_date == datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc) or response.status_code != 304:
                                    # 将当前时间（UTC）作为日期
                                    last_modified_date = datetime.now(timezone.utc)
                        else:
                            # 如果 Last-Modified 不存在
                            if last_modified_date == datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc) or response.status_code != 304:
                                # 将当前时间（UTC）作为日期
                                last_modified_date = datetime.now(timezone.utc)

                    except Exception:
                        pass
                    if last_modified_date > existing_child_page.date:  # 链接已经在 visited 中但页面已被更改，则创建新的 webpage 对象并加入队列
                        new_page = webpage(url=absolute_link, parent_links=(existing_child_page.parent_links | {current_page.url}))
                        queue.append(new_page)
                        child_pages.append(new_page)
                    # 如果链接已经在 visited 中且页面未被更改，更新其 parent_links
                    else:
                        existing_child_page.parent_links.add(current_page.url)
                        child_pages.append(existing_child_page)
                else:
                    # 如果链接未被访问过，则创建新的 webpage 对象并加入队列
                    new_page = webpage(url=absolute_link, parent_links={current_page.url})
                    queue.append(new_page)
                    child_pages.append(new_page)

            # 在之前是子链接但现在不是子链接的网页的父链接里移除本页
            if existing_page:
                # 比对 existing_page.child_links 与 child_pages
                for child_link in existing_page.child_links:
                    # 如果 child_link 不在 child_pages 中
                    if child_link not in {page.url for page in child_pages}:
                        # 在 visited 中找到对应的页面
                        child_page = next((page for page in visited if page.url == child_link), None)
                        if child_page:
                            # 从 child_page 的 parent_links 中移除 current_page.url
                            if current_page.url in child_page.parent_links:
                                child_page.parent_links.remove(current_page.url)

                            # 如果 child_page 不是 start_url 且其 parent_links 为空，则从 visited 中移除
                            if child_page.url != start_url and not child_page.parent_links:
                                visited.remove(child_page)

                        # 在 queue 中找到对应的页面
                        for queued_page in queue:
                            if queued_page.url == child_link:
                                # 从 queued_page 的 parent_links 中移除 current_page.url
                                if current_page.url in queued_page.parent_links:
                                    queued_page.parent_links.remove(current_page.url)

                                # 如果 queued_page 不是 start_url 且其 parent_links 为空，则从 queue 中移除
                                if queued_page.url != start_url and not queued_page.parent_links:
                                    queue.remove(queued_page)
                                break

        except Exception:
            pass

    if bool_save_to_database:
        save_to_database("webpages.db", visited, start_url)
    return visited