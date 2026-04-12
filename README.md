# 声影随行

面向亲子沟通场景的双向陪伴助手，支持聊天陪伴、图片夸夸、语音克隆朗读、心理信号分析和日报。

## 最新说明（2026-04-12）

当前版本已经拆成两个独立前端页面：

1. 孩子端：http://127.0.0.1:5173/
2. 父母端：http://127.0.0.1:5174/
3. 后端：http://127.0.0.1:8001
4. 后端文档：http://127.0.0.1:8001/docs

父母端包含心理日报、人声注册、已注册人声管理、留言箱，以及“回复设定”。“回复设定”可以勾选使用默认家长语气，也就是后端 `backend/app/main.py` 里的 `PARENT_STYLE_RULES`；取消勾选后可以输入自定义提示词，保存后孩子端后续 AI 聊天会使用这段自定义规则。设定保存到 `backend/data/parent_styles.json`。

孩子端包含 AI 聊天、图片上传、声音选择和留言箱。声音选择权在孩子端；选择“暂不使用人声”时，AI 回复不生成语音；选择已注册人声时，AI 回复会生成音频。聊天里的文字消息不会显示播放控件，只有可播放语音才显示播放控件。

留言箱是独立聊天框，孩子端和父母端都有。留言箱支持文字和麦克风录音，不支持本地上传音频文件；孩子端清空留言只影响孩子端视图，父母端清空留言只影响父母端视图。清空 AI 历史记录不会删除留言箱引用的音频文件。

场景背景图会在孩子描述“看见/看到/遇到/发现”等场景时触发。后端优先使用 DashScope 生成图片；如果远程图片生成或图链访问失败，会生成本地 `/uploads/scene_*.svg` 兜底背景，避免页面空白。

当前默认不走代理。`DASHSCOPE_TTS_PROXY_URL` 和 `DASHSCOPE_COMPATIBLE_PROXY_URL` 为空时，后端会直连 DashScope，并在调用时清理系统代理环境变量，避免本机残留代理影响请求。如果云服务器或本机必须走代理，再在 `.env` 中显式填写代理地址。

## 技术栈

1. 后端：FastAPI
2. 前端：Vue 3 + Vite
3. 存储：本地 JSON
4. 大模型与语音：DashScope（Qwen + CosyVoice）

## 当前能力

1. 双页面：孩子端 5173，父母端 5174
2. 孩子端亲子口吻 AI 聊天，自动保存当天会话
3. AI 聊天支持文字和可选图片上传
4. 孩子端选择是否使用已注册人声
5. 图片上传后生成夸夸回复
6. 场景描述触发背景图更新，支持本地兜底背景
7. 心理信号分析与父母端日报实时更新
8. 父母端声纹注册、语音列表、语音删除
9. 父母端自定义 AI 回复设定，或使用默认 `PARENT_STYLE_RULES`
10. 双端留言箱，支持文字和麦克风语音留言
11. 当天会话恢复，刷新不丢当天 AI 历史
12. AI 历史清空与留言箱清空分离

## 项目结构

1. backend：后端服务
2. frontend：前端页面
3. .gitignore：版本控制忽略规则
4. backend/data/conversations.json：对话记录
5. backend/data/analyses.json：分析记录
6. backend/data/reports.json：日报缓存
7. backend/data/uploads：上传文件与生成音频
8. backend/data/voices.json：已注册人声
9. backend/data/mailbox.json：留言箱消息
10. backend/data/mailbox_clears.json：双端留言箱清空状态
11. backend/data/parent_styles.json：父母端回复设定

## 环境要求

1. Python 3.10+
2. Node.js 18+
3. npm 9+

## 一键配置并运行（克隆后推荐）

在 Windows PowerShell 里执行：

```powershell
Set-Location "d:\声影随行"
.\scripts\bootstrap_run.ps1 -OpenBrowser
```

这个脚本会自动：

1. 检查 Python/Node/npm 是否可用
2. 若缺失则从 `backend/.env.example` 生成 `backend/.env`
3. 调用现有启动链路完成依赖安装与双前端+后端启动

