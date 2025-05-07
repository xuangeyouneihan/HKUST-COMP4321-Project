import os
import sys
import sqlite3
from datetime import datetime, timezone, timedelta
import requests
from nltk.stem import PorterStemmer
from collections import Counter, defaultdict
from math import log
import re
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from spider import read_database, webpage, spider, load_stopwords, tokenize_and_filter, to_base64

def check_database(database_file, start_url, start_page):
    """
    检查数据库的有效性
    :param database_file: SQLite 数据库文件名。
    :param start_url: 起始 URL。
    :param start_page: 起始 webpage。
    """
    if start_page.url == start_url:
        try:
            response = requests.head(start_url, timeout=5)
            response.raise_for_status()
            last_modified = response.headers.get("Last-Modified")
            if last_modified:
                start_url_last_modified = datetime.strptime(last_modified, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
            else:
                start_url_last_modified = datetime.now(timezone.utc)
        except Exception:
            # 如果 HEAD 请求失败，认为数据库有效
            return True

        # 如果 start_url 的最后修改时间不早于网页中记录的日期
        if start_url_last_modified >= start_page.date:
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), database_file)
            db_last_modified = datetime.fromtimestamp(os.path.getmtime(db_path), tz=timezone.utc)
            if datetime.now(timezone.utc) - db_last_modified < timedelta(days=1):
                return True
            else:
                return False

    # 如果条件不满足，删除数据库文件后返回 False
    os.remove(os.path.join(os.path.dirname(os.path.abspath(__file__)), database_file))
    return False

# 定义辅助函数，将 posting 编码成 "url_base64:tf_base64:tf-idf_base64"
def encode_posting(posting):
    url_enc = to_base64(posting['url'])
    tf_enc = to_base64(str(posting['tf']))
    tfidf_enc = to_base64(f"{posting['tf-idf']:.4f}")
    return f"{url_enc}:{tf_enc}:{tfidf_enc}"

def save_to_database(database_file, inverted_index):
    """
    将单个倒排索引存入指定的 SQLite 数据库文件。
    存入时，将 keyword 转换为其 base64 编码，
    postings 存储格式为：
    url1_base64:tf1_base64:tf-idf1_base64,url2_base64:tf2_base64:tf-idf2_base64,…
    
    :param database_file: SQLite 数据库文件名。
    :param inverted_index: 倒排索引，格式为 
           {keyword: [{"url": url, "tf": tf, "tf-idf": tf-idf}, ...]}。
    """
    import os, sqlite3
    conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), database_file))
    cursor = conn.cursor()

    # 创建存储倒排索引的表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inverted_index (
            keyword TEXT PRIMARY KEY,
            postings TEXT
        )
    ''')

    for keyword, postings in inverted_index.items():
        # 将 keyword 以 base64 编码存储
        encoded_keyword = to_base64(keyword)
        # 将每个 posting 转换后，用逗号分隔
        postings_str = ",".join(encode_posting(posting) for posting in postings)
        cursor.execute('''
            INSERT OR REPLACE INTO inverted_index (keyword, postings)
            VALUES (?, ?)
        ''', (encoded_keyword, postings_str))

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
            # 如果关键词多于1个单词，则对其中每个单词都进行词干化
            if " " in keyword:
                tokens = keyword.split()
                stemmed_keyword = " ".join(stemmer.stem(token) for token in tokens)
            else:
                stemmed_keyword = stemmer.stem(keyword)
            body_inverted_index[stemmed_keyword].append({"url": page.url, "tf": tf})
            body_document_frequencies[stemmed_keyword] += 1

        # 处理标题关键词

        # 1. 单词统计：通过 tokenize_and_filter 获取去除停用词后的单词，并词干化统计
        title_single_words = tokenize_and_filter(page.title, stopwords)
        title_single_counter = Counter(stemmer.stem(word) for word in title_single_words)

        # 2. 短语统计：直接从原始标题文本提取单词（不移除停用词），组合连续2到5个词构成短语，并词干化每个短语
        raw_title_words = re.findall(r'\b\w+\b', page.title.lower())
        title_phrase_counter = Counter()
        # 当标题较短时，确保 n 不超过标题单词个数
        for n in range(2, min(6, len(raw_title_words) + 1)):
            for i in range(len(raw_title_words) - n + 1):
                phrase = " ".join(raw_title_words[i:i+n])
                # 对短语中的每个单词进行词干化
                stemmed_phrase = " ".join(stemmer.stem(word) for word in phrase.split())
                title_phrase_counter[stemmed_phrase] += 1

        # 合并单词和短语的统计结果
        title_combined_counter = title_single_counter + title_phrase_counter

        # 更新标题倒排索引和文档频率统计
        for keyword, tf in title_combined_counter.items():
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