# Toyoko Monitor

一个本地运行的东横 INN 空房监控工具。当前版本提供酒店目录浏览、空房查询、房型级监控、Bark / Server酱 推送、运行日志查看，以及 Windows / WSL 常驻启动脚本。

## 当前能力

- 按地区加载东横官网酒店目录
- 选择入住 / 退房日期后，批量查询所选酒店的空房情况
- 从查询结果中选择具体房型，加入本地监控
- 后台固定每 15 分钟自动刷新监控状态
- 推送配置页统一管理 Bark / Server酱，并支持测试发送
- 日志页查看应用日志、推送内容日志、推送结果日志

## 运行要求

- Python `3.12+`
- `conda`，推荐 `Miniforge`
- 本地浏览器

运行时依赖不再手工写在 `requirements.txt` 里，统一以 [pyproject.toml](/mnt/d/github/toyoko_monitor/pyproject.toml) 为准。当前声明的运行依赖是：

- `fastapi`
- `httpx`
- `pydantic`
- `uvicorn[standard]`

如果后续要增删依赖，请直接修改 [pyproject.toml](/mnt/d/github/toyoko_monitor/pyproject.toml) 的 `[project.dependencies]` 和 `requires-python`。

## 用 `pyproject.toml` 管理环境

这个仓库当前不维护手写 `requirements.txt`。推荐流程是：

1. 先创建一个名字就叫 `web` 的 conda 环境。
2. 激活这个环境。
3. 用 `pip install -e .` 按 [pyproject.toml](/mnt/d/github/toyoko_monitor/pyproject.toml) 安装项目。

不要假设机器上已经有一个可以“直接进入”的 `web` 环境。你需要先自己创建它，而且环境名必须是 `web`。

原因是：

- [scripts/run_service.sh](/mnt/d/github/toyoko_monitor/scripts/run_service.sh) 里写死了 `conda activate web`
- Windows 包装脚本最终也是调用这个启动脚本

标准安装步骤：

```bash
conda create -n web python=3.12 -y
conda activate web
python -m pip install --upgrade pip
python -m pip install -e .
```

如果你修改了 [pyproject.toml](/mnt/d/github/toyoko_monitor/pyproject.toml)，重新执行一次：

```bash
conda activate web
python -m pip install -e .
```

如果你只想做非 editable 安装，也可以：

```bash
conda activate web
python -m pip install .
```

如果你确实需要导出一份当前环境快照，再在安装完成后执行：

```bash
conda activate web
python -m pip freeze > requirements.lock.txt
```

这个 `requirements.lock.txt` 只是环境快照，不应替代 [pyproject.toml](/mnt/d/github/toyoko_monitor/pyproject.toml) 作为依赖源。

## 本地运行

启动开发服务：

```bash
conda activate web
cd /mnt/d/github/toyoko_monitor
PYTHONPATH=. python -m uvicorn app.main:app --reload
```

启动后打开：

- 主页：`http://127.0.0.1:8000`
- 推送配置页：`http://127.0.0.1:8000/settings`
- 日志页：`http://127.0.0.1:8000/logs`

快速自检：

```bash
conda activate web
cd /mnt/d/github/toyoko_monitor
python -m compileall app
```

## 数据、配置与日志

- 数据库： [data/toyoko_monitor.db](/mnt/d/github/toyoko_monitor/data/toyoko_monitor.db)
- 推送配置： [data/notification.json](/mnt/d/github/toyoko_monitor/data/notification.json)
- 应用日志目录： [logs](/mnt/d/github/toyoko_monitor/logs)
- 推送内容日志： [logs/push.content.log](/mnt/d/github/toyoko_monitor/logs/push.content.log)
- 推送结果日志： [logs/push.result.log](/mnt/d/github/toyoko_monitor/logs/push.result.log)

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

如果你在 WSL 中运行本项目，最稳的方式仍然是：

- Windows 任务计划程序负责开机 / 登录时拉起
- 实际服务进程仍由 WSL 里的 [scripts/run_service.sh](/mnt/d/github/toyoko_monitor/scripts/run_service.sh) 启动

### 从 WSL 手动启动

```bash
cd /mnt/d/github/toyoko_monitor
./scripts/run_service.sh
```

停止：

```bash
cd /mnt/d/github/toyoko_monitor
./scripts/stop_service.sh
```

### 从 Windows 手动启动

启动：

```bat
D:\github\toyoko_monitor\scripts\windows\start-toyoko-monitor.cmd
```

停止：

```bat
D:\github\toyoko_monitor\scripts\windows\stop-toyoko-monitor.cmd
```

### 注册为登录自启

```powershell
cd D:\github\toyoko_monitor
powershell -ExecutionPolicy Bypass -File .\scripts\windows\install-startup-task.ps1
```

立即启动一次：

```powershell
Start-ScheduledTask -TaskName ToyokoMonitor
```

移除：

```powershell
cd D:\github\toyoko_monitor
powershell -ExecutionPolicy Bypass -File .\scripts\windows\remove-startup-task.ps1
```

### 注册为 Windows 服务

如果你希望它出现在 `services.msc` 里，建议使用 `NSSM` 包装，而不是直接把 `wsl.exe` 当 Windows Service。

安装：

```powershell
cd D:\github\toyoko_monitor
powershell -ExecutionPolicy Bypass -File .\scripts\windows\install-service.ps1
```

卸载：

```powershell
cd D:\github\toyoko_monitor
powershell -ExecutionPolicy Bypass -File .\scripts\windows\remove-service.ps1
```

### 日志文件

- [logs/uvicorn.stdout.log](/mnt/d/github/toyoko_monitor/logs/uvicorn.stdout.log)
- [logs/uvicorn.stderr.log](/mnt/d/github/toyoko_monitor/logs/uvicorn.stderr.log)
- [logs/nssm-service.stdout.log](/mnt/d/github/toyoko_monitor/logs/nssm-service.stdout.log)
- [logs/nssm-service.stderr.log](/mnt/d/github/toyoko_monitor/logs/nssm-service.stderr.log)

## 注意事项

- 如果你的 Miniforge / conda 初始化脚本路径不是 `/home/yuxx/miniforge3/etc/profile.d/conda.sh`，请同步修改 [scripts/run_service.sh](/mnt/d/github/toyoko_monitor/scripts/run_service.sh)。
- 如果你把 conda 环境命名成别的名字，启动脚本和 Windows 包装脚本不会自动适配。
- 当前实现使用东横官网日文站点数据，酒店名、地区名、房型名会保持日文。