首次运行后，如果提示 `DASHSCOPE_API_KEY` 未设置，请编辑 `backend/.env` 填入真实 Key。

## 首次安装（Windows）

### 1. 后端依赖

```powershell
Set-Location "d:\声影随行\backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

### 2. 前端依赖

```powershell
Set-Location "d:\声影随行\frontend"
npm install
```

## 日常启动步骤（完整）

也可以直接使用脚本一键启动（推荐）：

```powershell
Set-Location "d:\声影随行"
.\scripts\start_all.ps1
```

如需启动后自动打开孩子页和家长页，可加：

```powershell
Set-Location "d:\声影随行"
.\scripts\start_all.ps1 -OpenBrowser
```

## Docker 部署

项目已经提供 Docker 配置：

1. `backend/Dockerfile`：FastAPI 后端镜像
2. `frontend/Dockerfile`：Vue 构建 + Nginx 静态服务
3. `frontend/nginx.conf`：同源反代 `/api/` 和 `/uploads/`
4. `docker-compose.yml`：一键启动前后端

### 本地 Docker 运行

先准备后端环境变量：

```powershell
Set-Location "d:\声影随行"
Copy-Item backend\.env.example backend\.env -ErrorAction SilentlyContinue
notepad backend\.env
```

至少填写：

```env
DASHSCOPE_API_KEY=你的DashScope Key
MOCK_MODE=false
DASHSCOPE_TTS_PROXY_URL=
DASHSCOPE_COMPATIBLE_PROXY_URL=
CPOLAR_AUTO_TUNNEL=false
PUBLIC_ASSET_BASE_URL=http://localhost
```

启动：

```powershell
Set-Location "d:\声影随行"
docker compose up -d --build
```

访问：

1. 孩子端：http://localhost/
2. 父母端：http://localhost/parent
3. 后端文档：http://localhost/docs
4. 后端接口：http://localhost/api/
5. 上传资源：http://localhost/uploads/

停止：

```powershell
docker compose down
```

查看日志：

```powershell
docker compose logs -f backend
docker compose logs -f frontend
```

### 云服务器 Docker 部署

云服务器上推荐使用域名和 HTTPS。假设域名是：

```text
https://your-domain.com
```

后端 `.env` 建议：

```env
DASHSCOPE_API_KEY=你的DashScope Key
MOCK_MODE=false
DATA_DIR=/app/data
PUBLIC_ASSET_BASE_URL=https://your-domain.com
CPOLAR_AUTO_TUNNEL=false
DASHSCOPE_IGNORE_ENV_PROXY=true
DASHSCOPE_TTS_PROXY_URL=
DASHSCOPE_COMPATIBLE_PROXY_URL=
```

说明：

1. `PUBLIC_ASSET_BASE_URL` 很重要。声纹注册时 DashScope 需要公网可访问的样本音频 URL，Docker 云部署时应填你的公网域名。
2. 云服务器默认不走代理；如果直连 DashScope 失败，再填写 `DASHSCOPE_TTS_PROXY_URL` 和 `DASHSCOPE_COMPATIBLE_PROXY_URL`。
3. 当前 compose 会把后端数据放到 Docker volume `backend_data`，容器重建不会丢数据。
4. 如果服务器 80 端口已经被 Nginx/Caddy 占用，可以把 `docker-compose.yml` 里的前端端口改成 `"8080:80"`，再由宿主机 Nginx/Caddy 反代到 `127.0.0.1:8080`。

### 1. 启动后端（端口 8001）

```powershell
Set-Location "d:\声影随行\backend"
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --app-dir "d:\声影随行\backend"
```

### 2. 启动孩子端前端（5173）

```powershell
Set-Location "d:\声影随行\frontend"
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

### 3. 启动父母端前端（5174）

