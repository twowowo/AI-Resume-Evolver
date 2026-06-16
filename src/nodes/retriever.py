from src.config import get_vector_db_client, get_collection_name
from src.state import AgentState


def retriever_node(state: AgentState):
    """
    检索节点：基于 JD 和原始简历，从金牌库中提取案例

    v4.2 三层漏斗 Layer 2: ChromaDB where 元数据硬过滤，
    物理阻断跨简历"偷听"任何历史片段的可能性。
    """
    print("--- 正在调取金牌案例库 (RAG) ---")

    # 1. 初始化客户端（自动识别本地/远程）
    client = get_vector_db_client()
    collection = client.get_collection(name=get_collection_name())

    # 2. v4.2 构建元数据硬过滤条件
    user_id = state.get("user_id", "")
    resume_id = state.get("resume_id", "")
    where_filter = None
    if user_id and resume_id:
        where_filter = {"$and": [{"user_id": user_id}, {"resume_id": resume_id}]}
        print(f"[retriever] 三层漏斗 Layer 2 已激活: user_id={user_id}, resume_id={resume_id}")

    # 3. 执行混合检索（带元数据硬过滤）
    query_text = f"{state['jd']} {state['resume']}"
    query_kwargs = {
        "query_texts": [query_text],
        "n_results": 3,
        "include": ['documents', 'metadatas'],
    }
    if where_filter:
        query_kwargs["where"] = where_filter

    results = collection.query(**query_kwargs)

    # 4. 提取并格式化 context
    retrieved_docs = []
    docs_list = results['documents'][0] if results['documents'] else []
    metas_list = results['metadatas'][0] if results['metadatas'] else []
    for doc, meta in zip(docs_list, metas_list):
        tag = meta.get('tag', '通用')
        retrieved_docs.append(f"[{tag}] 案例内容：\n{doc}")

    context = "\n\n".join(retrieved_docs) if retrieved_docs else "(未命中沙箱内案例，以通用知识库兜底)"

    # 5. 更新 State：将检索到的案例塞进 rag_context，并记录内心独白
    return {
        "rag_context": context,
        "internal_monologue": f"[沙箱: {user_id}/{resume_id}] 已检索到 {len(retrieved_docs)} 条隔离区内的金牌案例，准备参考其 STAR 话术进行简历重写。"
    }
