# cc-connect 部署指南

> 本文档供 AI 智能体参考，用于在 Windows 环境下部署 cc-connect 桥接服务。
> cc-connect 是一个将 Claude Code 连接到即时通讯平台（如微信）的桥接工具。

---

## 1. 环境准备

### 1.1 安装 Node.js

cc-connect 依赖 Node.js 运行时。

```powershell
# 检查是否已安装
node -v    # 需要 v18+
npm -v
```

如未安装，前往 https://nodejs.org 下载 LTS 版本。

### 1.2 安装 Claude Code CLI

cc-connect 底层调用 Claude Code，需确保 `claude` 命令可用：

```powershell
npm install -g @anthropic-ai/claude-code
```

### 1.3 配置 Claude Code 模型

在 `~/.claude/settings.json` 中设置你的模型端点：

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "你的API密钥",
    "ANTHROPIC_BASE_URL": "你的API端点",
    "ANTHROPIC_MODEL": "你的模型名称"
  }
}
```

---

## 2. 安装 cc-connect

```powershell
npm install -g cc-connect
```

验证安装：

```powershell
cc-connect --version
# 输出类似: cc-connect v1.3.2
```

---

## 3. 配置 cc-connect

### 3.1 初始化配置

首次运行会在 `~/.cc-connect/` 下生成默认配置文件：

```powershell
cc-connect
# Ctrl+C 停止，然后编辑配置
```

### 3.2 编辑 config.toml

配置文件位于 `~/.cc-connect/config.toml`，关键字段说明：

```toml
data_dir = ""                    # 数据目录，留空使用默认
attachment_send = "on"           # 是否发送附件
language = "zh"                  # 界面语言

# ---- 模型提供商 ----
[[providers]]
  name = "你的提供商名称"
  api_key = "你的API密钥"
  base_url = "https://你的API端点/anthropic"
  model = "模型名称"
  agent_types = ["claudecode"]

  [providers.options]
    model = "模型名称"

# ---- 项目配置 ----
[[projects]]
  name = "项目名称"

  [projects.agent]
    type = "claudecode"

    [projects.agent.options]
      mode = "bypassPermissions"    # 跳过权限确认（生产环境建议用其他模式）
      work_dir = "你的工作目录绝对路径"

  # ---- 平台配置（以微信为例）----
  [[projects.platforms]]
    type = "weixin"

    [projects.platforms.options]
      account_id = "你的企业微信机器人ID"
      base_url = "https://ilinkai.weixin.qq.com"
      token = "你的token"

# ---- 日志 ----
[log]
  level = "info"                   # debug / info / warn / error

# ---- Bridge（可选，用于 Web 控制台）----
[bridge]
  enabled = true
  port = 9810
  token = "自定义token"
  cors_origins = ["*"]

# ---- 管理面板（可选）----
[management]
  enabled = true
  port = 9820
  token = "自定义token"
  cors_origins = ["*"]
```

---

## 4. 手动启动测试

```powershell
# 设置环境变量（如果你的提供商需要）
$env:ANTHROPIC_MODEL = "你的模型名称"
$env:CLAUDECODE = ""

# 启动
cc-connect
```

观察日志输出，确认连接成功后 `Ctrl+C` 停止。

---

## 5. 配置开机自启（静默运行）

cc-connect 需要长期运行。通过 Windows 计划任务 + VBS 脚本实现静默后台启动。

### 5.1 创建 VBS 启动脚本

在 `~/.cc-connect/` 下创建 `cc-connect.vbs`：

```vbs
CreateObject("WScript.Shell").Run "cmd /c ""set CLAUDECODE= && set ANTHROPIC_MODEL=你的模型名称 && cc-connect""", 0, False
```

> **说明：** `", 0, False` 表示隐藏窗口运行，不弹出黑色终端。

### 5.2 创建计划任务

用管理员权限的 PowerShell 执行：

```powershell
# 删除旧任务（如果存在）
schtasks /delete /tn "cc-connect-guardian" /f 2>$null

# 创建计划任务：用户登录时自动启动
schtasks /create /tn "cc-connect-guardian" `
  /tr "wscript.exe `"C:\Users\你的用户名\.cc-connect\cc-connect.vbs`"" `
  /sc onlogon `
  /rl highest `
  /f
```

### 5.3 验证

```powershell
# 查看任务状态
schtasks /query /tn "cc-connect-guardian" /fo LIST /v

# 确认进程在运行
Get-Process cc-connect -ErrorAction SilentlyContinue
```

---

## 6. 配置要点总结

| 组件 | 作用 | 文件位置 |
|------|------|---------|
| `config.toml` | cc-connect 主配置 | `~/.cc-connect/config.toml` |
| `cc-connect.vbs` | 静默启动脚本 | `~/.cc-connect/cc-connect.vbs` |
| 计划任务 | 开机自启 + 崩溃重启 | Windows 任务计划程序 |
| `settings.json` | Claude Code 模型配置 | `~/.claude/settings.json` |

---

## 7. 常用运维命令

```powershell
# 查看 cc-connect 进程
Get-Process cc-connect

# 查看日志（如果配置了日志文件）
Get-Content ~/.cc-connect/logs/*.log -Tail 50

# 重启 cc-connect
Stop-Process -Name cc-connect -Force
# VBS 会通过计划任务自动重新拉起，或手动：
wscript.exe "$env:USERPROFILE\.cc-connect\cc-connect.vbs"

# 查看计划任务状态
schtasks /query /tn "cc-connect-guardian" /fo LIST

# 卸载
schtasks /delete /tn "cc-connect-guardian" /f
npm uninstall -g cc-connect
```

---

## 8. 故障排查

| 问题 | 排查方向 |
|------|---------|
| cc-connect 启动后立即退出 | 检查 `config.toml` 语法，运行 `cc-connect` 看报错 |
| 消息发不出去 | 检查平台 token 是否过期，网络是否通畅 |
| 进程不存在但计划任务在 | 查看 VBS 路径是否正确，环境变量是否生效 |
| 模型调用失败 | 确认 `ANTHROPIC_MODEL` 和 `ANTHROPIC_BASE_URL` 设置正确 |

---

## 9. 安全提示

- `config.toml` 中包含 API 密钥和 token，**不要**提交到公开仓库
- `mode = "bypassPermissions"` 会跳过所有权限确认，仅在可信环境使用
- 定期轮换 bridge/management 的 token
- 计划任务使用 `InteractiveToken` 登录类型，确保用户已登录 Windows

---

*文档生成时间：2026-06-02 | cc-connect v1.3.2 | Windows 11*
