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
   
## 安装

```powershell
git clone https://github.com/zalazp/mcp-adb-sms.git
cd mcp-adb-sms
py -3.12 -m pip install -r requirements.txt
```

### 设备手机号配置（必填）

手机号**不由 adb 读取**，请用户自行配置：

1. `adb devices` 查看 serial（如 `10AD410LNF000PX`）
2. 复制 `devices.json.example` → `devices.json`
3. 以 serial 为 key，填入该手机的**全部**手机号

```json
{
  "10AD410LNF000PX": {
    "phone_numbers": ["18317840243", "19139582095"]
  }
}
```

adb 只负责：**识别当前连接设备** + **读短信验证码**。

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
| `adb_health_check` | 诊断设备、SMS、devices.json 是否已配置 |
| `adb_list_devices` | 列出 ADB 设备 |
| `adb_get_sim_numbers` | 从 devices.json 读取该 serial 的手机号 |
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



## 安全说明

- 仅读取 USB 连接的本机设备短信
- 不持久化短信内容到磁盘
- `adb_shell` 仅允许 content/dumpsys/getprop 等白名单命令
- 仅限本人设备或已授权测试场景

