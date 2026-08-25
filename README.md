# adb-sms MCP

通过 ADB 读取 Android **短信验证码**，供 Cursor Agent 配合 **chrome-devtools** 完成 Web 短信登录。

> **设计原则**：手机号由用户在 `devices.json` 里配置；adb 只负责识别设备 serial + 读短信 OTP。

## 工作原理

```
USB 连接手机（adb devices → serial）
        │
        ├─ devices.json[serial].phone_numbers  →  Web 填手机号
        │
        └─ adb 读短信 inbox                    →  adb_wait_for_otp 拿验证码
```

## 项目结构

```
mcp-adb-sms/
├── server.py              # MCP 服务入口
├── adb_client.py          # ADB 设备 / 短信读取
├── sms_parser.py          # 短信与 OTP 解析
├── test_local.py          # 本地自检（不启动 MCP）
├── requirements.txt
├── devices.json.example   # 手机号配置模板（提交到 git）
├── devices.json           # 本地配置（git 忽略，需自行创建）
└── README.md
```

## 前置条件

1. Android 手机开启 **USB 调试** 并授权电脑
2. `adb devices` 显示 `device`（非 `unauthorized`）
3. Python **3.10+**（推荐 3.12）
4. [Android platform-tools](https://developer.android.com/tools/releases/platform-tools)（含 `adb`）
## 安装

```powershell
git clone https://github.com/zalazp/mcp-adb-sms.git
cd mcp-adb-sms
py -3.12 -m pip install -r requirements.txt
```

### 配置手机号（必填）

手机号**不由 adb 读取**，请自行写入 `devices.json`：

```powershell
copy devices.json.example devices.json
```

1. 运行 `adb devices`，记下 serial（例如 `10AD410LNF000PX`）
2. 以 serial 为 key，填入该手机的**全部**手机号

```json
{
  "10AD410LNF000PX": {
    "model": "V2271A",
    "brand": "vivo",
    "phone_numbers": [
      "13800138000",
      "13900139000"
    ]
  }
}
```

| 字段 | 说明 |
|------|------|
| key（serial） | `adb devices` 第一列，用于匹配当前连接的设备 |
| `phone_numbers` | 该设备上所有可用于 Web 登录的手机号（双卡填多个） |

## Cursor 配置

编辑 `%USERPROFILE%\.cursor\mcp.json`：

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
| `args` 中的路径 | 改成 clone 目录下 `server.py` 的**绝对路径** |
| `ADB_PATH` | 本机 `adb.exe` 绝对路径；已在 PATH 中可写 `"adb"` |

保存后 **重启 Cursor**，MCP 面板中 `adb-sms` 应变绿。

## 本地自检

```powershell
cd mcp-adb-sms
$env:ADB_PATH="D:\RJAZ\Sdk\platform-tools\adb.exe"
py -3.12 test_local.py
```

正常输出示例：

```json
{
  "adb_exists": true,
  "devices": [{ "serial": "10AD410LNF000PX", "state": "device" }],
  "sms_readable": true,
  "sim_numbers": [
    { "number": "13800138000", "available": true },
    { "number": "13900139000", "available": true }
  ],
  "device_profile": { "source": "devices.json" }
}
```

若 `recommendations` 提示缺少配置，按上文创建 `devices.json`。

## MCP 工具

| 工具 | 说明 |
|------|------|
| `adb_health_check` | 诊断 adb、短信可读性、`devices.json` 是否已配置 |
| `adb_list_devices` | 列出已连接 ADB 设备 |
| `adb_get_sim_numbers` | 从 `devices.json` 读取当前 serial 的手机号 |
| `adb_read_recent_sms` | 读取最近 N 条短信 |
| `adb_wait_for_otp` | Web 点击发送验证码后，轮询等待新 OTP |
| `adb_grant_sms_permission` | Android 11+ 尝试授权 shell 读 SMS |
| `adb_shell` | 受限 adb shell（白名单命令） |

### Agent 典型流程（短信登录）

```
1. adb_health_check()
2. adb_get_sim_numbers()              ← 从 devices.json 取手机号
3. chrome-devtools: 打开登录页、填号、勾选协议
4. chrome-devtools: 滑块验证码（失败则人工完成）
5. chrome-devtools: 点击「发送验证码」
6. adb_wait_for_otp(timeout=90, sender_filter="Midea|美的")
7. chrome-devtools: 填入验证码并登录
```

## 短信读不到时

```powershell
adb shell appops set com.android.shell READ_SMS allow
```

或在 Agent 中调用 `adb_grant_sms_permission`，再执行 `adb_health_check`。

仍失败时，MCP 会尝试 `dumpsys notification` 降级读取通知栏短信（精度较低）。

## 安全说明

- 仅读取 **USB 连接的本机设备** 短信
- 不持久化短信内容到磁盘
- `devices.json` 含手机号，已在 `.gitignore` 中，**请勿提交到公开仓库**
- `adb_shell` 仅允许 content / dumpsys / getprop 等白名单命令
- 仅限本人设备或已授权测试场景

## License

MIT
