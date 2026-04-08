# Toyoko Monitor

一个本地运行的东横 INN 空房监控工具。

当前版本提供这些能力：

- 按 `area` 拉取东横官网当前酒店列表
- 选择入住 / 退房日期后，批量查询该 area 下酒店是否有空房
- 从查询结果里选中部分酒店，加入本地监控
- 后台每 15 分钟自动刷新一次监控状态
- 用本地 Web 页面查看最新状态

## 技术方案

- 后端：`FastAPI`
- 前端：原生 HTML / CSS / JavaScript
- 存储：本地 `SQLite`
- 官网数据来源：
  - `/_next/data/.../eng/hotel_list.json`
  - `/_next/data/.../eng/search/result/room_plan.json`

## 运行

1. 进入 `web` 环境并安装依赖：

```bash
source /home/yuxx/miniforge3/etc/profile.d/conda.sh
conda activate web
python -m pip install fastapi httpx "uvicorn[standard]" pydantic
```

2. 启动服务：

```bash
PYTHONPATH=. python -m uvicorn app.main:app --reload
```

3. 打开浏览器：

```text
http://127.0.0.1:8000
```

## Windows 本地服务

当前项目运行在 WSL 里的 `conda web` 环境中，所以最稳的 Windows 常驻方式不是直接做原生 Windows Python 服务，而是：

- Windows 任务计划程序负责开机 / 登录时拉起进程
- 实际服务仍然由 WSL 里的 [scripts/run_service.sh](/mnt/d/github/toyoko_monitor/scripts/run_service.sh) 启动

### 手动启动

在 Windows 命令行里直接运行：

```bat
D:\github\toyoko_monitor\scripts\windows\start-toyoko-monitor.cmd
```

停止：

```bat
D:\github\toyoko_monitor\scripts\windows\stop-toyoko-monitor.cmd
```

### 注册为登录自启

在 Windows PowerShell 中运行：

```powershell
cd D:\github\toyoko_monitor
powershell -ExecutionPolicy Bypass -File .\scripts\windows\install-startup-task.ps1
```

注册后可以立即启动一次：

```powershell
Start-ScheduledTask -TaskName ToyokoMonitor
```

删除自启任务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\remove-startup-task.ps1
```

### 注册为 Windows 服务

如果你希望它出现在任务管理器的“服务”页以及 `services.msc` 里，不要直接用 `sc create` 指向 `wsl.exe` 或 `cmd.exe`。它们不是原生 Windows Service 进程，最稳的做法是用 `NSSM` 作为服务包装器。

先准备好 `nssm.exe`，确保它在 `PATH` 中，或者运行脚本时传 `-NssmPath` 指定它的完整路径。

然后在管理员 PowerShell 里执行：

```powershell
cd D:\github\toyoko_monitor
powershell -ExecutionPolicy Bypass -File .\scripts\windows\install-service.ps1
```

脚本会弹出 Windows 账户凭据输入框。这里建议输入“当前这个安装了 WSL / Ubuntu 的同一个 Windows 账户”，否则服务进程可能拿不到你的 WSL 发行版环境。

注册完成后，你可以在这些地方看到并管理它：

- `services.msc`
- 任务管理器 -> `服务`

如果你已经启用了上面的“登录自启计划任务”，建议先删掉或禁用它，否则服务和计划任务可能会重复启动，抢占 `127.0.0.1:8000`。

卸载服务：

```powershell
cd D:\github\toyoko_monitor
powershell -ExecutionPolicy Bypass -File .\scripts\windows\remove-service.ps1
```

### 日志

日志默认写到：

```text
D:\github\toyoko_monitor\logs\uvicorn.stdout.log
D:\github\toyoko_monitor\logs\uvicorn.stderr.log
D:\github\toyoko_monitor\logs\nssm-service.stdout.log
D:\github\toyoko_monitor\logs\nssm-service.stderr.log
```

## Server酱 通知

当前仓库已支持在监控刷新后自动发送 Server酱 微信通知。

- 配置文件路径：`data/serverchan.json`
- 发送方式：`POST`
- 编码方式：`application/json`
- 当前默认通道：`9`（方糖服务号）

行为说明：

- 每次监控刷新结束后，如果本次刷新里有任意监控项出现空房，会汇总成一条通知发送。
- 通知内容会包含本次刷新的全部可订结果，包括酒店名、地址、房型、状态、可订房数、价格、入住退房日期和查询时间。

## 说明

- 监控间隔当前固定为 15 分钟。
- `area` 查询会对该区域酒店逐个检查房型页，因此大区域会稍慢一些。
- 数据库默认保存在 [data/toyoko_monitor.db](/mnt/d/github/toyoko_monitor/data/toyoko_monitor.db)。
- 当前实现使用东横官网日文站点数据，酒店名、小区块名、房型名都会保持日文。
- 监控粒度已细化到单个房型，不再只是整家酒店。
