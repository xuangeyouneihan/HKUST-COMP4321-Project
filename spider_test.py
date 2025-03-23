import os
import sys
from collections import Counter
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import spider_indexer
# import io

# # 强制将标准输出和错误流的编码设置为 UTF-8
# sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
# sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import nltk
nltk.download("wordnet")

print("""
       　  　▃▆█▇▄▖
　 　 　 ▟◤▖　　　◥█▎
   　 ◢◤　 ▐　　　 　▐▉
　 ▗◤　　　▂　▗▖　　▕█▎
　◤　▗▅▖◥▄　▀◣　　█▊
▐　▕▎◥▖◣◤　　　　◢██
█◣　◥▅█▀　　　　▐██◤
▐█▙▂　　     　◢██◤
◥██◣　　　　◢▄◤
 　　▀██▅▇▀
""")

# start_url = "https://www.cse.ust.hk/~kwtleung/COMP4321/testpage.htm"
start_url = "https://comp4321-hkust.github.io/testpages/testpage.htm"
max_pages = 30

# 尝试从数据库读取数据
webpages, start_page = spider_indexer.indexer_read_database("webpages.db")

# 数据库无效
if webpages is None or start_page is None or not spider_indexer.indexer_check_database("webpages.db", start_url, start_page):
    # 调用 spider 函数进行爬取
    webpages = spider_indexer.spider(start_url, max_pages)
    start_page = next((page for page in webpages if page.url == start_url), None)

with open((os.path.dirname(os.path.abspath(__file__)) + "/spider_result.txt"), "w", encoding="utf-8") as file:
    total_pages = len(webpages)
    for index, page in enumerate(webpages):
        # 处理标题关键词
        stopwords = spider_indexer.load_stopwords("stopwords.txt")
        title_words = spider_indexer.tokenize_and_filter(page.title, stopwords)  # 分词并移除停用词
        title_keywords = Counter(title_words)  # 统计词频

        # 合并正文关键词和标题关键词
        combined_keywords = Counter(page.body_keywords)  # 将正文关键词转换为 Counter
        for keyword, freq in title_keywords.items():
            combined_keywords[keyword] += freq  # 如果关键词已存在，则累加词频

        # 获取关键词词频的前 10 项
        top_keywords = combined_keywords.most_common(10)

        # 写入页面标题
        file.write(f"{page.title}\n")
        # 写入 URL
        file.write(f"{page.url}\n")
        # 写入最后修改日期和页面大小
        file.write(f"{page.date.isoformat()}, {page.size} bytes\n")
        # 写入前 10 个关键词及其频率
        keywords_str = "; ".join(f"{key} {value}" for key, value in top_keywords)
        file.write(f"{keywords_str}\n")
        # 写入子链接（限制最多写入 10 个）
        for i, child_link in enumerate(page.child_links):
            if i >= 10:  # 超过 10 个子链接时停止写入
                break
            file.write(f"{child_link}\n")
        # 写入分隔符（仅当不是最后一个网页时）
        if index < total_pages - 1:
            file.write("——————————————–\n")
    file.close()

spider_indexer.indexer(start_url, max_pages)