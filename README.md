# 声影随行 Voice Shadow

《声影随行》是一款面向留守儿童与父母的双端陪伴系统。项目包含孩子端和父母端两个前端页面，孩子端用于日常表达与 AI 陪伴互动，父母端用于查看心理日报、注册父母人声、设置回复语气和处理留言。

系统结合阿里云 DashScope 的文本理解、图像理解、图像生成、语音合成和声纹注册能力，目标是让孩子在远程场景中获得更自然的陪伴感，同时帮助父母及时了解孩子的情绪线索。

## 主要功能

- 孩子端 AI 聊天
- 孩子端文字输入和图片上传
- 孩子端选择父母人声或暂不使用人声
- AI 回复可生成语音并播放
- 父母端心理日报
- 父母端人声注册和人声管理
- 父母端自定义 AI 回复语气
- 双端留言箱
- 留言、对话、日报、人声和上传资源持久化
- Docker 云服务器部署

## 技术栈

- 前端：Vue 3、Vite、TypeScript、Nginx
- 后端：Python、FastAPI、Uvicorn、Pydantic
- 数据存储：本地 JSON 文件和上传资源目录
- 部署：Docker、Docker Compose
- 模型服务：阿里云 DashScope

使用到的 DashScope 模型：

- `qwen3.5-flash`：文本对话
- `qwen3-vl-flash`：图像理解
- `wan2.7-image`：图像生成
- `cosyvoice-v3.5-flash`：声纹注册与语音合成

说明：Vite 主要用于本地开发和前端构建。云服务器 Docker 部署时，Vite 会在镜像构建阶段执行 `npm run build`，生成静态前端文件；真正对外提供页面服务的是前端容器里的 Nginx，不是 Vite dev server。远程仓库默认按云服务器部署版维护，本地 Vite 代理配置只作为开发说明，不要求提交到远程仓库。

## 项目结构

```text
Voice-Shadow/
├─ backend/
│  ├─ app/                    # FastAPI 后端代码
│  ├─ data/                   # 本地数据目录
│  │  └─ uploads/             # 上传文件和生成音频
│  ├─ Dockerfile
│  ├─ requirements.txt
│  └─ .env.example
├─ frontend/
│  ├─ src/                    # Vue 前端源码
│  ├─ Dockerfile
│  ├─ nginx.conf              # Docker 前端 Nginx 反代配置
│  ├─ package.json
│  └─ vite.config.ts
├─ scripts/                   # 本地启动和停止脚本
├─ docker-compose.yml
└─ README.md
```

## 云服务器部署

以下步骤以 Ubuntu 22.04 云服务器为例。推荐优先使用 Docker Compose 部署。

### 1. 开放安全组端口

在云服务器安全组中放行：

```text
TCP 22    SSH 登录
TCP 80    Web 页面访问
TCP 8001  后端接口调试，可选
```

正常使用页面时只需要访问 80 端口；`8001` 主要用于调试。

### 2. 安装 Docker、Docker Compose 和 Git

```bash
apt update
apt install -y docker.io docker-compose git
systemctl enable docker
systemctl start docker
```

检查安装：

```bash
docker --version
docker-compose --version
```

### 3. 拉取项目

```bash
cd /opt
git clone https://github.com/HNUwzj/Voice-Shadow.git
cd Voice-Shadow
```

### 4. 配置环境变量

复制环境变量模板：

```bash
cp backend/.env.example backend/.env
nano backend/.env
```

至少需要填写：

```env
DASHSCOPE_API_KEY=你的DashScope API Key
DASHSCOPE_BASE_HTTP_API_URL=https://dashscope.aliyuncs.com/api/v1
DASHSCOPE_IGNORE_ENV_PROXY=true
DASHSCOPE_TTS_PROXY_URL=
DASHSCOPE_COMPATIBLE_PROXY_URL=
DASHSCOPE_IMAGE_MODEL=wan2.7-image
DASHSCOPE_IMAGE_SIZE=2K
MOCK_MODE=false
PUBLIC_ASSET_BASE_URL=http://你的服务器公网IP
CPOLAR_AUTO_TUNNEL=false
```

