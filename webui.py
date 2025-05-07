from flask import Flask, request, render_template_string, send_from_directory, redirect, url_for
from nltk.stem import PorterStemmer
import os
from spider import webpage, load_stopwords, tokenize_and_filter, read_database as spider_read_database
from retrieval import retrieval

app = Flask(__name__)

# 默认参数配置，可根据实际情况修改
DEFAULT_START_URL = "https://www.cse.ust.hk/~kwtleung/COMP4321/testpage.htm"
DEFAULT_MAX_PAGES = 300
DEFAULT_MAX_RESULTS = 50

# HTML 模板：使用 <pre> 标签及内联 CSS 控制对齐格式
html_template = """
<!DOCTYPE html>
<head>
    <meta charset="utf-8">
    <title>Simple Search Engine</title>
    <link rel="icon" type="image/x-icon" href="/favicon.ico">
    <script>
    // 将弯引号转换成傻瓜引号，并移除非ASCII字符
    function filterInput(el) {
        var value = el.value;
        // 替换智能引号（‘ ’ “ ”）为普通引号 (")
        value = value.replace(/[‘’“”]/g, '"');
        // 移除非ASCII字符
        value = value.replace(/[^\x00-\x7F]/g, '');
        el.value = value;
    }
    document.addEventListener('DOMContentLoaded', function() {
        // 为所有文本输入框添加监听
        var inputs = document.querySelectorAll("input[type='text']");
        inputs.forEach(function(input) {
            input.addEventListener('input', function() {
                filterInput(this);
            });
        });
    });
    </script>
</head>
<body>
    <script>
    document.addEventListener('DOMContentLoaded', function() {
        // 从 sessionStorage 中获取已访问链接列表
        var visited = sessionStorage.getItem('visitedLinks');
        if (visited) {
            visited = JSON.parse(visited);
        } else {
            visited = [];
        }

        // 更新页面上所有已访问链接为紫色（不更新带有 "title-link" 类的链接）
        function updateVisitedLinks() {
            var anchors = document.getElementsByTagName('a');
            for (var i = 0; i < anchors.length; i++) {
                if (visited.indexOf(anchors[i].href) !== -1) {
                    if (!anchors[i].classList.contains("title-link")) {
                        anchors[i].style.color = 'purple';
                    }
                }
            }
        }

        updateVisitedLinks();

        // 监听链接点击事件
        document.addEventListener('click', function(e) {
            var target = e.target;
            // 确保点击的是a标签或者其内部子元素
            while (target && target.tagName && target.tagName.toLowerCase() !== 'a') {
                target = target.parentElement;
            }
            if (target && target.tagName && target.tagName.toLowerCase() === 'a') {
                var url = target.href;
                if (visited.indexOf(url) === -1) {
                    visited.push(url);
                    sessionStorage.setItem('visitedLinks', JSON.stringify(visited));
                    updateVisitedLinks();
                }
            }
        });
    });
    </script>
    <center>
        {% if not query %}
        <pre style="font-family: inherit; font-size: inherit; font-weight: inherit;">
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
        </pre>
        {% endif %}
        <form method="get">
            <div>
                <input type="text" name="query" size="60" placeholder="Type here to search" value="{{ query|default('') }}">
                <input type="submit" value="Search">
            </div>
            <div>
                Start URL: <input type="text" name="start_url" value="{{ start_url }}"><br>
                Max Crawled Pages: <input type="number" name="max_pages" value="{{ max_pages }}"><br>
                Max Results: <input type="number" name="max_results" value="{{ max_results }}">
            </div>
        </form>
        {% if results %}
            <p>{{ results|length }} results found.</p>
            {% for page, score in results %}
<pre style="text-align: left; font-family: inherit; font-size: inherit; font-weight: inherit; width: fit-content; margin-left: auto; margin-right: auto;">
<strong>{{ score|round(4) }}</strong>&#9;<a href="{{ page.url }}" target="_blank"  class="title-link" style="color: inherit; text-decoration: none;">{{ page.title or "Untitled" }}</a>
&#9;&#9;<a href="{{ page.url }}" target="_blank">{{ page.url }}</a>
&#9;&#9;{{ page.date }}, {{ page.size }} Bytes
&#9;&#9;{{ page.keywords }}
{%- for link in page.parent_links %}
&#9;&#9;<a href="{{ link }}" target="_blank">{{ link }}</a>
{%- endfor %}
{%- for link in page.child_links %}
&#9;&#9;<a href="{{ link }}" target="_blank">{{ link }}</a>
{%- endfor %}
</pre>
            {% endfor %}
        {% endif %}
    </center>
</body>
</html>
"""

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, ''), 'favicon.ico', mimetype='image/x-icon')

