import sqlite3
import re
import math
from collections import defaultdict, Counter
from nltk.stem import PorterStemmer
from datetime import datetime, timezone, timedelta
import os
from spider import spider, read_database as spider_read_database, webpage, load_stopwords, from_base64
from indexer import indexer, check_database

# 加载倒排索引数据
def read_database(db_file):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT keyword, postings FROM inverted_index")
    index = defaultdict(list)
    rows = cursor.fetchall()
    for keyword, postings_str in rows:
        # 解码关键字
        decoded_keyword = from_base64(keyword)
        postings = []
        if postings_str:
            for item in postings_str.split(","):
                parts = item.split(":")
                # parts[0]、parts[1]、parts[2] 均为 base64 编码的字符串
                if len(parts) == 3:
                    decoded_url = from_base64(parts[0])
                    decoded_tf = float(from_base64(parts[1]))
                    decoded_tfidf = float(from_base64(parts[2]))
                    postings.append({"url": decoded_url, "tf": decoded_tf, "tf-idf": decoded_tfidf})
        index[decoded_keyword] = postings
    conn.close()
    return index

# 根据倒排索引构造文档向量（字典形式：{doc_url: {term: weight, ...}}）
def build_doc_vectors(inverted_index):
    doc_vectors = defaultdict(dict)
    for term, postings in inverted_index.items():
        for p in postings:
            url = p["url"]
            # 若该文档中该词已经存在则累加（一般不会重复出现）
            doc_vectors[url][term] = p["tf-idf"]
    # 对每个文档的向量按 max(tf-idf) 归一化
    for url, vector in doc_vectors.items():
        max_val = max(vector.values()) if vector else 1.0
        for term in vector:
            vector[term] = vector[term] / max_val
    return doc_vectors

# 合并正文和标题的文档向量，同时对标题部分进行 boost（这里选取 boost=2）
def merge_doc_vectors(body_vectors, title_vectors, title_boost=2.0):
    merged = defaultdict(dict)
    all_docs = set(body_vectors.keys()) | set(title_vectors.keys())
    for url in all_docs:
        merged[url] = {}
        # 添加正文部分
        if url in body_vectors:
            for term, weight in body_vectors[url].items():
                merged[url][term] = merged[url].get(term, 0) + weight
        # 添加标题部分，并进行 boost
        if url in title_vectors:
            for term, weight in title_vectors[url].items():
                merged[url][term] = merged[url].get(term, 0) + title_boost * weight
    return merged

# 解析查询：提取双引号中的短语以及剩余的单个查询词
def parse_query(query, stemmer, stopwords):
    """
    解析查询字符串，提取由双引号括起来的短语与剩余的普通查询词。
    - 对普通查询部分先移除停用词，再进行词干化；
    - 对由双引号括起来的短语不移除停用词，直接返回原始短语，再进行词干化生成词列表。
    返回格式：(query_terms, query_phrases)
      - query_terms: 列表，每个元素已词干化的普通查询词（已过滤停用词）
      - query_phrases: 列表，每个元素为短语对应的词干化列表（短语内部未移除停用词）
    """
    query = query.lower()
    tokens = []   # 保存非短语部分的文本，且过滤停用词
    phrases = []  # 保存提取到的原始短语（不移除停用词）
    i = 0
    n = len(query)
    while i < n:
        if query[i] == '"':
            # 遇到引号，则提取引号内的内容作为短语，不进行停用词过滤
            j = query.find('"', i+1)
            if j == -1:
                break  # 没有闭合直接退出
            phrase = query[i+1:j].strip()
            if phrase:
                phrases.append(phrase)
            i = j + 1
        else:
            # 非引号部分：提取单词并过滤停用词
            j = query.find('"', i)
            if j == -1:
                part = query[i:]
                i = n
            else:
                part = query[i:j]
                i = j
            tokens.extend([token for token in re.findall(r'\w+', part.lower()) if token not in stopwords])
    # 对普通查询词进行词干化
    query_terms = [stemmer.stem(token) for token in tokens if token]
    # 对短语部分：仅进行词干化，不过滤停用词
    query_phrases = []
    for phrase in phrases:
        phrase_tokens = re.findall(r'\w+', phrase.lower())
        if phrase_tokens:
            query_phrases.append([stemmer.stem(token) for token in phrase_tokens])
    return query_terms, query_phrases

# 基于查询构造查询向量（权重为 tf * idf，并归一化）
def build_query_vector(query_terms, total_docs, inverted_indexes):
    # inverted_indexes 为一个列表，可以为 [body_index, title_index]
    # 用于计算每个 term 的文档频率（df）
    df_dict = {}
    for term in query_terms:
        docs_with_term = set()
        for idx in inverted_indexes:
            if term in idx:
                for p in idx[term]:
                    docs_with_term.add(p["url"])
        df_dict[term] = len(docs_with_term)
    q_tf = Counter(query_terms)
    q_vector = {}
    for term, tf in q_tf.items():
        # idf = log(total_docs/(1+df))
        idf = math.log(total_docs / (1 + df_dict.get(term, 0)))
        q_vector[term] = tf * idf
    # 归一化查询向量
    norm = math.sqrt(sum(w**2 for w in q_vector.values()))
    if norm > 0:
        for term in q_vector:
            q_vector[term] /= norm
    return q_vector

# 计算余弦相似度
def cosine_similarity(vec_doc, vec_query):
    dot = 0.0
    for term, weight in vec_query.items():
        if term in vec_doc:
            dot += vec_doc[term] * weight
    norm_doc = math.sqrt(sum(w**2 for w in vec_doc.values()))
    norm_query = math.sqrt(sum(w**2 for w in vec_query.values()))
    if norm_doc == 0 or norm_query == 0:
        return 0.0
    return dot / (norm_doc * norm_query)

