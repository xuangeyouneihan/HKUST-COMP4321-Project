from flask import Flask, request, render_template_string
from retrieval import retrieval

app = Flask(__name__)

# 默认参数配置，可根据实际情况修改
DEFAULT_START_URL = "https://www.cse.ust.hk/~kwtleung/COMP4321/testpage.htm"
DEFAULT_MAX_PAGES = 300
DEFAULT_MAX_RESULTS = 50

html_template = """
<!DOCTYPE html>
<html lang="zh-cn">
<head>
    <meta charset="utf-8">
    <title>Simple Search Engine</title>
</head>
<body>
    <center>
        <pre>
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
        <form method="post">
            <div>
                <input type="text" name="query" size="60" placeholder="Type here to search">
                <input type="submit" value="Search">
            </div>
            <div>
                Start URL: <input type="text" name="start_url" value="{{ start_url }}"><br>
                Max Pages: <input type="number" name="max_pages" value="{{ max_pages }}"><br>
                Max Results: <input type="number" name="max_results" value="{{ max_results }}">
            </div>
        </form>
        {% if results %}
            <h2>搜索结果（共 {{ results|length }} 条）：</h2>
            {% for url, score in results %}
                <div>
                    <a href="{{ url }}" target="_blank">{{ url }}</a>
                    <div>得分：{{ score|round(4) }}</div>
                </div>
            {% endfor %}
        {% endif %}
    </center>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    results = []
    # 初始化默认参数
    start_url = DEFAULT_START_URL
    max_pages = DEFAULT_MAX_PAGES
    max_results = DEFAULT_MAX_RESULTS
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        if query:
            # 获取自定义参数
            start_url = request.form.get("start_url", DEFAULT_START_URL).strip() or DEFAULT_START_URL
            try:
                max_pages = int(request.form.get("max_pages", DEFAULT_MAX_PAGES))
            except:
                max_pages = DEFAULT_MAX_PAGES
            try:
                max_results = int(request.form.get("max_results", DEFAULT_MAX_RESULTS))
            except:
                max_results = DEFAULT_MAX_RESULTS
            results = retrieval(start_url, query, max_pages, max_results)
    return render_template_string(html_template, results=results,
                                  start_url=start_url,
                                  max_pages=max_pages,
                                  max_results=max_results)

if __name__ == "__main__":
    # Windows 下启动服务器：python webui.py，默认监听 5000 端口
    app.run(debug=True, port=11451)