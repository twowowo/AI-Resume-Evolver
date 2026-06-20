"""
LangGraph Checkpoint 回滚工具 — 用于前端 Abort 熔断后的状态事务性回退

当 Agent 深度推演被前端主动 Abort 中断时，利用 LangGraph 的
checkpointer 机制将当前 Thread 恢复到本轮请求发起前的安全快照，
擦除本轮由于卡死/中断导致的脏数据。
"""
import logging

logger = logging.getLogger("CheckpointRollback")


async def rollback_thread_to_parent(compiled_graph, thread_id: str) -> bool:
    """将指定 thread_id 的 LangGraph 状态回滚到父检查点

    Args:
        compiled_graph: 已编译的 LangGraph StateGraph (带 checkpointer)
        thread_id: 要回滚的 thread_id

    Returns:
        True 回滚成功
        False 无父检查点可回滚（首轮请求或状态已丢失）

    原理:
        1. 获取当前 thread 的状态快照 (aget_state)
        2. 通过 parent_config 拿到本轮请求前的历史快照
        3. 用 aupdate_state 将当前状态覆盖为父快照值
        4. 脏数据（本轮 Agent 产生的中间消息/工具调用结果）被原子擦除
    """
    config = {"configurable": {"thread_id": thread_id}}

    try:
        current_state = await compiled_graph.aget_state(config)
    except Exception as e:
        logger.warning(f"[Rollback] aget_state 失败: {type(e).__name__}: {e}")
        return False

    if current_state is None:
        logger.info(f"[Rollback] thread [{thread_id}] 无历史快照，跳过回滚")
        return False

    parent_config = getattr(current_state, "parent_config", None)
    if parent_config is None:
        logger.info(f"[Rollback] thread [{thread_id}] 为初始节点，无父快照可回滚")
        return False

    # 获取父快照的完整状态值
    try:
        parent_state = await compiled_graph.aget_state(parent_config)
    except Exception as e:
        logger.warning(f"[Rollback] 获取父快照失败: {type(e).__name__}: {e}")
        return False

    if parent_state is None or not getattr(parent_state, "values", None):
        logger.warning(f"[Rollback] 父快照 values 为空，无法回滚")
        return False

    parent_values = parent_state.values

    try:
        await compiled_graph.aupdate_state(config, parent_values)
        logger.info(
            f"[Rollback] thread [{thread_id}] 已回滚到父快照 "
            f"(step={getattr(parent_state.metadata, 'step', '?') if hasattr(parent_state, 'metadata') else '?'}), "
            f"本轮脏数据已擦除"
        )
        return True
    except Exception as e:
        logger.error(f"[Rollback] aupdate_state 回滚失败: {type(e).__name__}: {e}")
        return False


def rollback_thread_to_parent_sync(compiled_graph, thread_id: str) -> bool:
    """同步版本 — 在 ThreadPoolExecutor 中调用"""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(rollback_thread_to_parent(compiled_graph, thread_id))

    # 在已运行的事件循环中，创建新任务
    import concurrent.futures
    future = asyncio.run_coroutine_threadsafe(
        rollback_thread_to_parent(compiled_graph, thread_id), loop
    )
    try:
        return future.result(timeout=10)
    except concurrent.futures.TimeoutError:
        logger.error(f"[Rollback] thread [{thread_id}] 回滚超时 (>10s)")
        return False
