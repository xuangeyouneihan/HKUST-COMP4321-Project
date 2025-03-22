import requests
from lxml import html
from collections import deque
from urllib.parse import urljoin  # 用于处理相对链接
from datetime import datetime, timezone, timedelta
import sqlite3
import re
from collections import Counter
import os
from nltk.stem import PorterStemmer
from collections import defaultdict

stopwords_path = os.path.dirname(os.path.abspath(__file__)) + "/stopwords.txt"
database_path = os.path.dirname(os.path.abspath(__file__)) + "/webpages.db"

# 网页
class webpage:
    title = ""  # 网页标题
    url = ""  # 网页链接
    date = datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)  # 最后修改时间
    keywords = {}  # 关键字及其频率
    parent_links = set()  # 父链接
    child_links = set()  # 子链接

    def __init__(self, url="", title="", date=None, keywords=None, parent_links=None, child_links=None):
        self.url = url
        self.title = title
        self.date = date if date else datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        self.keywords = keywords if keywords else {}
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

def save_to_database(visited, start_url):
    """
    Save all visited webpages to a SQLite database.

    :param visited: A set of webpage objects.
    :param start_url: The starting URL for the spider.
    """
    # 连接到 SQLite 数据库（如果不存在则创建）
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    # 创建表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS webpages (
            url TEXT PRIMARY KEY,
            title TEXT,
            date TEXT,
            parent_links TEXT,
            is_start INTEGER
        )
    ''')

    # 插入数据
    for page in visited:
        parent_links_str = ",".join(page.parent_links)  # 将父链接集合转换为字符串
        is_start = 1 if page.url == start_url else 0  # 标记是否为起始 URL
        cursor.execute('''
            INSERT OR REPLACE INTO webpages (url, title, date, parent_links, is_start)
            VALUES (?, ?, ?, ?, ?)
        ''', (page.url, page.title, page.date.isoformat(), parent_links_str, is_start))

    # 提交更改并关闭连接
    conn.commit()
    conn.close()

def read_webpages_db():
    """
    读取 webpages.db 并返回网页集合和 is_start 为 1 的页面。
    :return: 一个包含 webpage 对象的集合和 start_page 对象，或者 (None, None)。
    """
    # 检查数据库文件是否存在
    if not os.path.exists(database_path):
        print("数据库文件不存在。")
        return None, None

    # 连接到 SQLite 数据库
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    try:
        # 读取数据库中的所有记录
        cursor.execute("SELECT url, title, date, parent_links, is_start FROM webpages")
        rows = cursor.fetchall()

        # 转换为 webpage 对象集合
        webpages = set()
        start_page = None

        for row in rows:
            url, title, date_str, parent_links_str, is_start = row
            date = datetime.fromisoformat(date_str) if date_str else datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            parent_links = set(parent_links_str.split(",")) if parent_links_str else set()

            page = webpage(url=url, title=title, date=date, parent_links=parent_links)
            webpages.add(page)

            # 标注 is_start 为 1 的页面
            if is_start == 1:
                start_page = page

        # 如果没有找到 is_start 为 1 的页面，返回 None
        if not start_page:
            print("数据库中没有标记为 is_start 的页面。")
            return None, None

        return webpages, start_page

    except Exception as e:
        print(f"读取数据库时出错：{e}")
        return None, None

    finally:
        conn.close()

def check_database(start_url, start_page):
    # 比对 start_page 与 start_url
    if start_page.url == start_url:
        # 发送 HEAD 请求获取 start_url 的最后修改时间
        try:
            response = requests.head(start_url, timeout=5)
            response.raise_for_status()
            last_modified = response.headers.get("Last-Modified")
            if last_modified:
                start_url_last_modified = datetime.strptime(last_modified, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
            else:
                start_url_last_modified = datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        except Exception as e:
            print(f"无法获取 start_url 的最后修改时间：{e}")
            # 如果 HEAD 请求失败，返回True
            return True

        # 检查 start_url 的最后修改时间是否新于 start_page
        if start_url_last_modified <= start_page.date:
            # 检查数据库文件的最后修改时间
            db_last_modified = datetime.fromtimestamp(os.path.getmtime(database_path), tz=timezone.utc)
            if datetime.now(timezone.utc) - db_last_modified < timedelta(days=1):
                # 数据库文件有效，返回集合和 start_page
                return True

    # 如果条件不满足，删除数据库文件
    print("数据库文件无效，删除数据库。")
    os.remove(database_path)
    return False

def load_stopwords():
    """
    从文件中加载停用词。
    :return: 停用词集合。
    """
    try:
        with open(stopwords_path, "r", encoding="utf-8") as file:
            stopwords = set(line.strip() for line in file if line.strip())
        return stopwords
    except FileNotFoundError:
        print(f"停用词文件 {stopwords_path} 未找到，使用空停用词列表。")
        return set()

def extract_text_content(tree):
    """
    提取网页的标题和正文内容。
    :param tree: lxml 的 HTML 解析树。
    :return: 提取的纯文本内容。
    """
    # 提取标题
    title = tree.xpath('//title/text()')
    title_text = title[0] if title else ""

    # 提取正文内容，忽略脚本和样式
    body_text = " ".join(tree.xpath('//body//text()[not(parent::script) and not(parent::style)]'))

    # 合并标题和正文内容
    full_text = f"{title_text} {body_text}"
    return full_text

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

def spider(start_url, max_pages):
    """
    A simple web spider that crawls pages using BFS.

    :param start_url: The starting URL for the spider.
    :param max_pages: The maximum number of pages to crawl.
    :return: A set of visited webpage objects.
    """
    # 加载停用词
    stopwords = load_stopwords()

    visited = set()  # 访问过的网页对象集合
    queue = deque([webpage(url=start_url)])  # BFS 队列，初始化时只设置 URL

    while queue and len(visited) < max_pages:
        current_page = queue.popleft()  # 从队列中取出一个 webpage 对象

        try:
            # 抓取当前页面的内容
            response = requests.get(current_page.url, timeout=5)
            response.raise_for_status()  # 出错时抛出异常

            # 获取最后修改日期并更新
            if current_page.date != datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc):
                last_modified = response.headers.get("Last-Modified")
                last_modified_date = datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
                if last_modified:
                    try:
                        # 将 Last-Modified 转换为 datetime 对象
                        last_modified_date = datetime.strptime(last_modified, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass
                current_page.date = last_modified_date

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

            # 提取网页标题和正文内容
            full_text = extract_text_content(tree)

            # 分词并移除停用词
            words = tokenize_and_filter(full_text, stopwords)

            # 统计词频并更新到 keywords
            current_page.keywords = dict(Counter(words))

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
                current_page.child_links.add(link)
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
                        last_modified_date = datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
                        if last_modified:
                            try:
                                # 将 Last-Modified 转换为 datetime 对象
                                last_modified_date = datetime.strptime(last_modified, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
                            except ValueError:
                                pass
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

            print(f"Crawled: {current_page.url}")
        except Exception as e:
            print(f"Failed to crawl {current_page.url}: {e}")

    return visited

# def indexer(start_url, max_pages, phrase):
#     """
#     从 phrase 中移除停用词，并尝试从数据库读取数据。
#     如果数据库不存在或无效，则调用 spider 函数进行爬取。
#     :param start_url: 起始 URL。
#     :param max_pages: 最大爬取页面数。
#     :param phrase: 输入的短语字符串。
#     :return: 移除停用词后的单词列表。
#     """
#     # 加载停用词
#     stopwords = load_stopwords()

#     # 分词并移除停用词
#     words = re.findall(r'\b\w+\b', phrase.lower())  # 使用正则表达式分词
#     filtered_words = [word for word in words if word not in stopwords]

#     # 尝试从数据库读取数据
#     webpages, start_page = read_webpages_db(start_url)

#     # 数据库无效
#     if webpages is None or start_page is None or not check_database(start_url, start_page):
#         print("Invalid database, database outdated or the database does not exist. Calling spider()...")
#         # 调用 spider 函数进行爬取
#         webpages = spider(start_url, max_pages)
#         start_page = next((page for page in webpages if page.url == start_url), None)
#         # 保存爬取结果到数据库
#         save_to_database(webpages, start_url)

#     # 初始化 PorterStemmer
#     stemmer = PorterStemmer()

#     # 对 filtered_words 进行 Porter Stemming
#     stemmed_filtered_words = [stemmer.stem(word) for word in filtered_words]

#     # 对 webpages 中的每个 webpage 的 keywords 进行 Porter Stemming
#     for page in webpages:
#         stemmed_keywords = {stemmer.stem(word): freq for word, freq in page.keywords.items()}
#         page.keywords = stemmed_keywords  # 将处理后的关键词写回 keywords 属性

#     return filtered_words

def indexer(start_url, max_pages):
    """
    尝试从数据库读取数据或调用 spider 爬取网页，
    并基于单词和动态生成的短语构建倒排索引。
    :param start_url: 起始 URL。
    :param max_pages: 最大爬取页面数。
    :param phrase: 输入的短语字符串。
    :return: 倒排索引。
    """
    # 尝试从数据库读取数据
    webpages, start_page = read_webpages_db(start_url)

    # 数据库无效
    if webpages is None or start_page is None or not check_database(start_url, start_page):
        print("Invalid database, database outdated or the database does not exist. Calling spider()...")
        # 调用 spider 函数进行爬取
        webpages = spider(start_url, max_pages)
        start_page = next((page for page in webpages if page.url == start_url), None)
        # 保存爬取结果到数据库
        save_to_database(webpages, start_url)

    # 初始化 PorterStemmer
    stemmer = PorterStemmer()

    # 对 webpages 中的每个 webpage 的 keywords 进行 Porter Stemming
    for page in webpages:
        stemmed_keywords = {stemmer.stem(word): freq for word, freq in page.keywords.items()}
        page.keywords = stemmed_keywords  # 将处理后的关键词写回 keywords 属性

    # 构建倒排索引（支持单词和动态生成的短语）
    inverted_index = defaultdict(list)

    for page in webpages:
        # 单词索引
        for keyword in page.keywords:
            inverted_index[keyword].append(page.url)

        # 动态生成短语索引
        content = list(page.keywords.keys())  # 获取关键词列表
        for i in range(len(content) - 1):
            phrase = f"{content[i]} {content[i + 1]}"
            inverted_index[phrase].append(page.url)

    # 去重：确保每个 URL 在倒排索引中只出现一次
    for key in inverted_index:
        inverted_index[key] = list(set(inverted_index[key]))

    return inverted_index

# Example usage
if __name__ == "__main__":
    # start_url = "https://www.cse.ust.hk/~kwtleung/COMP4321/testpage.htm"
    start_url = "https://comp4321-hkust.github.io/testpages/testpage.htm"
    max_pages = 30  # Replace with your desired maximum number of pages
    crawled_pages = spider(start_url, max_pages)

    # 保存到 SQLite 数据库
    save_to_database(crawled_pages, start_url)

    # 打印爬取的网页信息
    print(f"Total crawled pages: {len(crawled_pages)}")
    for page in crawled_pages:
        print(f"URL: {page.url}, Title: {page.title}, Parent Links: {page.parent_links}")