# Toyoko Monitor

一个本地运行的东横 INN 空房监控工具。当前版本提供酒店目录浏览、空房查询、房型级监控、Bark / Server酱 推送、运行日志查看，以及 WSL / Windows 常驻启动脚本。

## 当前能力

- 按地区加载东横官网酒店目录
- 选择入住 / 退房日期后，批量查询所选酒店的空房情况
- 从查询结果中选择具体房型，加入本地监控
- 后台固定每 15 分钟自动刷新监控状态
- 推送配置页统一管理 Bark / Server酱，并支持测试发送
- 日志页查看应用日志、推送内容日志、推送结果日志

## 运行要求

- Python `3.12+`
- `conda`，推荐 `Miniforge`，镜像之类请自行选用
- 本地浏览器

## 依赖来源

这个仓库当前不维护手写 `requirements.txt`。运行依赖统一由 [pyproject.toml](./pyproject.toml) 管理。

当前声明的运行依赖是：

- `fastapi`
- `httpx`
- `pydantic`
- `uvicorn[standard]`

如果后续需要增删依赖，请直接修改 [pyproject.toml](./pyproject.toml) 的：

- `[project.dependencies]`
- `requires-python`

安装依赖时，推荐直接用：

```bash
python -m pip install -e .
```

这条命令会按 [pyproject.toml](./pyproject.toml) 安装项目，不需要再手工维护一份独立的 `requirements.txt`。

如果你只是想导出当前环境快照，可以在安装完成后执行：

```bash
python -m pip freeze > requirements.lock.txt
```

这个 `requirements.lock.txt` 只是快照，不应替代 [pyproject.toml](./pyproject.toml) 作为依赖源。

## Conda 环境

环境名不一定非得叫 `web`。你可以使用任意 conda 环境名。

不过需要注意：

- [scripts/run_service.sh](./scripts/run_service.sh) 默认会尝试激活 `web`
- 如果你使用别的环境名，需要在运行脚本前设置环境变量 `TOYOKO_MONITOR_CONDA_ENV`

推荐流程如下。

如果你愿意沿用默认值 `web`：

```bash
conda create -n web python=3.12 -y
conda activate web
python -m pip install --upgrade pip
python -m pip install -e .
```

如果你想用别的环境名，例如 `toyoko`：

```bash
conda create -n toyoko python=3.12 -y
conda activate toyoko
python -m pip install --upgrade pip
python -m pip install -e .
```

然后在调用 [scripts/run_service.sh](./scripts/run_service.sh) 前设置：

```bash
export TOYOKO_MONITOR_CONDA_ENV=toyoko
```

如果脚本无法自动找到 `conda.sh`，还可以额外指定：

```bash
export TOYOKO_MONITOR_CONDA_SH=/path/to/conda.sh
```

## 本地运行

在仓库根目录执行：

```bash
conda activate <your-conda-env>
python -m pip install -e .
PYTHONPATH=. python -m uvicorn app.main:app --reload
```

启动后打开：

- 主页：`http://127.0.0.1:8000`
- 推送配置页：`http://127.0.0.1:8000/settings`
- 日志页：`http://127.0.0.1:8000/logs`

快速自检：

```bash
conda activate <your-conda-env>
python -m compileall app
```

## 数据、配置与日志

- 数据库：`data/toyoko_monitor.db`
- 推送配置：`data/notification.json`
- 应用日志目录：`logs/`
- 推送内容日志：`logs/push.content.log`
- 推送结果日志：`logs/push.result.log`

## 推送配置文件

统一推送配置文件位置：

- `data/notification.json`

项目当前优先读取这份文件。旧版 `data/serverchan.json` 只用于兼容旧配置导入，不建议继续作为主配置使用。

`data/notification.json` 的结构如下：

```json
{
  "enabled": true,
  "provider": "bark",
  "serverchan": {
    "send_key": "YOUR_SERVERCHAN_SEND_KEY",
    "channel": "9",  //推送微信，其他参数可以查看serverchan的文档
    "noip": 1,
    "title_prefix": "Toyoko Monitor"
  },
  "bark": {
    "base_url": "https://api.day.app",
    "device_key": "YOUR_BARK_DEVICE_KEY",
    "title_prefix": "Toyoko Monitor",
    "url": "",
    "group": "",
    "icon": "",
    "sound": "alarm",
    "call": false,
    "ciphertext": "",
    "level": "timeSensitive"
  }
}
```