例如服务器公网 IP 是 `8.163.84.168`：

```env
PUBLIC_ASSET_BASE_URL=http://8.163.84.168
```

`PUBLIC_ASSET_BASE_URL` 用于生成公网可访问的上传资源地址。声纹注册时，DashScope 需要通过这个地址下载人声音频样本，因此它必须是外部可以访问的地址。

不要把真实的 `DASHSCOPE_API_KEY` 提交到 GitHub。

### 5. 启动服务

云服务器运行时不需要单独启动 Vite。前端构建会在 Docker 镜像中完成，运行阶段由 Nginx 提供静态页面，并把 `/api/` 和 `/uploads/` 反向代理到后端。

```bash
docker-compose up -d --build
```

查看容器状态：

```bash
docker-compose ps
```

正常情况下应看到：

```text
voice-shadow_backend_1    Up    0.0.0.0:8001->8001/tcp
voice-shadow_frontend_1   Up    0.0.0.0:80->80/tcp
```

### 6. 验证服务

在服务器执行：

```bash
curl -I http://127.0.0.1/
curl "http://127.0.0.1/api/voice/list?child_id=default-child"
curl "http://127.0.0.1/api/report/daily?child_id=default-child"
```

如果首页返回 `200 OK`，接口返回 JSON，说明服务已经启动成功。

### 7. 访问地址

使用公网 IP 访问：

```text
孩子端：http://服务器公网IP/
父母端：http://服务器公网IP/parent
```

例如：

```text
孩子端：http://8.163.84.168/
父母端：http://8.163.84.168/parent
```

前端容器中的 Nginx 会把 `/api/` 和 `/uploads/` 自动反向代理到后端容器。

## 更新部署

服务器上拉取最新代码并重建：

```bash
cd /opt/Voice-Shadow
git pull
docker-compose up -d --build
```

查看日志：

```bash
docker-compose logs --tail=100 backend
docker-compose logs --tail=100 frontend
```

持续查看日志：

```bash
docker-compose logs -f backend
docker-compose logs -f frontend
```

停止服务：

```bash
docker-compose down
```

注意：`docker-compose down` 不会删除数据卷；`docker-compose down -v` 会删除后端数据卷，聊天记录、人声、上传文件和日报都会丢失。

## 从头清理服务器部署

如果需要彻底删除旧部署并重新开始：

```bash
cd /opt/Voice-Shadow 2>/dev/null || true
docker-compose down -v --remove-orphans 2>/dev/null || true
docker rm -f voice-shadow_backend_1 voice-shadow_frontend_1 voice-shadow_caddy_1 2>/dev/null || true
docker volume rm voice-shadow_backend_data voice-shadow_caddy_data voice-shadow_caddy_config 2>/dev/null || true
cd /opt
rm -rf /opt/Voice-Shadow
```

然后重新执行“拉取项目”之后的部署步骤。

## docker-compose 兼容问题

部分 Ubuntu 源里的 `docker-compose 1.29.2` 在重建容器时可能出现：

```text
KeyError: 'ContainerConfig'
```

通常是旧容器元数据兼容问题。可以先查看残留容器：

```bash
docker ps -a
```

然后删除报错相关的旧容器：

```bash
docker rm -f 旧容器名
docker-compose up -d
```

如果容器名带随机前缀，例如：

```text
e1bbb3d954fe_voice-shadow_frontend_1
```

就删除实际显示的完整容器名。

## 公网访问和麦克风说明

当前部署可以直接使用公网 IP + HTTP 访问页面：

```text
http://服务器公网IP/
http://服务器公网IP/parent
```