```powershell
Set-Location "d:\声影随行\frontend"
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

### 4. 访问地址

1. 孩子端：http://127.0.0.1:5173/
2. 父母端：http://127.0.0.1:5174/
3. 后端文档：http://127.0.0.1:8001/docs
4. 健康检查：http://127.0.0.1:8001/health

## 声音克隆流程（无公网环境）

1. 打开父母端并进入人声注册区域。
2. 输入人声名称，上传音频样本（建议 10 秒以上，单人清晰录音）。
3. 点击注册后，后端会自动：
	- 拉起 cpolar 内网穿透
	- 获取公网 URL
	- 将样本 URL 提交到 DashScope 完成声纹注册
4. 也可以直接打开麦克风录音，停止后前端会自动转成 `.wav` 再注册。
5. 注册成功后，会在“已注册人声列表”看到新 voice，孩子端声音下拉框会轮询更新。

说明：默认 `CPOLAR_KILL_EXISTING=false`，不会主动杀掉所有 cpolar 进程，避免影响已有隧道；如果明确希望启动新隧道前清理旧进程，可在 `.env` 中改成 `true`。

## 父母端回复设定

父母端有“回复设定”区域：

1. 勾选“使用默认家长语气”：使用 `backend/app/main.py` 里的 `PARENT_STYLE_RULES`。
2. 取消勾选并输入自定义提示词：孩子端后续 AI 聊天会使用自定义规则。
3. 设定保存到 `backend/data/parent_styles.json`。
4. 如果自定义规则写“像孩子的爸爸”或“自称爸爸”，后端自称规范化会倾向“爸爸”；写“妈妈”则倾向“妈妈”；默认模式使用“爸爸妈妈”。

## 代理配置

默认不走代理：

```env
DASHSCOPE_IGNORE_ENV_PROXY=true
DASHSCOPE_TTS_PROXY_URL=
DASHSCOPE_COMPATIBLE_PROXY_URL=
```

含义：

1. `DASHSCOPE_IGNORE_ENV_PROXY=true`：调用 DashScope 时忽略系统里的 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 等环境变量。
2. `DASHSCOPE_TTS_PROXY_URL`：只控制 CosyVoice TTS websocket 语音合成。留空表示直连。
3. `DASHSCOPE_COMPATIBLE_PROXY_URL`：控制文本、视觉、图片相关的 OpenAI-compatible 请求。留空表示直连。

如果云服务器上确实需要代理，可以显式配置：

```env
DASHSCOPE_TTS_PROXY_URL=http://127.0.0.1:7897
DASHSCOPE_COMPATIBLE_PROXY_URL=http://127.0.0.1:7897
```

也可以填远程代理，例如：

```env
DASHSCOPE_TTS_PROXY_URL=http://proxy.example.com:7897
DASHSCOPE_COMPATIBLE_PROXY_URL=http://proxy.example.com:7897
```

注意：只有在对应代理服务真实可用时才填写；否则语音合成可能出现 websocket 建连失败。

## 留言箱

1. 孩子端和父母端都有留言箱。
2. 支持文字留言和麦克风语音留言。
3. 不支持本地上传音频文件到留言箱。
4. 双端会轮询刷新，发送新内容后自动滚动到底部。
5. 孩子端清空留言只影响孩子端视图，父母端清空留言只影响父母端视图。

## 服务停止

优先使用脚本停止：

```powershell
Set-Location "d:\声影随行"
.\scripts\stop_all.ps1 -StopCpolar
```

其中 `-StopCpolar` 可选；不传时只停止前后端。

1. 在运行 uvicorn 的终端按 Ctrl+C
2. 在运行 Vite 的终端按 Ctrl+C

如果忘记在哪个终端启动，可用以下命令强制释放端口：

```powershell
$p = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess
if ($p) { Stop-Process -Id $p -Force }

$p2 = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess
if ($p2) { Stop-Process -Id $p2 -Force }

