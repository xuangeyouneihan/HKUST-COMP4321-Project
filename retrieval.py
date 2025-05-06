import sqlite3
import re
import math
from collections import defaultdict, Counter
from nltk.stem import PorterStemmer

# 加载倒排索引数据
def load_database(db_file):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT keyword, postings FROM inverted_index")
    index = defaultdict(list)
    rows = cursor.fetchall()
    for keyword, postings_str in rows:
        postings = []
        if postings_str:
            for item in postings_str.split(","):
                parts = item.split(":")
                if len(parts) == 3:
                    postings.append({"url": parts[0], "tf": float(parts[1]), "tf-idf": float(parts[2])})
        index[keyword] = postings
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
def parse_query(query, stemmer):
    # 提取短语（双引号内内容）
    phrases = re.findall(r'"([^"]+)"', query)
    # 去除短语部分后的剩余查询
    remaining = re.sub(r'"[^"]+"', "", query)
    # 提取单个单词（忽略标点）
    words = re.findall(r'\w+', remaining.lower())
    # 词干化单个查询词
    query_terms = [stemmer.stem(word) for word in words]
    # 对每个短语进行分词并词干化
    query_phrases = []
    for phrase in phrases:
        tokens = re.findall(r'\w+', phrase.lower())
        if tokens:
            query_phrases.append([stemmer.stem(token) for token in tokens])
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
def retrieval(query, max_results=50):
    stemmer = PorterStemmer()
    # 加载两个倒排索引
    body_index = load_database("body_inverted_index.db")
    title_index = load_database("title_inverted_index.db")
    # 构建正文与标题的文档向量
    body_doc_vectors = build_doc_vectors(body_index)
    title_doc_vectors = build_doc_vectors(title_index)
    # 合并文档向量，标题部分加权提升
    merged_doc_vectors = merge_doc_vectors(body_doc_vectors, title_doc_vectors, title_boost=2.0)
    # 计算全库文档集合总数（取正文与标题并集）
    all_docs = set(body_doc_vectors.keys()) | set(title_doc_vectors.keys())
    total_docs = len(all_docs) if all_docs else 1

    # 解析查询，得到单词与短语（其中 phrases 为 list[list[str]]）
    query_terms, query_phrases = parse_query(query, stemmer)
    # 构造查询向量（用 body_index 和 title_index 计算 df）
    q_vector = build_query_vector(query_terms, total_docs, [body_index, title_index])

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
                boost = 2.0
            # 否则检查正文匹配
            elif url in body_doc_vectors and phrase_in_doc(phrase_tokens, body_doc_vectors[url]):
                boost = 1.5
            scores[url] *= boost

    # 排序并返回得分前 max_results 的文档
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked[:max_results]

# 简单测试
if __name__ == "__main__":
    query = input("请输入查询：")
    results = retrieval(query)
    print("排名结果：")
    for url, score in results:
        print(f"{url}: {score:.4f}")