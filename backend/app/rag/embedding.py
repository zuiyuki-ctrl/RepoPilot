import httpx

from ..core import config


def embed_texts(texts: list[str]) -> list[list[float]]:
    # 1. 空列表直接返回 []，不发送请求。
    if not texts:
        return []

    if len(texts) > 10:
        raise ValueError("At most 10 texts are allowed per batch")

    # 2. 校验本批最多 10 条，每条文本不能是空白。
    # 不满足时抛 ValueError。
    # 用 text.strip() 判断，但不要修改实际提交的源码。
    for text in texts:
        if text.strip() == "":
            raise ValueError("Text cannot be an empty string")

    # 3. 检查 API Key、endpoint 非空，
    # 并确认本阶段 dimensions 固定为 1024。
    # 配置无效时抛 ValueError，不在错误信息中包含密钥。
    if not (config.DASHSCOPE_API_KEY and config.EMBEDDING_ENDPOINT and config.EMBEDDING_DIMENSIONS == 1024):
        raise ValueError("Invalid configuration")

    # 4. 组装 headers
    headers = {
        "Authorization": f"Bearer {config.DASHSCOPE_API_KEY}",
        "Content-Type": "application/json"
    }

    # 5. 组装请求体
    request_body = {
        "model": config.EMBEDDING_MODEL,
        "input": texts,
        "encoding_format": "float",
        "dimensions": config.EMBEDDING_DIMENSIONS,
    }

    timeout = httpx.Timeout(
        connect=10.0,
        read=120.0,
        write=30.0,
        pool=10.0,
    )

    with httpx.Client(timeout=timeout) as client:
        # 6. POST 到配置的完整 endpoint
        response = client.post(config.EMBEDDING_ENDPOINT, headers=headers, json=request_body)

        # 7. 检查 HTTP 状态，再解析 JSON
        response.raise_for_status()
        payload = response.json()

    # 8. 从响应的 data 字段取得向量条目。
    # 按每条的 index 升序排序
    items = payload["data"]
    sorted_items  = sorted(items, key=lambda item: item["index"])

    # 9. 检查排序后的 index 列表，
    # 必须恰好等于 list(range(len(texts)))。
    # 否则抛 ValueError，不能将缺失或错位的结果继续使用。
    actual_indexes: list[int] = []

    for item in sorted_items:
        actual_indexes.append(item["index"])

    if actual_indexes != list(range(len(texts))):
        raise ValueError("Embedding response indexes do not match input")

    # 10. 逐条取出 embedding
    embeddings: list[list[float]] = []
    for item in sorted_items:
        vector = item["embedding"]

        # 1. 检查 vector 是否为 list
        if not isinstance(vector, list):
            raise ValueError("Vector format is incorrect")

        # 2. 检查 len(vector) 是否等于 config.EMBEDDING_DIMENSIONS
        if len(vector) != config.EMBEDDING_DIMENSIONS:
            raise ValueError("Vector dimension mismatch")

        # 3. 校验通过后，追加 vector。
        embeddings.append(vector)

    return embeddings