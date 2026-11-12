# 桌边 · 旧 iPad 信息中控屏（Windows / macOS / Linux 通用版）

把吃灰的旧 iPad（如 iPad Air 1 / iPad mini 2、iOS 12+）或旧平板变成一块放在桌边的只读信息中控屏。

- **零前端构建依赖**：纯 HTML + CSS + ES5 JS（使用 `XMLHttpRequest` 与基础 Flexbox，针对 iOS 12 Safari 实机兼容优化，无需 Node.js / npm）。
- **轻量 Python 后端**：核心功能仅依赖 Python 标准库（可选 `maxminddb` 仅在开启网络流量地图定位时使用）。
- **日夜双主题 + 横竖屏自适应**：暖米纸日间 / 深海蓝夜间切换，1024×768 横屏分栏吸附，竖屏自动堆叠。
- **开箱即用 + 模块化扩展**：默认只开启人人都可用的通用模块；Docker、旁路由流量监控、Mihomo 代理监控、Navidrome 私有音乐库、快捷入口卡片均可在 `config.json` 按需打开。

---

## 一、功能模块一览

| 模块 | 默认开启 | 适用平台 / 前提条件 | 说明 |
|---|---:|---|---|
| 时钟与宿主机状态（`host`） | **是** | Windows / macOS / Linux | 磁盘剩余/总量、物理内存占用率；macOS/Linux 显示 1 分钟负载，Windows 显示 CPU 占用率 |
| AI 热点（`aihot`） | **是** | 仅需联网 | 定时缓存 AIHOT 热点榜与 24h 精选，整行防裁切轮播 |
| Readhub 热门（`readhub`） | **是** | 仅需联网 | 定时缓存科技资讯话题并滚动展示 |
| 桌面电台（`radio`） | **是** | 仅需联网 | 内置 `stations.json` 中文音乐/资讯电台，支持后台探测与 ICY 曲目解析；iPad 直连播放 |
| 在线搜歌（`music_search`） | **是** | 仅需联网 | 通过第三方目录搜索歌曲并解析直链交给同一 `<audio>` 播放 |
| Docker 容器（`docker`） | 否 | 本机 Docker 或 SSH 远程主机 | 支持 `local`（Docker Desktop / OrbStack / Linux）或 `ssh` 只读查看容器状态 |
| 旁路由流量脉动（`router`） | 否 | OpenWrt / ImmortalWrt + SSH 免密 | 采集网口 RX/TX、设备实时排行与目标地区分布图 |
| 代理核心监控（`proxy`） | 否 | Mihomo 宿主机 + SSH 免密 | 独立视图展示代理上下行、历史趋势图与目标地区分布 |
| 私有音乐库（`library`） | 否 | Navidrome（Subsonic API） | 服务端代理音频流与封面，凭据不下发浏览器，支持 WAV/APE 按需转码 MP3 |
| 快捷入口屏（`links`） | 否 | 自定义网址 | 顶栏新增切换页签，放置内网或个人常用入口卡片 |

---

## 二、5 分钟快速部署（Windows & macOS 通用）

### 前提条件
- 一台在同一局域网下的电脑（**Windows 10/11**、**macOS** 或 **Linux**）。
- 已安装 **Python 3.10+**（Windows 安装时请务必勾选 **"Add Python to PATH"**）。

### 1. 获取项目
下载或克隆本仓库到电脑任意目录，例如：
- Windows：`D:\ipad-desk-dashboard`
- macOS：`~/Projects/ipad-desk-dashboard`

### 2. 一键启动

#### macOS / Linux
在终端进入项目目录执行：
```sh
./start.sh
```
首次运行会自动完成：生成 `config.json`、创建 `.venv`、安装可选依赖，并自动打印当前局域网访问地址（如 `http://192.168.x.x:8788`）。

#### Windows
直接**双击 `start.bat`**（或在 PowerShell 中运行 `.\start.ps1`）。
首次运行会自动创建 `.venv`、生成 `config.json` 并打印你的局域网 IPv4 地址，例如：
```text
-> http://192.168.1.50:8788
```

> **Windows 防火墙提示**：首次启动时如果弹出「Windows 安全中心警报」，请勾选**「专用网络」**并点击「允许访问」。若没弹窗但 iPad 打不开，请见下方第六节放行 `8788` 端口。

### 3. iPad 端设置
1. 确保 iPad 与运行服务的电脑连接在**同一个 Wi-Fi / 局域网**。
2. 在 iPad Safari 打开终端显示的局域网地址（例如 `http://192.168.1.50:8788`）。
3. 点击 Safari 顶部/底部分享按钮 → **「添加到主屏幕」**，即可去掉浏览器地址栏全屏运行。
4. **常亮建议**：在 iPad「设置 → 显示与亮度 → 自动锁定」设为「永不」（或使用「辅助功能 → 引导式访问」锁定在桌面看板）。

