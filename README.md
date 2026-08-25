# adb-sms MCP

通过 ADB 读取 Android 手机短信验证码，供 Cursor Agent 配合 **chrome-devtools** 完成 Web 短信登录。

## 项目结构

```
mcp-adb-sms/
├── server.py           # MCP 服务入口
├── adb_client.py       # ADB / SMS / SIM 封装
├── sms_parser.py       # 短信与 OTP 解析
├── test_local.py       # 本地诊断（不启动 MCP）
├── requirements.txt
├── devices.json.example  # 设备手机号配置模板
├── devices.json          # 本地配置（git 忽略，需自行创建）
└── README.md
```

## 前置条件

1. Android 手机开启 **USB 调试** 并授权电脑
2. `adb devices` 显示 `device`
3. Python **3.10+**（推荐 3.12）
4. [Android platform-tools](https://developer.android.com/tools/releases/platform-tools)（含 `adb`）

## 安装

```powershell
git clone https://github.com/<你的用户名>/mcp-adb-sms.git
cd mcp-adb-sms
py -3.12 -m pip install -r requirements.txt
```

### 设备手机号配置（可选）

adb 常读不到 SIM 号码，可复制模板并填写：

```powershell
copy devices.json.example devices.json
# 编辑 devices.json：把 YOUR_DEVICE_SERIAL 换成 adb devices 里的 serial
```

## Cursor 配置

编辑 `%USERPROFILE%\.cursor\mcp.json`，添加：

```json
{
  "mcpServers": {
    "adb-sms": {
      "command": "py",
      "args": [
        "-3.12",
        "E:\\path\\to\\mcp-adb-sms\\server.py"
      ],
      "env": {
        "ADB_PATH": "D:\\RJAZ\\Sdk\\platform-tools\\adb.exe"
      }
    }
  }
}
```

| 字段 | 说明 |
|------|------|
| `args` 中的路径 | 改成你 clone 下来的 `server.py` **绝对路径** |
| `ADB_PATH` | 改成你本机 `adb.exe` 绝对路径；若在 PATH 中可写 `"adb"` |

保存后 **重启 Cursor**，MCP 面板中 `adb-sms` 应变绿。

## 本地自检

```powershell
$env:ADB_PATH="D:\RJAZ\Sdk\platform-tools\adb.exe"
py -3.12 test_local.py
```

正常输出应包含：`devices` 有 serial、`sms_readable: true`。

## MCP 工具

| 工具 | 说明 |
|------|------|
| `adb_health_check` | 诊断设备、SMS、SIM/配置号码 |
| `adb_list_devices` | 列出 ADB 设备 |
| `adb_get_sim_numbers` | SIM 或 devices.json 中的手机号 |
| `adb_read_recent_sms` | 最近 N 条短信 |
| `adb_wait_for_otp` | Web 发码后轮询等新验证码 |
| `adb_grant_sms_permission` | Android 11+ 授权 shell 读 SMS |
| `adb_shell` | 受限 adb shell（白名单） |

### 典型调用顺序

```
adb_health_check()
→ adb_get_sim_numbers()          # 取手机号
→ [chrome-devtools 填号、滑块、点发送验证码]
→ adb_wait_for_otp(timeout=90, sender_filter="Midea|美的")
→ [chrome-devtools 填验证码并登录]
```

## SMS 读不到

```powershell
adb shell appops set com.android.shell READ_SMS allow
```

或在 Agent 中调用 `adb_grant_sms_permission`，再执行 `adb_health_check`。

## 发布到 GitHub

在项目目录执行：

```powershell
cd E:\PTaas\mcp-adb-sms
git init
git add .
git commit -m "Initial commit: adb-sms MCP for Cursor"
gh repo create mcp-adb-sms --public --source=. --push
```

若无 `gh` CLI，可在 GitHub 网页新建空仓库后：

```powershell
git remote add origin https://github.com/<用户名>/mcp-adb-sms.git
git branch -M main
git push -u origin main
```

**注意**：`devices.json` 已在 `.gitignore` 中，不会上传手机号；公开仓库请勿提交真实号码。

## 安全说明

- 仅读取 USB 连接的本机设备短信
- 不持久化短信内容到磁盘
- `adb_shell` 仅允许 content/dumpsys/getprop 等白名单命令
- 仅限本人设备或已授权测试场景

## License

MIT（可按需修改）
