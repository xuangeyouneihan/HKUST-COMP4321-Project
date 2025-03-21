import requests
from lxml import html
from collections import deque
from urllib.parse import urljoin  # 用于处理相对链接
from datetime import datetime, timezone
import sqlite3

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
    conn = sqlite3.connect("webpages.db")
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

def spider(start_url, max_pages):
    """
    A simple web spider that crawls pages using BFS.

    :param start_url: The starting URL for the spider.
    :param max_pages: The maximum number of pages to crawl.
    :return: A set of visited webpage objects.
    """
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
            title = tree.xpath('//title/text()')  # 获取网页标题
            title = title[0] if title else "Untitled"
            current_page.title = title  # 更新网页标题

            # 将当前页面添加到 visited 集合
            visited.add(current_page)

            # 提取所有链接
            links = tree.xpath('//a/@href')  # 解析所有超链接
            for link in links:
                # 将相对链接转换为绝对链接
                absolute_link = urljoin(current_page.url, link)
                # 添加绝对链接为子链接
                current_page.child_links.add(link)
                # 检查链接是否已经在 visited 中
                existing_page = next((page for page in visited if page.url == absolute_link), None)
                if existing_page:
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
                    if last_modified_date > existing_page.date:  # 链接已经在 visited 中但页面已被更改，则创建新的 webpage 对象并加入队列
                        new_page = webpage(url=absolute_link, parent_links={current_page.url})
                        queue.append(new_page)
                    # 如果链接已经在 visited 中且页面未被更改，更新其 parent_links
                    else:
                        existing_page.parent_links.add(current_page.url)
                else:
                    # 如果链接未被访问过，则创建新的 webpage 对象并加入队列
                    new_page = webpage(url=absolute_link, parent_links={current_page.url})
                    queue.append(new_page)

            print(f"Crawled: {current_page.url}")
        except Exception as e:
            print(f"Failed to crawl {current_page.url}: {e}")

    return visited

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