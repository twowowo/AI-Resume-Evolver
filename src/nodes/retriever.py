from src.config import get_vector_db_client, get_collection_name
from src.state import AgentState


def retriever_node(state: AgentState):
    """
    检索节点：基于 JD 和原始简历，从 352 条金牌库中提取案例
    """
    print("--- 正在调取金牌案例库 (RAG) ---")
    
    # 1. 初始化客户端（自动识别本地/远程）
    client = get_vector_db_client()
    collection = client.get_collection(name=get_collection_name())
    
    # 2. 执行混合检索 (在此处调用你之前验证过的 RRF 逻辑)
    # 提示：为了简化演示，我们先实现基础的向量检索，稍后合并 BM25
    query_text = f"{state['jd']} {state['resume']}"
    results = collection.query(
        query_texts=[query_text],
        n_results=3,
        include=['documents', 'metadatas']
    )
    
    # 3. 提取并格式化 context
    retrieved_docs = []
    for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
        tag = meta.get('tag', '通用')
        retrieved_docs.append(f"[{tag}] 案例内容：\n{doc}")
    
    context = "\n\n".join(retrieved_docs)
    
    # 4. 更新 State：将检索到的案例塞进 rag_context，并记录内心独白
    return {
        "rag_context": context,
        "internal_monologue": "已检索到 3 条最相关的金牌案例，准备参考其 STAR 话术进行简历重写。"
    }