---

## 三、后台静默运行与开机自启

> 仅当你希望关掉命令行窗口仍持续提供服务时配置以下方案。

### macOS（`launchd` 后台常驻）
1. 复制并修改模板：
   ```sh
   mkdir -p logs
   cp deploy/macos/com.deskboard.ipad.plist.example ~/Library/LaunchAgents/com.deskboard.ipad.plist
   ```
2. 把 `com.deskboard.ipad.plist` 中的 `/ABS/PATH/TO/ipad-desk-dashboard` 替换为你的实际目录路径。
3. 加载服务：
   ```sh
   launchctl load -w ~/Library/LaunchAgents/com.deskboard.ipad.plist
   ```
   如需停止：`launchctl unload ~/Library/LaunchAgents/com.deskboard.ipad.plist`。
   > **提示**：台式 Mac mini / 笔记本建议在「系统设置 → 能源 / 电池」关闭自动睡眠，否则休眠后会断连。

### Windows（无黑框后台自启 + 防火墙一键放行）
- **临时无黑框启动**：先运行过一次 `start.bat` 初始化环境后，以后直接双击 `deploy\windows\start-hidden.vbs` 即可在后台静默运行（无终端窗口）。
- **开机/登录自动启动**：以**管理员身份**打开 PowerShell，进入项目目录运行：
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\deploy\windows\install-task.ps1
  ```
  该脚本会注册一个名为 `iPadDeskDashboard` 的任务计划程序（使用 `pythonw.exe` 静默启动），并尝试添加 TCP `8788` 的专用网络入站放行规则。
  > **提示**：Windows 笔记本如需长期充当服务宿主机，请在电源选项中调整「接通电源时从不睡眠」。

---

## 四、配置说明（`config.json`）

首次启动会自动从 `config.example.json` 复制出 `config.json`（已加入 `.gitignore`，不会误提交个人 IP 或密码）。修改 `config.json` 后重启服务生效。

### 基础字段与功能开关

```json
{
  "site": {
    "title": "桌边控制屏",
    "subtitle": "",
    "greeting": "留一块屏，给日常。"
  },
  "server": {
    "host": "0.0.0.0",
    "port": 8788
  },
  "features": {
    "host": true,
    "aihot": true,
    "readhub": true,
    "radio": true,
    "music_search": true,
    "docker": false,
    "router": false,
    "proxy": false,
    "library": false,
    "links": false
  }
}
```
- `site.subtitle` 留空时会自动显示当前主机名与操作系统（例如 `MyPC · Windows` 或 `Mac-mini · macOS`）。
- 未开启的模块在前端会自动隐藏对应区域，**不会发起无用的接口轮询或启动后台采集线程**。
- 也可以通过环境变量覆盖：`DASHBOARD_HOST`、`DASHBOARD_PORT`、`DASHBOARD_CONFIG`、`DASHBOARD_FEATURE_DOCKER=true` 等。

### 自定义电台清单（`stations.json`）
修改根目录下的 `stations.json` 即刻生效（无需重启服务）。每条记录格式：
```json
{"id": "cnr3", "name": "音乐之声", "group": "音乐", "url": "https://ngcdn001.cnr.cn/live/yyzs/index.m3u8"}
```
- `id` 只允许字母、数字、`_`、`-`；
- `url` 仅接受公网 `http(s)` 音频流（旧版 iOS 12 支持 MP3 / AAC / HLS `.m3u8`，不支持 Ogg/Opus）。

---

## 五、进阶：Homelab 扩展配置（按需开启）

### 1. Docker 容器状态（本机或远程）
- **查看本机 Docker**（Windows Docker Desktop / macOS OrbStack / Linux）：
  ```json
  "features": { "docker": true },
  "docker": { "mode": "local", "label": "本机 Docker" }
  ```
- **通过 SSH 查看远程 Linux / PVE 容器**：
  ```json
  "features": { "docker": true },
  "docker": {
    "mode": "ssh",
    "label": "Homelab Docker",
    "ssh_host": "root@192.168.1.10",
    "admin_url": "https://192.168.1.2:8006"
  }
  ```
  要求宿主机已配置 **SSH 免密登录** 且目标主机已在 `~/.ssh/known_hosts` 中（后端强制 `BatchMode=yes` 与 `StrictHostKeyChecking=yes`）。

### 2. OpenWrt / ImmortalWrt 旁路由流量监控
1. 在旁路由确保已启用连接跟踪字节计数：`/proc/sys/net/netfilter/nf_conntrack_acct` 值为 `1`。
2. 在运行本服务的电脑配置到旁路由的 **SSH 免密登录** 并先手动 `ssh root@<旁路由IP>` 确认一次主机指纹（Windows 10/11 自带 OpenSSH 客户端，可在 PowerShell 运行 `ssh-keygen` 后把 `~/.ssh/id_ed25519.pub` 追加到路由器 `/etc/dropbear/authorized_keys`）。
3. 如需在地图上显示目标国家/地区，请自行从 Mihomo/Clash 数据目录或 MaxMind/MetaCubeX 下载离线库放到 `data/geoip.metadb`（缺失不影响速率和设备排行，仅跳过地图定位）。
4. 在 `config.json` 中开启并填写你的网段与设备别名：
   ```json
   "features": { "router": true },
   "router": {
     "ssh_host": "root@192.168.1.2",
     "interface": "eth0",
     "lan_cidr": "192.168.1.0/24",
     "aliases": {
       "192.168.1.10": "NAS",
       "192.168.1.20": "台式机"
     },
     "geoip_path": "data/geoip.metadb"
   }
   ```

### 3. Mihomo 代理核心监控
```json
"features": { "proxy": true },
"proxy": {
  "ssh_host": "root@192.168.1.10",
  "label": "Mihomo",
  "mihomo_config": "/opt/1panel/apps/mihomo/mihomo/config.yaml",
  "mihomo_api": "http://127.0.0.1:9090/connections",
  "geoip_path": "data/geoip.metadb"
}
```
后端通过 SSH stdin 运行 `remote_proxy.py`，仅回传脱敏后的地区聚合与速率计数，代理密钥不会离开远端宿主机。

### 4. Navidrome 私有音乐库
```json
"features": { "library": true },
"library": {
  "url": "http://192.168.1.10:4533",
  "user": "your_username",
  "password": "your_password",
  "hint": "点选专辑或搜索曲目。"
}
```
也可以通过环境变量 `NAVIDROME_URL`、`NAVIDROME_USER`、`NAVIDROME_PASSWORD` 传入，避免明文落盘。音频流由本机服务端代理透传（并按需转码 320kbps MP3 兼容旧 iPad），凭据不会下发浏览器。

### 5. 快捷入口页签（`links`）
```json
"features": { "links": true },
"site": {
  "links_title": "常用入口",
  "links_lead": "点击卡片在新标签打开。",
  "links": [
    {"title": "路由器后台", "desc": "ImmortalWrt 管理", "url": "http://192.168.1.1"},
    {"title": "NAS", "desc": "文件与相册", "url": "http://192.168.1.10:5000"}
  ]
}
```

### 6. Docker 容器化集中部署（适合 Homelab / NAS 7×24 运行）

仓库自带 `Dockerfile` 与 `docker-compose.example.yml`，可直接部署在一直开机的 Linux / PVE / NAS 主机上：

```sh
cp config.example.json config.json
cp docker-compose.example.yml docker-compose.yml
docker compose up -d --build
```

- 在容器内可将 `docker.mode` 设为 `"socket"`（只读挂载 `/var/run/docker.sock`），将 `proxy.mode` 设为 `"local"`（`network_mode: host` 下直连本机 Mihomo），无需再通过 SSH 绕回宿主机。

---

## 六、安全与边界

- **仅限可信局域网使用**：本面板无内置登录认证，请勿将 `8788` 端口直接映射到公网。
- **隐私与最小权限**：所有远端 SSH 采集均为只读命令；浏览器收不到公网目标 IP、代理 Secret 或 Navidrome 账号密码。
- **第三方源说明**：AIHOT 与 Readhub 仅按公开接口定时抓取展示字段；在线搜歌会向第三方公开目录发送搜索关键词，播放流由 iPad 直连 CDN，如第三方接口波动面板会如实提示错误。

---

## 七、验证与常见问题排查

### 运行自动化测试
```sh
# macOS / Linux
.venv/bin/python -m unittest discover -s tests -v

# Windows
.venv\Scripts\python.exe -m unittest discover -s tests -v
```
如本机装有 Node.js，也可校验前端严格 ES5 语法：
```sh
for f in app.js network.js ticker.js news.js readhub.js library-ui.js radio.js theme-init.js; do node --check "$f"; done
```

### 常见问题
1. **iPad 打不开 `http://<IP>:8788`？**
   - 检查电脑和 iPad 是否在同一 Wi-Fi（非访客网络 / AP 隔离）。
   - **Windows**：确认 Windows 网络配置文件为「专用网络」，并在「高级安全 Windows Defender 防火墙」允许 TCP `8788` 入站（或运行 `deploy\windows\install-task.ps1`）。
   - **macOS**：如开启了系统防火墙，请在「系统设置 → 网络 → 防火墙 → 选项」允许 `Python` 接受传入连接。
2. **刷新页面后电台没有自动继续播放？**
   - 这是 iOS Safari 安全限制：页面重新加载后必须由用户手动点击一次播放，界面会提示「点击继续播放」。
3. **老版 iPad（iOS 10/11/12）切到后台声音暂停？**
   - iOS Safari 网页音频在切出浏览器或锁屏后会暂停，建议将面板「添加到主屏幕」并保持常亮放在桌边使用。