def generate_keywords(page, stemmer, stopwords):
    """
    生成关键词字符串：首先从 page.body_keywords 中移除多词短语（只保留单词项），
    然后对剩余单词词干化并统计；再利用 tokenize_and_filter 对页面标题生成单词
    （不生成短语），词干化并统计，最后合并两部分。
    返回格式为 "keyword1 freq1; keyword2 freq2; ..."，
    如果关键词总数多于 5，则返回前 5 项，并在第 5 项后加上省略号。
    """
    from collections import Counter  # 防止未引入Counter
    body_counter = Counter()
    if hasattr(page, "body_keywords") and isinstance(page.body_keywords, dict):
        for kw, freq in page.body_keywords.items():
            # 仅保留单词项，去除多词短语
            if len(kw.split()) == 1:
                stemmed = stemmer.stem(kw)
                body_counter[stemmed] += freq

    title_counter = Counter()
    if page.title:
        tokens = tokenize_and_filter(page.title, stopwords)
        for token in tokens:
            stemmed = stemmer.stem(token)
            title_counter[stemmed] += 1

    merged_counter = body_counter + title_counter
    # 对合并后的关键词按照词频从大到小排序
    sorted_keywords = sorted(merged_counter.items(), key=lambda x: x[1], reverse=True)
    # 判断关键词总数，如果大于5只取前5项，并在第5项后加上省略号
    if len(sorted_keywords) > 5:
        top_keywords = sorted_keywords[:5]
        keywords_str = "; ".join(f"{word} {count}" for word, count in top_keywords) + "; ..."
    else:
        keywords_str = "; ".join(f"{word} {count}" for word, count in sorted_keywords)
    return keywords_str

@app.route("/", methods=["GET"])
def index():
    results = []
    # 默认参数赋值
    start_url = DEFAULT_START_URL
    max_pages = DEFAULT_MAX_PAGES
    max_results = DEFAULT_MAX_RESULTS
    # 通过 GET 参数获取搜索查询
    query = request.args.get("query", "").strip()
    # 检查输入是否为空、仅包含非 ASCII 字符或者只包含引号
    if (query and (not any(ord(c) < 128 for c in query) or 
         query.replace('"', '').replace("'", "").strip() == "")):
        # 如果URL中传入了 query 参数但内容无效，则重定向回主页
        return redirect(url_for("index"))
    # 如果 query 为空（即没有搜索要求），直接渲染主页
    if not query:
        return render_template_string(html_template,
                                      results=[],
                                      start_url=DEFAULT_START_URL,
                                      max_pages=DEFAULT_MAX_PAGES,
                                      max_results=DEFAULT_MAX_RESULTS,
                                      query="")
        
    # 获取用户输入的 start_url，如果为空则使用默认值
    start_url = request.args.get("start_url", DEFAULT_START_URL).strip() or DEFAULT_START_URL
    # 检查输入的 start_url 是否以 "http://" 或 "https://" 或 "file://" 开头
    if not (start_url.startswith("http://") or start_url.startswith("https://") or start_url.startswith("file://")):
        if start_url.endswith((".html", ".htm", ".shtml", ".jsp", ".php")):
            # 转换为 file:// 形式
            start_url = "file://" + os.path.abspath(start_url)
        else:
            start_url = "http://" + start_url
    try:
        max_pages = int(request.args.get("max_pages", DEFAULT_MAX_PAGES))
        if max_pages <= 0:
            max_pages = DEFAULT_MAX_PAGES
    except Exception:
        max_pages = DEFAULT_MAX_PAGES
    try:
        max_results = int(request.args.get("max_results", DEFAULT_MAX_RESULTS))
        if max_results <= 0:
            max_results = DEFAULT_MAX_RESULTS
    except Exception:
        max_results = DEFAULT_MAX_RESULTS
        
    # 后续的数据库读取和检索逻辑...
    try:
        db_pages, start_page = spider_read_database("webpages.db")
    except Exception:
        db_pages = None
    if (db_pages is None or start_page is None or len(db_pages) > max_pages or start_page.url != start_url):
        for db_file in ["webpages.db", "body_inverted_index.db", "title_inverted_index.db"]:
            if os.path.exists(db_file):
                os.remove(db_file)
                
    results = retrieval(start_url, query, max_pages, max_results)
    stopwords = set(load_stopwords("stopwords.txt"))
    stemmer = PorterStemmer()
    for i, (page, score) in enumerate(results):
        kw_str = generate_keywords(page, stemmer, stopwords)
        page.keywords = kw_str
        results[i] = (page, score)
    return render_template_string(html_template,
                                  results=results,
                                  start_url=start_url,
                                  max_pages=max_pages,
                                  max_results=max_results,
                                  query=query)

if __name__ == "__main__":
    print("Port: 11451")
    app.run(debug=True, port=11451)