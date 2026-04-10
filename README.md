# 声影随行

面向亲子沟通场景的双向陪伴助手，支持聊天陪伴、图片夸夸、语音克隆朗读、心理信号分析和日报。

## 技术栈

1. 后端：FastAPI
2. 前端：Vue 3 + Vite
3. 存储：本地 JSON
4. 大模型与语音：DashScope（Qwen + CosyVoice）

## 当前能力

1. 亲子口吻聊天（自动保存会话）
2. 图片上传后生成夸夸回复
3. 心理信号分析与日报统计
4. 声纹注册、语音列表、语音删除
5. 助手回复自动朗读（返回音频 URL，前端自动播放）
6. 当天会话恢复（刷新不丢当天历史）
7. 一键清空历史与日报

## 项目结构

1. backend：后端服务
2. frontend：前端页面
3. .gitignore：版本控制忽略规则
4. backend/data/conversations.json：对话记录
5. backend/data/analyses.json：分析记录
6. backend/data/reports.json：日报缓存
7. backend/data/uploads：上传文件与生成音频

## 环境要求

1. Python 3.10+
2. Node.js 18+
3. npm 9+

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

### 1. 启动后端（端口 8001）

```powershell
Set-Location "d:\声影随行\backend"
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --app-dir "d:\声影随行\backend"
```

### 2. 启动前端（优先 5173）

```powershell
Set-Location "d:\声影随行\frontend"
npm run dev -- --host 0.0.0.0 --port 5173
```

说明：如果 5173 被占用，Vite 会自动切到 5174 或更高端口，请以终端输出为准。

### 3. 访问地址

1. 前端：http://127.0.0.1:5173（或终端显示的实际端口）
2. 后端文档：http://127.0.0.1:8001/docs
3. 健康检查：http://127.0.0.1:8001/health

## 声音克隆流程（无公网环境）

1. 打开前端并进入人声注册区域。
2. 输入人声名称，上传音频样本（建议 10 秒以上，单人清晰录音）。
3. 点击注册后，后端会自动：
	- 拉起 cpolar 内网穿透
	- 获取公网 URL
	- 将样本 URL 提交到 DashScope 完成声纹注册
4. 注册成功后，会在“已注册人声列表”看到新 voice。

说明：若 cpolar 旧会话占满，后端会自动清理旧 cpolar 进程后重试。

## 服务停止

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

## 删除历史行为

前端点击“删除历史记录”会调用 `POST /api/history/reset`，并执行：

1. 清空 `conversations`、`analyses`、`reports`
2. 清空 `backend/data/uploads` 目录内容（保留目录本身）

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
9. DASHSCOPE_VOICE_PREFIX：声纹 ID 前缀
10. PUBLIC_ASSET_BASE_URL：部署公网地址（已配置时优先使用）
11. CPOLAR_AUTO_TUNNEL：未配置 PUBLIC_ASSET_BASE_URL 时是否自动拉起 cpolar（默认 true）
12. CPOLAR_KILL_EXISTING：启动新隧道前是否自动清理旧 cpolar 进程（默认 true）
13. CPOLAR_PATH：cpolar 可执行文件路径
14. CPOLAR_START_TIMEOUT_SEC：等待 cpolar 返回公网地址的超时时间（秒）
15. MOCK_MODE：false 为真实调用，true 为本地兜底
16. DATA_DIR：数据目录，默认 ./data

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

## 常见问题

1. 后端无法启动：先检查 8001 是否被占用，再重启。
2. 前端端口变化：5173 被占用时自动切 5174，属正常行为。
3. 声纹注册失败：通常是 cpolar 未启动成功、样本 URL 无法公网访问，或音频质量不足。
4. 视觉或语音偶发失败：优先检查 DashScope 配额、限流和模型开通状态。
5. 若报错包含 `ERR_CPOLAR_108`：表示 cpolar 会话超限，重试一次即可（后端会自动清理旧会话）。

## 安全建议

1. 不要提交真实 .env 到仓库
2. API Key 泄漏后立即在平台旋转