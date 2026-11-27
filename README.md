# RoboMaster 小车开发记录

保存 RoboMaster EP 小车的调试代码、环境信息和开发历程。

## 当前功能

| 文件 | 用途 |
| --- | --- |
| `控制小车代码/01_sta_pair.py` | 交互输入 Wi-Fi 信息，生成临时二维码并等待小车加入网络 |
| `控制小车代码/02_sta_check.py` | 通过 STA 模式连接小车，读取固件版本，不发送运动指令 |
| `控制小车代码/03_ep_control.py` | Tkinter 控制窗口，支持 STA/AP 连接、按住方向按钮运动和松开停止 |
| `控制小车代码/*.cmd` | 本机 Windows 双击启动入口 |
| `requirements.txt` | 当前本机环境的 Python 包版本快照 |
| `docs/开发历程.md` | 已知的开发进度、证据和待办 |
| `docs/调试记录模板.md` | 每次实车调试可复制使用的记录模板 |

## 本机运行

现有环境为 Windows、64 位 Python 3.8.8、RoboMaster SDK 0.1.1.68。
本机通过 `D:\RoboMaster` 兼容路径访问 SDK 环境，双击三个 `.cmd` 文件即可启动对应程序。

也可以在仓库根目录用 PowerShell 执行：

```powershell
# 1. 首次配网或更换网络时使用
& 'D:\RoboMaster\venv\Scripts\python.exe' -X utf8 '.\控制小车代码\01_sta_pair.py'

# 2. 检查连接并读取固件版本
& 'D:\RoboMaster\venv\Scripts\python.exe' -X utf8 '.\控制小车代码\02_sta_check.py'

# 3. 打开运动控制窗口，手动连接后操作
& 'D:\RoboMaster\venv\Scripts\python.exe' -X utf8 '.\控制小车代码\03_ep_control.py'
```

STA 模式下，电脑和小车需要接入同一网络。连接测试支持 `--local-ip` 指定电脑所用网卡的 IPv4，支持 `--sn` 选择小车。
窗口打开时不会自动连接小车；运动前请确认周围空旷，并准备使用停止按钮或空格键停止。

## 换电脑时

本仓库不包含 Python 解释器、虚拟环境、安装包和下载的完整第三方 SDK。
按 [RoboMaster 开发文档](https://robomaster-dev.readthedocs.io/zh-cn/latest/python_sdk/installs.html) 安装兼容环境，参考 `requirements.txt` 对齐依赖。
依赖清单来自当前机器，尚未在全新环境中验证安装。

当前 `.cmd` 启动器、配网临时目录以及运动控制日志目录使用 `D:\RoboMaster` 路径；换电脑时需按实际目录调整。
代码保留当前调试版本，后续可将这些路径改成配置项。

## 记录方式

每次调试后，复制调试模板记录目标、操作、现象、结论及对应提交。确认有效的结论再补入开发历程。
提交示例：`git add .`，然后 `git commit -m "记录：STA 连接调试结果"`，最后 `git push`。
本机已成功使用现有 Git 凭据推送，`main` 分支已关联远端 `origin/main`。
换电脑后需配置 Git 的 GitHub 身份验证；网页已登录不等于命令行已登录。

公开提交前不放入 Wi-Fi 密码、配网二维码、令牌、设备序列号和含私人信息的原始日志。
当前没有为自有代码选择开源许可证。
