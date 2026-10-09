# 检索与工具上下文证据

- 任务 ID：f58111a3-4d12-49d9-8d04-665fd512f53a
- 证据状态：未记录
- 读取事件数：25；末尾序号：25

这是读取时可见事件的快照；运行中的任务可能继续追加事件。
模型调用成功不等于模型语义上采纳了证据；hash 不能独自重建源码。

未记录新版检索 / 上下文证据，不从当前索引或工作区补造历史。

## 工具调用 1


    {
      "call_id": "d82d88a0-425d-470e-9ddc-9145abec3b16",
      "tool_call_id": "call_090c0b99b4504acea0d31a04",
      "tool_name": "search_code",
      "event_sequences": [
        4,
        5
      ]
    }

检索结果摘要：未记录（源码读取、跳过或失败也可能没有检索事件）。
预算后工具消息：未记录，不能推断为已发送。
没有唯一匹配的后续模型调用记录，不能推断已提交。

## 工具调用 2


    {
      "call_id": "f0972285-b9bd-4ce1-baa4-e400e17ab575",
      "tool_call_id": "call_e44016e6fb1a44778d704d98",
      "tool_name": "search_code",
      "event_sequences": [
        6,
        7
      ]
    }

检索结果摘要：未记录（源码读取、跳过或失败也可能没有检索事件）。
预算后工具消息：未记录，不能推断为已发送。
没有唯一匹配的后续模型调用记录，不能推断已提交。

## 工具调用 3


    {
      "call_id": "e7ab2e43-44a2-4c64-81cf-eebb2f9cc1ba",
      "tool_call_id": "call_2367146f14474be392b536fb",
      "tool_name": "read_source",
      "event_sequences": [
        10,
        11
      ]
    }

检索结果摘要：未记录（源码读取、跳过或失败也可能没有检索事件）。
预算后工具消息：未记录，不能推断为已发送。
没有唯一匹配的后续模型调用记录，不能推断已提交。

## 工具调用 4


    {
      "call_id": "7c1c8fd5-0fa4-41fc-af01-49fc56d1bfa2",
      "tool_call_id": "call_0837c41a0e4b4df596ca46a0",
      "tool_name": "read_source",
      "event_sequences": [
        12,
        13
      ]
    }

检索结果摘要：未记录（源码读取、跳过或失败也可能没有检索事件）。
预算后工具消息：未记录，不能推断为已发送。
没有唯一匹配的后续模型调用记录，不能推断已提交。

## 模型调用清单


    {
      "call_id": "37157ddb-4133-4aea-b984-18226f65fed2",
      "node_name": "model",
      "started_sequence": 2,
      "finished_sequence": 3,
      "outcome": "completed",
      "context_recorded": false,
      "unmatched_tool_context": []
    }


    {
      "call_id": "38218d65-9a49-487c-ac1d-ea5f08b59f2d",
      "node_name": "model",
      "started_sequence": 8,
      "finished_sequence": 9,
      "outcome": "completed",
      "context_recorded": false,
      "unmatched_tool_context": []
    }


    {
      "call_id": "eb25d4ae-fa6e-4c51-bc71-af48cd5d6cdd",
      "node_name": "model",
      "started_sequence": 14,
      "finished_sequence": 15,
      "outcome": "completed",
      "context_recorded": false,
      "unmatched_tool_context": []
    }


    {
      "call_id": "c1eb47f2-b4d7-497c-8b5c-3aa36c3f8261",
      "node_name": "plan",
      "started_sequence": 16,
      "finished_sequence": 17,
      "outcome": "completed",
      "context_recorded": false,
      "unmatched_tool_context": []
    }

