# Vibecoding Signal Light

**中文** | [English](README.en.md)

> 给 AI Agent 一个看得见的菜单栏状态灯。

Vibecoding Signal Light 把 macOS 菜单栏变成 AI 编程助手的环境状态面板。Codex、Claude Code 或其他本地 Agent 开始工作、请求权限、遇到阻塞时，菜单栏图标会同步变化。

它的目标不是炫技，而是让 AI Agent 从屏幕里的文字流，变成一眼就能感知的工作状态。

## 为什么做这个

AI 编程助手越来越能自己跑命令、改文件、开子任务，但它的状态通常还困在终端或聊天窗口里。于是你要么反复切回去看，打断自己的注意力；要么忘了它正在等权限、等你读结果、或者已经失败。

这个项目给 Agent 一个在菜单栏里的可见存在：

- 绿灯：没事，继续你的事。
- 绿灯闪烁：Agent 正在工作。
- 黄闪：Agent 明确需要你看一眼或继续。
- 红闪：需要马上处理，通常是权限、阻塞或失败。

## 灯语

灯语刻意保持简单，并且状态会持续显示。你不需要记复杂动画，只要看当前灯效。

| 灯效 | Agent 状态 | 你该做什么 |
| --- | --- | --- |
| 绿灯常亮 | 空闲 | 不用管 |
| 绿灯闪烁 | 正在思考、跑工具、改文件或测试 | 等它跑 |
| 黄灯闪烁 | 明确需要你读结果或继续 | 有空看一眼 |
| 红灯闪烁 | 需要权限、阻塞或失败 | 马上处理 |
| 全灭 | 手动清除 | 不用管 |

## 功能亮点

- macOS 菜单栏应用，彩色图标 + 浮动详情面板。
- 支持 Codex hook。
- 支持 Claude Code hook。
- 支持多个 Agent 会话并发时的状态聚合。
- 红灯/黄灯告警不会被另一个会话的工作态覆盖。
- 支持通过 launchd 开机自启。

## 快速开始

```bash
cd SignalLightApp && ./build.sh && cd ..          # 构建 macOS 菜单栏应用
open SignalLightApp/.build/SignalLightApp.app     # 启动
```

应用在菜单栏运行，右键点击可查看详情或退出。首次启动会自动配置 launchd 开机自启。

### Hook 安装

安装或修复本地 hook 最简单的方式是内置向导：

```bash
# CLI 二进制（app bundle 内）
APP=SignalLightApp/.build/SignalLightApp.app/Contents/MacOS/SignalLightApp

$APP install-hooks                    # 交互式选择
$APP install-hooks --all -y           # 安装全部 Agent
$APP install-hooks --agent codex --agent claude-code -y
```

也可以右键菜单栏图标 → "Install Hooks" 子菜单，按 Agent 分别安装。向导会识别已支持的 Agent，检查当前 hook 文件，写入前创建带时间戳的备份，并且只安装 Signal Light 自己的 hook 条目，保留同一事件下已有的其它 hook。

## Codex 集成

Codex hook 通过事件名调用：

```bash
$APP codex-hook UserPromptSubmit
$APP codex-hook PreToolUse
$APP codex-hook PermissionRequest
$APP codex-hook Stop
```

推荐映射：

| Codex 事件 | 灯效行为 |
| --- | --- |
| `SessionStart` | 绿灯空闲 |
| `UserPromptSubmit` | 绿灯闪烁（工作中） |
| `PreToolUse` | 绿灯闪烁（工作中） |
| `PostToolUse` | 绿灯闪烁（工作中） |
| `PermissionRequest` | 黄灯闪烁 |
| `Stop` | 清理普通工作态 |
| `SessionEnd` | 绿灯短闪提示完成，然后恢复当前聚合状态 |

完整 `~/.codex/hooks.json` 示例见 [docs/LAMP_LANGUAGE.md](docs/LAMP_LANGUAGE.md)。

## Claude Code 集成

Claude Code 通过 stdin 传入 JSON hook 数据，不需要额外参数：

```bash
echo '{"event":"PreToolUse","session_id":"demo"}' | $APP claude-code-hook
echo '{"event":"PermissionRequest","session_id":"demo"}' | $APP claude-code-hook
echo '{"event":"Notification","session_id":"demo"}' | $APP claude-code-hook
```

支持的 Claude Code 事件包括：

| Claude Code 事件 | 灯效行为 |
| --- | --- |
| `SessionStart` | 绿灯空闲 |
| `UserPromptSubmit` | 绿灯闪烁（工作中） |
| `PreToolUse` | 绿灯闪烁（工作中） |
| `PostToolUse` | 绿灯闪烁（工作中） |
| `PostToolUseFailure` | 红灯闪烁 |
| `Notification` | 黄灯闪烁 |
| `PermissionRequest` | 黄灯闪烁 |
| `Stop` | 清理普通工作态 |
| `SessionEnd` | 绿灯短闪提示完成，然后恢复当前聚合状态 |

完整 `~/.claude/settings.json` 示例见 [docs/LAMP_LANGUAGE.md](docs/LAMP_LANGUAGE.md)。

## 多会话行为

运行时会记录每个 Agent 会话的最新状态，并把最高优先级状态显示到菜单栏：

```text
红灯闪烁 > 黄灯闪烁 > 工作循环 > 绿灯常亮
```

因此，一个会话正在等待权限时，即使另一个会话开始工作，红灯也不会被覆盖。普通 `Stop` 只会清掉非紧急的工作态，不会误清除已有红灯告警。

当某个已记录的会话结束、但其它会话还在运行时，运行时会让绿灯短暂闪烁，提示"有一个会话完成了"，然后恢复当前聚合状态。如果所有会话都结束了，最终会回到绿灯常亮。红灯或黄灯告警不会被这个完成提示打断。

## 项目状态

这是一个可扩展的 AI 编程伴侣项目。你可以很容易地 fork 并扩展它：

- 把更多 Agent 系统映射到同一套灯语。
- 扩展灯语，增加新的信号类型。
- 自定义菜单栏外观或详情面板。

如果 AI Agent 已经成了你的工作流的一部分，给它一盏状态灯。
