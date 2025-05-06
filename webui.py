from flask import Flask, request, render_template_string
import sqlite3
import os
import re
from collections import Counter
from nltk.stem import PorterStemmer
from retrieval import retrieval

app = Flask(__name__)

def load_stopwords(file_path="stopwords.txt"):
    if not os.path.exists(file_path):
        return set()
    with open(file_path, encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

stopwords = load_stopwords("stopwords.txt")
stemmer = PorterStemmer()

def tokenize(text):
    # 将文本转换为小写并提取单词
    return re.findall(r'\w+', text.lower())

def get_page_details(url):
    """
    从网页数据库中获取页面详细信息，假定数据库 webpages.db 中有表 webpages，
    表结构中包含：url, title, last_modified, content, parent_links, child_links。
    倘若 last_modified 字段为空，则直接取内容修改日期；若 size 字段不存在，则直接计算内容字符数。
    上层链接和下层链接假定以逗号分隔存储。
    同时，计算页面中出现的、去除停用词后的前 5 个词干和出现频数。
    """
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webpages.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM webpages WHERE url=?", (url,))
    row = cursor.fetchone()
    conn.close()

    if row:
        title = row["title"] if row["title"] else "No Title"
        last_modified = row["last_modified"] if row["last_modified"] else "Unknown"
        content = row["content"] if row["content"] else ""
        size = len(content)
        # 假设 parent_links 和 child_links 字段以逗号分隔字符串存储
        parent_links = row["parent_links"].split(",") if row["parent_links"] else []
        child_links = row["child_links"].split(",") if row["child_links"] else []
        # 计算页面内关键词（去除停用词，并词干化）
        tokens = tokenize(content)
        filtered = [stemmer.stem(token) for token in tokens if token not in stopwords]
        keyword_freq = Counter(filtered)
        top_keywords = keyword_freq.most_common(5)
        return {
            "title": title,
            "url": url,
            "last_modified": last_modified,
            "size": size,
            "top_keywords": top_keywords,
            "parent_links": parent_links,
            "child_links": child_links
        }
    else:
        return {
            "title": "No Title",
            "url": url,
            "last_modified": "Unknown",
            "size": 0,
            "top_keywords": [],
            "parent_links": [],
            "child_links": []
        }

HTML_TEMPLATE = '''
<!doctype html>
<html lang="zh-cn">
<head>
    <meta charset="utf-8">
    <title>简单搜索引擎</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .result { margin-bottom: 20px; padding: 10px; border: 1px solid #ccc; }
        .result h3 { margin: 0; }
        .result a { text-decoration: none; color: blue; }
        .meta { font-size: 0.9em; color: #555; }
        .links { margin-top: 5px; font-size: 0.9em; }
    </style>
</head>
<body>
    <h1>简单搜索引擎</h1>
    <form method="post">
        <input type="text" name="query" size="60" placeholder="请输入查询，短语请用双引号括起来">
        <input type="submit" value="搜索">
    </form>
    {% if results %}
        <h2>搜索结果</h2>
        {% for item in results %}
            <div class="result">
                <div class="score">得分: {{ item.score|round(4) }}</div>
                <h3>
                    <a href="{{ item.url }}" target="_blank">{{ item.title }}</a>
                </h3>
                <div class="meta">
                    <a href="{{ item.url }}" target="_blank">{{ item.url }}</a><br>
                    最后修改时间: {{ item.last_modified }}, 页面大小: {{ item.size }} 字符
                </div>
                <div class="meta">
                    {% if item.top_keywords %}
                        关键词: 
                        {% for kw, freq in item.top_keywords %}
                            {{ kw }} {{ freq }}; 
                        {% endfor %}
                    {% endif %}
                </div>
                <div class="links">
                    {% if item.parent_links %}
                        <div>上层链接:
                        {% for link in item.parent_links %}
                            <a href="{{ link }}" target="_blank">{{ link }}</a> 
                        {% endfor %}
                        </div>
                    {% endif %}
                    {% if item.child_links %}
                        <div>下层链接:
                        {% for link in item.child_links %}
                            <a href="{{ link }}" target="_blank">{{ link }}</a> 
                        {% endfor %}
                        </div>
                    {% endif %}
                </div>
            </div>
        {% endfor %}
    {% endif %}
</body>
</html>
'''

@app.route("/", methods=["GET", "POST"])
def index():
    results = []
    if request.method == "POST":
        query = request.form.get("query", "")
        if query:
            # 调用 retrieval 函数，返回 (url, score) 的列表
            raw_results = retrieval(query, max_results=50)
            for url, score in raw_results:
                details = get_page_details(url)
                details["score"] = score
                results.append(details)
    # 根据得分降序排序结果后再传递给模板
    results.sort(key=lambda x: x["score"], reverse=True)
    return render_template_string(HTML_TEMPLATE, results=results)