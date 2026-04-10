# 声影随行

一个面向亲子沟通场景的双向陪伴助手，包含聊天陪伴、心理风险侧写、图片夸夸和日报能力。

当前版本技术栈：

1. 后端：FastAPI
2. 前端：Vue 3 + Vite
3. 数据存储：本地 JSON 文件

## 核心能力

1. 亲子风格聊天
2. 心理信号识别（自卑、被欺凌、孤独、陪伴需求）
3. 图片上传夸夸（多模态）
4. 每日心理日报汇总
5. 一键删除历史记录并重置日报
6. 背景图仅在识别到“看到/看见/遇到”等场景描述时切换

## 项目结构

1. backend：后端服务
2. frontend：前端页面
3. backend/data：本地数据目录
4. backend/data/conversations.json：对话记录
5. backend/data/analyses.json：心理分析记录
6. backend/data/reports.json：日报缓存记录
7. backend/data/uploads：上传图片

## 环境要求

1. Python 3.10+
2. Node.js 18+
3. npm 9+

## 快速启动（Windows）

### 1. 启动后端

```powershell
Set-Location "d:\声影随行\backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

可选依赖（启用 DashScope 文生图时建议安装）：

```powershell
pip install dashscope
```

启动服务（当前项目默认使用 8001 端口）：

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --app-dir "d:\声影随行\backend"
```

### 2. 启动前端

```powershell
Set-Location "d:\声影随行\frontend"
npm install
npm run dev
```

访问地址：

1. 前端：http://127.0.0.1:5173
2. 后端文档：http://127.0.0.1:8001/docs
3. 健康检查：http://127.0.0.1:8001/health

## 环境变量说明

配置文件路径：backend/.env

常用项：

1. DASHSCOPE_API_KEY：阿里云 DashScope Key（用于文本、视觉理解与场景图）
2. DASHSCOPE_COMPATIBLE_BASE_URL：默认 https://dashscope.aliyuncs.com/compatible-mode/v1
3. DASHSCOPE_TEXT_MODEL：默认 qwen3.5-flash
4. DASHSCOPE_VISION_MODEL：默认 qwen3-vl-flash
5. DASHSCOPE_ENABLE_THINKING：默认 false
6. MOCK_MODE：true 为本地兜底，false 为真实模型调用
7. DATA_DIR：数据目录，默认 ./data

## API 概览

### 1. 聊天

1. 路径：POST /api/chat
2. 用途：聊天回复 + 可选心理分析 + 可选场景图

请求示例：

```json
{
	"child_id": "default-child",
	"message": "今天我看见一只小狗",
	"enable_scene": true,
	"enable_psych_analysis": true
}
```

### 2. 图片夸夸

1. 路径：POST /api/praise-image
2. 用途：上传图片并生成夸夸文案

### 3. 日报

1. 路径：GET /api/report/daily?child_id=default-child
2. 用途：返回当天消息数、心理指标均值与建议

### 4. 重置历史

1. 路径：POST /api/history/reset
2. 用途：清空 conversations、analyses、reports

## 数据与重置说明

点击前端“删除历史记录”后会：

1. 调用 /api/history/reset
2. 清空后端 JSON 数据
3. 聊天与日报展示回到初始状态

## 常见问题排查

### 1. 前端无法启动，提示找不到 package.json

原因：在项目根目录执行了 npm run dev。

解决：

```powershell
npm --prefix "d:\声影随行\frontend" run dev
```

### 2. 后端 500，提示 Unexpected UTF-8 BOM

原因：JSON 文件编码包含 BOM。

当前代码已兼容 utf-8-sig 读取。如果仍异常，可手工把 data 下 JSON 改为无 BOM UTF-8。

### 3. DashScope 视觉失败，提示配额或限流

常见报错：429 / ResourceExhausted。

含义：模型配额不足或触发短时速率限制。

建议：

1. 稍后重试（等待 retry_delay）
2. 在 DashScope 控制台检查套餐与配额
3. 确认模型开通（如 qwen3-vl-flash）或启用付费计划
4. 必要时切回 MOCK_MODE=true 保障演示稳定

### 4. 背景图切换不符合预期

当前逻辑：仅在输入中识别到“看到/看见/见到/遇到/发现”等场景描述时切换。

## 安全建议

1. 不要把真实 API Key 提交到仓库
2. 如果 Key 在日志或截图中泄漏，请立即在平台旋转（重置）
3. 建议把 .env 加入版本控制忽略

## 版本备注

当前 README 对齐了本地实现与运行端口（8001 + 5173），如后续改动接口或模型配置，请同步更新本文档。