$p3 = Get-NetTCPConnection -LocalPort 5174 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess
if ($p3) { Stop-Process -Id $p3 -Force }
```

## 清空行为与确认弹窗

前端对以下操作统一采用应用内二次确认弹窗：

1. 清空历史记录：文案为“确定要清空历史记录吗？”
2. 清空留言：文案为“确定要清空留言吗？”

确认后才会调用对应接口执行清空。

### 清空历史记录接口行为

前端点击“清空历史记录”会调用 `POST /api/history/reset`，并执行：

1. 清空 `conversations`、`analyses`、`reports`
2. 删除 AI 聊天、图片夸夸、人声合成等相关上传/生成文件
3. 保留留言箱引用的语音文件，避免留言箱播放失效

## 环境变量（backend/.env）

核心项如下：

1. DASHSCOPE_API_KEY：DashScope API Key
2. DASHSCOPE_TEXT_MODEL：默认 qwen3.5-flash
3. DASHSCOPE_VISION_MODEL：默认 qwen3-vl-flash
4. DASHSCOPE_TTS_MODEL：默认 cosyvoice-v3.5-flash
5. DASHSCOPE_TTS_INSTRUCTION：朗读风格指令
6. DASHSCOPE_TTS_SEED：语音稳定随机种子
7. DASHSCOPE_TTS_RETRY_ATTEMPTS：语音失败重试次数
8. DASHSCOPE_TTS_MIN_AUDIO_BYTES：最小音频体积阈值
9. DASHSCOPE_TTS_PROXY_URL：TTS websocket 代理地址，默认空，表示不走代理
10. DASHSCOPE_COMPATIBLE_PROXY_URL：文本/视觉 OpenAI-compatible 请求代理地址，默认空，表示不走代理
11. DASHSCOPE_VOICE_PREFIX：声纹 ID 前缀
12. PUBLIC_ASSET_BASE_URL：部署公网地址（已配置时优先使用）
13. CPOLAR_AUTO_TUNNEL：未配置 PUBLIC_ASSET_BASE_URL 时是否自动拉起 cpolar（默认 true）
14. CPOLAR_KILL_EXISTING：启动新隧道前是否自动清理旧 cpolar 进程（默认 false）
15. CPOLAR_PATH：cpolar 可执行文件路径
16. CPOLAR_START_TIMEOUT_SEC：等待 cpolar 返回公网地址的超时时间（秒）
17. PARENT_PERSONA：基础家长人格设定
18. MOCK_MODE：false 为真实调用，true 为本地兜底
19. DATA_DIR：数据目录，默认 ./data

## API 概览

1. POST /api/chat：聊天回复（可选心理分析/场景图）
2. POST /api/praise-image：图片夸夸
3. GET /api/report/daily：每日心理日报
4. POST /api/voice/enroll：注册声纹
5. GET /api/voice/list：获取已注册人声列表
6. DELETE /api/voice/{voice_id}：删除指定人声
7. POST /api/voice/synthesize：文本转语音
8. GET /api/conversations/today：获取当天会话
9. POST /api/history/reset：清空历史数据
10. GET /api/mailbox：获取留言箱
11. POST /api/mailbox：发送留言
12. POST /api/mailbox/clear：清空当前端留言视图
13. GET /api/parent-style：获取父母端回复设定
14. POST /api/parent-style：保存父母端回复设定

## 常见问题

1. 后端无法启动：先检查 8001 是否被占用，再重启。
2. 前端端口：孩子端固定 5173，父母端固定 5174；如果端口被占用，先运行 `scripts/stop_all.ps1` 再启动。
3. 声纹注册失败：通常是 cpolar 未启动成功、样本 URL 无法公网访问，或音频质量不足。
4. 视觉或语音偶发失败：优先检查 DashScope 配额、限流和模型开通状态；如果你显式配置了代理，再检查代理是否可用。
5. 若报错包含 `ERR_CPOLAR_108`：表示 cpolar 会话超限，重试一次即可（后端会自动清理旧会话）。
6. 回复没有声音：先看 `backend/uvicorn.err.log` 是否有 TTS websocket 失败；也可以用 `POST /api/voice/synthesize` 单独测试人声。
7. 背景图没有出现：检查 `/api/chat` 返回里是否有 `scene_image_url`；远程图失败时后端会返回本地 SVG 兜底。
8. 自定义爸爸/妈妈语气不生效：确认父母端没有勾选“使用默认家长语气”，并点击保存设定。
9. 云服务器部署：国内云服务器建议先保持代理为空直连 DashScope；只有直连失败时再配置代理。

## 安全建议

1. 不要提交真实 .env 到仓库
2. API Key 泄漏后立即在平台旋转
