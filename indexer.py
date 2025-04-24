import os
import sys
import sqlite3
from datetime import datetime, timezone, timedelta
import requests
from nltk.stem import PorterStemmer
from collections import Counter, defaultdict
from math import log
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from spider import read_database, webpage, spider, load_stopwords, tokenize_and_filter

def check_database(database_file, start_url, start_page):
    """
    :param database_file: SQLite 数据库文件名。
    :param start_url: 起始 URL。
    :param start_url: 起始 webpage。
    """
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
        except Exception:
            # 如果 HEAD 请求失败，返回True
            return True

        # 检查 start_url 的最后修改时间是否新于 start_page
        if start_url_last_modified > start_page.date:
            # 检查数据库文件的最后修改时间
            db_last_modified = datetime.fromtimestamp(os.path.getmtime(os.path.dirname(os.path.abspath(__file__)) + "/" + database_file), tz=timezone.utc)
            if datetime.now(timezone.utc) - db_last_modified < timedelta(days=1):
                # 数据库文件有效，返回集合和 start_page
                return True
            else:
                # 数据库需要更新，只返回 False 不删除数据库
                return False

    # 如果条件不满足，删除数据库文件
    os.remove(os.path.dirname(os.path.abspath(__file__)) + "/" + database_file)
    return False

def save_to_database(database_file, inverted_index):
    """
    将单个倒排索引存入指定的 SQLite 数据库文件。
    :param database_file: SQLite 数据库文件名。
    :param inverted_index: 倒排索引，格式为 {keyword: [{"url": url, "tf": tf, "tf-idf": tf-idf}, ...]}。
    """
    # 连接到 SQLite 数据库（如果不存在则创建）
    conn = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + "/" + database_file)
    cursor = conn.cursor()

    # 创建表存储倒排索引
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inverted_index (
            keyword TEXT PRIMARY KEY,
            postings TEXT
        )
    ''')

    # 插入倒排索引
    for keyword, postings in inverted_index.items():
        # 将 postings 转换为字符串格式存储
        postings_str = ",".join(
            f"{posting['url']}:{posting['tf']}:{posting['tf-idf']:.4f}" for posting in postings
        )
        cursor.execute('''
            INSERT OR REPLACE INTO inverted_index (keyword, postings)
            VALUES (?, ?)
        ''', (keyword, postings_str))

    # 提交更改并关闭连接
    conn.commit()
    conn.close()

def indexer(start_url, max_pages):
    """
    尝试从数据库读取数据或调用 spider 爬取网页，
    并基于正文关键词和标题关键词构建倒排索引。
    :param start_url: 起始 URL。
    :param max_pages: 最大爬取页面数。
    :return: 包含正文关键词和标题关键词的倒排索引。
    """
    # 尝试从数据库读取数据
    webpages, start_page = read_database("webpages.db")

    # 数据库无效
    if webpages is None or start_page is None or max_pages != len(webpages) or not check_database("webpages.db", start_url, start_page):
        # 调用 spider 函数进行爬取
        webpages = spider(start_url, max_pages)
        start_page = next((page for page in webpages if page.url == start_url), None)

    # 初始化 PorterStemmer
    stemmer = PorterStemmer()

    # 加载停用词
    stopwords = load_stopwords("stopwords.txt")

    # 构建正文关键词倒排索引
    body_inverted_index = defaultdict(list)
    body_document_frequencies = defaultdict(int)  # 用于存储每个正文词干的文档频率（DF）

    # 构建标题关键词倒排索引
    title_inverted_index = defaultdict(list)
    title_document_frequencies = defaultdict(int)  # 用于存储每个标题词干的文档频率（DF）

    total_documents = len(webpages)  # 文档总数

    # 遍历每个网页，填充正文和标题的倒排索引
    for page in webpages:
        # 处理正文关键词
        for keyword, tf in page.body_keywords.items():
            stemmed_keyword = stemmer.stem(keyword)
            body_inverted_index[stemmed_keyword].append({"url": page.url, "tf": tf})
            body_document_frequencies[stemmed_keyword] += 1

        # 处理标题关键词
        title_words = tokenize_and_filter(page.title, stopwords)  # 分词并移除停用词
        title_keywords = Counter(stemmer.stem(word) for word in title_words)  # 统计词频并词干化
        for keyword, tf in title_keywords.items():
            title_inverted_index[keyword].append({"url": page.url, "tf": tf})
            title_document_frequencies[keyword] += 1

    # 计算正文关键词的 TF-IDF 权重并更新倒排索引
    for keyword, postings in body_inverted_index.items():
        df = body_document_frequencies[keyword]  # 文档频率
        idf = log(total_documents / (1 + df))  # 计算 IDF，避免除以 0
        for posting in postings:
            tf = posting["tf"]
            posting["tf-idf"] = tf * idf  # 计算 TF-IDF 权重

    # 计算标题关键词的 TF-IDF 权重并更新倒排索引
    for keyword, postings in title_inverted_index.items():
        df = title_document_frequencies[keyword]  # 文档频率
        idf = log(total_documents / (1 + df))  # 计算 IDF，避免除以 0
        for posting in postings:
            tf = posting["tf"]
            posting["tf-idf"] = tf * idf  # 计算 TF-IDF 权重

    save_to_database("body_inverted_index.db", body_inverted_index)
    save_to_database("title_inverted_index.db", title_inverted_index)
    return body_inverted_index, title_inverted_index