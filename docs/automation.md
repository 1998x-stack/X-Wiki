# 自动化与恢复

## 执行链

`scripts/install_launch_agent.py` 安装用户级 launchd 服务。服务有三种触发来源：

1. Voice Memos 本地目录发生变化。
2. Mac 醒着时每隔 `XWIKI_SCAN_INTERVAL_SECONDS` 扫描一次。
3. 日历事件在睡眠期间被错过后，由 launchd 在唤醒时合并补跑。

处理器先等待音频静置，再校验前后文件大小和修改时间。每条录音独立转写，单个损坏
文件不会阻塞后续录音，但本次进程会返回失败状态。SQLite 状态库和进程锁保证扫描
幂等，避免并发重复处理。

## 睡眠语义

Mac 睡眠时，不能可靠保证 Voice Memos 继续从 iCloud 下载，也不能保证目录事件或
Python 脚本即时执行。该服务不会主动唤醒 Mac。

实际恢复路径是：Mac 唤醒并联网后，iCloud 继续同步；目录监听捕捉新文件。即使目录
事件被系统合并或丢失，日历补偿任务和下一次五分钟扫描仍会从 SQLite 状态继续处理。
因此目标是“唤醒后最终同步”，不是“睡眠中实时同步”。

Apple 说明 Voice Memos 会在开启 iCloud 后自动出现在同一 Apple Account 的设备上，
但未承诺录音会在深度睡眠期间即时落盘。Apple 的 launchd 文档说明，睡眠期间错过的
`StartCalendarInterval` 会在唤醒后执行，而其他定时任务可能被跳过：

- [在所有 Apple 设备上查看录音](https://support.apple.com/en-euro/guide/voice-memos/vma6cc4d0571/mac)
- [Apple launchd 定时任务与睡眠语义](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/ScheduledJobs.html)

## 保护边界

- 音频、转写缓存、状态数据库和 `raw/voice/` 不进入 Git。
- Raw 文件已存在且内容变化时创建 revision，绝不覆盖原证据。
- `wiki/`、`index.md` 或 `log.md` 有人工未提交修改时，自动编译以退出码 75 暂停。
- 编译或推送发生瞬时失败也以退出码 75 暂停（如 pi 超时、Mac 在编译中途睡眠、
  网络抖动），源保持 `raw_ready`/`publish_pending`，下一轮扫描自动重试。
- pi 只能修改知识层；脚本在调用前后校验 raw 哈希和 Git 变更边界，忽略缓存与
  代理状态目录（`.codegraph`、`.pytest_cache`、`.ruff_cache`、`.omo`、
  `.workbuddy-ai`、`__pycache__`、`.env`、`.DS_Store`）。
- 自动 Git 操作只暂存 `wiki/`、`index.md` 和 `log.md`，不会提交其他工作文件。
- 只有本轮编译或明确的 `publish_pending` 状态才会触发自动提交；普通手工编辑不会被提交。
- 推送失败后保留 `publish_pending` 状态，下一轮会再次尝试推送。

## 运维

```bash
# 安装或刷新服务
.venv/bin/python scripts/install_launch_agent.py

# 查看服务
launchctl print gui/$(id -u)/com.xwiki.voice-ingest

# 查看日志
tail -n 100 .state/logs/launchd.err.log
tail -n 100 .state/logs/launchd.out.log

# 卸载服务
.venv/bin/python scripts/install_launch_agent.py --remove
```

首次运行建议设置 `XWIKI_GIT_PUSH=false`，先用 `doctor.py` 和
`process_voice_memos.py --skip-push` 验证本地链路，再打开自动推送。