# 检查短语是否在文档向量中出现（简单判断所有词是否出现）
def phrase_in_doc(phrase_tokens, doc_vector):
    return all(token in doc_vector for token in phrase_tokens)

# 检查短语是否在文档标题中出现（从标题向量判断）
def phrase_in_title(phrase_tokens, title_vector):
    return all(token in title_vector for token in phrase_tokens)

# 主检索函数：返回按相似度排序的最多 max_results 个文档（格式为 (url, score)）
def retrieval(start_url, query, max_pages=300, max_results=50):
    stemmer = PorterStemmer()
    body_index = None
    title_index = None
    webpages, start_page = spider_read_database("webpages.db")
    # 没有数据库或数据库无效，重新生成索引
    if (not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "body_inverted_index.db"))) or (not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "title_inverted_index.db"))) or (not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "webpages.db"))) or (datetime.now(timezone.utc) - datetime.fromtimestamp(os.path.getmtime(os.path.join(os.path.dirname(os.path.abspath(__file__)), "body_inverted_index.db")), tz=timezone.utc) > timedelta(days=1)) or (datetime.now(timezone.utc) - datetime.fromtimestamp(os.path.getmtime(os.path.join(os.path.dirname(os.path.abspath(__file__)), "title_inverted_index.db")), tz=timezone.utc) > timedelta(days=1)) or (not check_database("webpages.db", start_url, start_page)):
        body_index, title_index = indexer(start_url, max_pages)
    # 数据库有效，加载两个倒排索引
    else:
        body_index = read_database("body_inverted_index.db")
        title_index = read_database("title_inverted_index.db")
    # 构建正文与标题的文档向量
    body_doc_vectors = build_doc_vectors(body_index)
    title_doc_vectors = build_doc_vectors(title_index)
    # 合并文档向量，标题部分加权提升
    merged_doc_vectors = merge_doc_vectors(body_doc_vectors, title_doc_vectors, title_boost=2.0)
    # 计算全库文档集合总数（取正文与标题并集）
    all_docs = set(body_doc_vectors.keys()) | set(title_doc_vectors.keys())
    total_docs = len(all_docs) if all_docs else 1

    # 解析查询，得到普通词和短语（短语为词列表）
    query_terms, query_phrases = parse_query(query, stemmer, load_stopwords("stopwords.txt"))
    # 构造带有权重的计数器，普通词权重为 1
    q_tf = Counter(query_terms)
    # 对于短语中的每个词，如果在普通词里未出现，则加上权重 0.5
    for phrase in query_phrases:
        # 先移除停用词（注意：这里假设停用词是在解析 query_terms 时已去除）
        phrase_tokens = [token for token in phrase if token not in q_tf]
        for token in phrase_tokens:
            q_tf[token] += 0.5

    # 构造 df_dict（文档频率），inverted_indexes 为 [body_index, title_index]
    df_dict = {}
    for term in q_tf:
        docs_with_term = set()
        for idx in [body_index, title_index]:
            if term in idx:
                for p in idx[term]:
                    docs_with_term.add(p["url"])
        df_dict[term] = len(docs_with_term)

    # 构造查询向量：权重为 tf * idf
    q_vector = {}
    for term, tf in q_tf.items():
        idf = math.log(total_docs / (1 + df_dict.get(term, 0)))
        q_vector[term] = tf * idf
    # 对查询向量归一化
    norm = math.sqrt(sum(w**2 for w in q_vector.values()))
    if norm > 0:
        for term in q_vector:
            q_vector[term] /= norm

    # 计算每个文档的初始相似度得分（余弦相似度）
    scores = {}
    for url, doc_vector in merged_doc_vectors.items():
        sim = cosine_similarity(doc_vector, q_vector)
        scores[url] = sim

    # 对于短语查询，检查短语是否出现在文档中，并额外提升得分
    # 如果短语在标题中出现，乘以 2；若仅在正文中出现，乘以 1.5
    for phrase_tokens in query_phrases:
        for url in scores:
            boost = 1.0
            # 检查标题中匹配（利用 title_doc_vectors 中的信息）
            if url in title_doc_vectors and phrase_in_title(phrase_tokens, title_doc_vectors[url]):
                boost = 3.0
            # 否则检查正文匹配
            elif url in body_doc_vectors and phrase_in_doc(phrase_tokens, body_doc_vectors[url]):
                boost = 1.5
            scores[url] *= boost

    # 排序并截取前 max_results 条文档（如果结果数量少于 max_results，则返回全部）
    ranked = sorted([(url, score) for url, score in scores.items() if score > 0], key=lambda x: x[1], reverse=True)
    results = ranked[:max_results]

    # 构造一个从 url 到 webpage 对象的字典（如果 webpages 为 None，则字典为空）
    webpage_dict = { page.url: page for page in webpages } if webpages else {}

    final_results = []
    for url, score in results:
        page_obj = webpage_dict.get(url)
        if page_obj is None:
            # 调用 spider 函数爬取，start_url 设为当前 url，max_pages 为 1，bool_save_to_database 为 False
            new_pages = spider(url, 1, False)
            if new_pages:
                for p in new_pages:
                    if p.url == url:
                        page_obj = p
                        break
        # 如果仍然未找到，则将 url 原样返回（一般不会发生）
        if page_obj is None:
            page_obj = url
        final_results.append((page_obj, score))

    return final_results