已有语音播放不依赖 HTTPS，可以正常播放。但浏览器对麦克风权限有安全限制，公网 HTTP 页面可能无法稳定使用麦克风录音。

如果需要稳定使用麦克风，建议后续配置：

```text
域名 + HTTPS 证书 + 反向代理
```

如果浏览器自动把 `http://服务器公网IP/` 改成 `https://服务器公网IP/`，会导致 SSL 错误。可以尝试：

- 确认地址栏输入的是 `http://`
- 使用无痕窗口
- 换浏览器
- 清理该 IP 的站点缓存

## 本地开发

本地开发需要：

- Python 3.11
- Node.js 18+
- npm

安装后端依赖：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

安装前端依赖：

```powershell
cd ..\frontend
npm install
```

启动本地服务：

```powershell
cd ..
.\scripts\start_all.ps1
```

本地访问：

```text
孩子端：http://127.0.0.1:5173/
父母端：http://127.0.0.1:5174/
后端文档：http://127.0.0.1:8001/docs
```

本地 Vite 开发服务器需要把 `/api` 和 `/uploads` 代理到后端 `8001`。如果本地前端接口失败，可以在本机的 `frontend/vite.config.ts` 中加入下面的开发代理配置：

```ts
proxy: {
  '/api': 'http://127.0.0.1:8001',
  '/uploads': 'http://127.0.0.1:8001'
}
```

这段配置只用于本地开发。云服务器部署版依赖 `frontend/nginx.conf` 做反向代理，因此远程仓库可以不提交本地 Vite 代理改动。

停止本地服务：

```powershell
.\scripts\stop_all.ps1
```

## 数据文件

后端默认使用 JSON 文件保存数据：

```text
backend/data/conversations.json    AI 对话记录
backend/data/analyses.json         心理分析记录
backend/data/reports.json          日报缓存
backend/data/voices.json           已注册人声
backend/data/mailbox.json          留言箱消息
backend/data/mailbox_clears.json   双端留言清空状态
backend/data/parent_styles.json    父母端回复设定
backend/data/uploads/              上传文件和生成音频
```

Docker 部署时，后端数据目录映射到 Docker volume `backend_data`，容器重建不会丢失数据。

## 常见问题

### 1. 不填 API Key 会怎样？

如果没有配置 `DASHSCOPE_API_KEY`，后端会进入 mock 模式。普通聊天会返回模板回复，但图片理解、人声注册和语音合成不能正常使用。

### 2. 声纹注册失败怎么办？

先检查：

- `DASHSCOPE_API_KEY` 是否正确
- `MOCK_MODE=false`
- `PUBLIC_ASSET_BASE_URL` 是否是公网可访问地址
- 服务器 80 端口是否开放
- 上传音频是否为可用 `.wav` 样本

可以在服务器测试上传资源访问：

```bash
curl -I http://服务器公网IP/uploads/文件名.wav
```

### 3. 前端能打开，但接口失败怎么办？

在服务器测试：

```bash
curl "http://127.0.0.1/api/voice/list?child_id=default-child"
docker-compose logs --tail=100 backend
docker-compose logs --tail=100 frontend
```

如果本机可以访问但浏览器不行，检查浏览器是否强制升级到 HTTPS，或是否有代理/VPN 干扰。

### 4. 前端更新后浏览器还是旧效果怎么办？

可以强制刷新页面，或临时加查询参数：

```text
http://服务器公网IP/?v=2
http://服务器公网IP/parent?v=2
```

新用户首次访问一般会直接加载服务器上的最新前端文件。

## 开源组件说明

本项目使用 Vue 3、Vite、TypeScript、FastAPI、Uvicorn、Pydantic、python-dotenv、python-multipart、OpenAI Python SDK、DashScope SDK、Nginx、Docker 等开源组件作为基础开发与部署依赖。项目调用的阿里云 DashScope 模型服务属于外部云服务能力，不作为项目内置开源代码。
