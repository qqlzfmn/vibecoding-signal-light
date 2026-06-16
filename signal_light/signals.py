"""Signal definitions — name, summary, and priority classification."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Signal:
    name: str
    summary: str
    attention: str


SIGNALS: dict[str, Signal] = {
    "idle": Signal(
        name="idle",
        summary="Agent 空闲。",
        attention="不需要关注。",
    ),
    "thinking": Signal(
        name="thinking",
        summary="Agent 已收到任务，正在思考或工作。",
        attention="不用处理。",
    ),
    "working": Signal(
        name="working",
        summary="Agent 正在执行工具、读写文件、跑命令或测试。",
        attention="不用处理。",
    ),
    "tool_done": Signal(
        name="tool_done",
        summary="一次工具调用完成，Agent 仍处于工作流中。",
        attention="不用处理。",
    ),
    "attention": Signal(
        name="attention",
        summary="Agent 停下来等你读结果或继续回复。",
        attention="需要你看一眼 Codex。",
    ),
    "permission": Signal(
        name="permission",
        summary="Codex 请求授权或需要你明确批准。",
        attention="需要立即关注。",
    ),
    "blocked": Signal(
        name="blocked",
        summary="Agent 遇到阻塞、失败或无法继续。",
        attention="需要你处理。",
    ),
    "done": Signal(
        name="done",
        summary="任务已完成。",
        attention="建议查看最终答复。",
    ),
    "session_start": Signal(
        name="session_start",
        summary="Codex 会话开始。",
        attention="不用处理。",
    ),
    "session_end": Signal(
        name="session_end",
        summary="Codex 会话结束，回到当前聚合状态。",
        attention="不需要关注。",
    ),
    "session_done": Signal(
        name="session_done",
        summary="一个 Agent 会话结束。",
        attention="不用处理。",
    ),
    "off": Signal(
        name="off",
        summary="关闭所有灯。",
        attention="不需要关注。",
    ),
}