字段说明：

- `enabled`
  当前是否启用推送总开关。
- `provider`
  当前使用哪个推送通道，可选 `bark` 或 `serverchan`。
- `serverchan.send_key`
  Server酱 SendKey，占位符写法请替换成你自己的真实值。
- `serverchan.channel`
  Server酱 推送通道。
- `serverchan.noip`
  是否隐藏调用方 IP；可为 `1`、`0` 或 `null`。
- `serverchan.title_prefix`
  Server酱 标题前缀。
- `bark.base_url`
  Bark 服务地址，默认是官方地址。
- `bark.device_key`
  Bark 设备 Key，占位符写法请替换成你自己的真实值。
- `bark.title_prefix`
  Bark 标题前缀。
- `bark.url`
  点击通知后的跳转地址。
- `bark.group`
  Bark 通知分组。
- `bark.icon`
  Bark 图标地址。
- `bark.sound`
  普通铃声名称。
- `bark.call`
  是否附带 `call=1`。
- `bark.ciphertext`
  Bark 加密推送字段。
- `bark.level`
  Bark 时效性级别，可选 `active`、`timeSensitive`、`passive`、`critical`。

## 刷新与查询逻辑

- 监控刷新间隔固定为 15 分钟
- 手动空房查询仍然会按所选酒店逐个抓取 `room_plan` 明细
- 后台监控刷新已经加了预筛逻辑：
  - 同一批日期 / 人数 / 房间数 / 吸烟条件下，先调用 `hotels.availabilities.prices`
  - 只有批量预筛判断“可能有空房”的酒店，才继续抓 `room_plan` 明细
  - 如果预筛接口失败，会自动回退到旧的逐酒店明细刷新
- `prices` 接口里的吸烟枚举与旧接口不同：
  - 项目内部仍用 `-all`
  - 调用 `prices` 接口时会自动映射成 `all`

## 技术说明

- 后端：`FastAPI`
- 前端：原生 HTML / CSS / JavaScript
- 存储：本地 `SQLite`
- 官网数据来源：
  - `/_next/data/.../ja/hotel_list.json`
  - `/_next/data/.../ja/search/result/room_plan.json`
  - `/api/trpc/hotels.availabilities.prices`

## WSL / Windows 常驻运行

如果你在 WSL 中运行本项目，比较稳的方式是：

- Windows 任务计划程序负责开机 / 登录时拉起
- 实际服务进程由 WSL 里的 [scripts/run_service.sh](./scripts/run_service.sh) 启动

### 从 WSL 手动启动

```bash
./scripts/run_service.sh
```

停止：

```bash
./scripts/stop_service.sh
```

如果你没有使用默认环境名 `web`，先设置：

```bash
export TOYOKO_MONITOR_CONDA_ENV=<your-conda-env>
./scripts/run_service.sh
```

### 从 Windows 手动启动

启动：

```bat
scripts\windows\start-toyoko-monitor.cmd
```

停止：

```bat
scripts\windows\stop-toyoko-monitor.cmd
```

### 注册为登录自启

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\install-startup-task.ps1
```

立即启动一次：

```powershell
Start-ScheduledTask -TaskName ToyokoMonitor
```

移除：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\remove-startup-task.ps1
```

### 注册为 Windows 服务

如果你希望它出现在 `services.msc` 里，建议使用 `NSSM` 包装，而不是直接把 `wsl.exe` 当 Windows Service。

安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\install-service.ps1
```

卸载：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\remove-service.ps1
```

### 日志文件

- `logs/uvicorn.stdout.log`
- `logs/uvicorn.stderr.log`
- `logs/nssm-service.stdout.log`
- `logs/nssm-service.stderr.log`

## 注意事项

- 如果 `scripts/run_service.sh` 无法自动探测 conda 初始化脚本，可以显式设置 `TOYOKO_MONITOR_CONDA_SH`
- 如果你使用了非默认环境名，请显式设置 `TOYOKO_MONITOR_CONDA_ENV`
- 当前实现使用东横官网日文站点数据，酒店名、地区名、房型名会保持日文
