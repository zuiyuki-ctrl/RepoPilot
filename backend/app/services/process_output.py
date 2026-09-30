from dataclasses import dataclass, field
from typing import TextIO

# 捕获的输出
@dataclass
class CapturedOutput:
    # 已保留的输出片段
    chunks: list[str] = field(default_factory=list)

    # 已保留的字符数
    stored_chars: int = 0

    # 是否丢弃过超出上限的内容
    truncated: bool = False

    # 读取期间出现的异常
    error: Exception | None = None

    def get_text(self) -> str:
        # 用空字符串连接 chunks，返回最终文本。
        return "".join(self.chunks)



# 按剩余容量保存片段
def append_output_chunk(
    captured: CapturedOutput,
    chunk: str,
    *,
    max_chars: int,
) -> None:
    remaining = max_chars - captured.stored_chars

    # 2. remaining > 0 时：
    #    取 chunk[:remaining]，保存为 kept。
    #    kept 非空才追加到 chunks。
    #    stored_chars 增加 len(kept)。
    if remaining > 0:
        kept = chunk[:remaining]

        if kept:
            captured.chunks.append(kept)

        captured.stored_chars += len(kept)


    # 3. 如果 chunk 中有内容没被保存，将 truncated 设为 True。
    if len(chunk) > remaining:
        captured.truncated = True


# 持续读取函数
def drain_text_stream(
    stream: TextIO,
    captured: CapturedOutput,
    *,
    max_chars: int,
) -> None:
    # 1. 循环调用 stream.read(4096)。
    try:
        while True:
            chunk = stream.read(4096)

            # 2. 返回空字符串时结束循环，表示输出流结束。
            if chunk == "":
                break

            # 3. 把非空文本块交给 append_output_chunk。
            append_output_chunk(captured, chunk, max_chars=max_chars)

    # 4. 读取发生异常时，把异常保存到 captured.error。
    except Exception as exc:
        captured.error = exc
    finally:
        try:
            # 5. 关闭 stream。
            stream.close()
        except Exception as exc:
            # 6. 只有 captured.error is None 时，
            #    才将关闭异常保存到 captured.error。
            if captured.error is None:
                captured.error = exc