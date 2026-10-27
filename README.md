# Decomposer

把科研图片重建成**可编辑的单页 PowerPoint**。配置视觉模型 API 后，一条命令启动，浏览器上传图片即可下载 PPTX 和预览。

## 快速部署（推荐 Docker）

需要 Git、Docker 和 Docker Compose。私有仓库需先获得仓库访问权限。

```bash
git clone https://github.com/goya4140/Decomposer.git
cd Decomposer
cp .env.example .env
```

在 `.env` 中填写三项：

```dotenv
DECOMPOSER_BASE_URL=https://your-provider.example/v1
DECOMPOSER_API_KEY=your-api-key
DECOMPOSER_MODEL=your-vision-model
```

模型接口需要支持图片输入和 Chat Completions。地址填写 API 根路径，程序会追加 `/chat/completions`。默认使用 `json_schema` 结构化输出；如果服务商只支持 JSON 模式，将 `DECOMPOSER_RESPONSE_MODE` 改为 `json_object`。`prompt_only` 供不支持这两种模式的兼容接口使用，输出仍会校验。

```bash
./deploy.sh --docker
```

打开 **http://127.0.0.1:7860**，上传图片、等待转换、下载 PPTX。首次启动会构建镜像并安装 OCR、字体和渲染器。

```bash
docker compose logs -f       # 查看启动/运行状态
docker compose down          # 停止服务，保留结果
docker compose up -d         # 再次启动
```

结果保存在 Docker 的 `decomposer-data` 数据卷中。浏览器刷新后可查看上次任务；`docker compose down -v` 会删除数据。

## 本机启动

安装 Python 3.12–3.13、Node.js 20+、LibreOffice、Poppler 和 Tesseract 后，配置同一份 `.env`：

```bash
./deploy.sh
```

脚本会建立虚拟环境、安装锁定的依赖并启动服务。macOS 上缺少系统依赖时，会通过已安装的 Homebrew 安装。Linux 建议直接使用上面的 Docker 方式。

Ubuntu/Debian 的系统组件可用以下命令安装，Node.js 需另行安装 20 或更新版本：

```bash
sudo apt-get update
sudo apt-get install -y libreoffice-impress poppler-utils tesseract-ocr \
  fonts-liberation fonts-dejavu-core fonts-noto-cjk
```

本机运行结果在 `data/jobs/`。停止前请等待当前任务完成；意外中断的任务会标记失败，重新上传即可。转换串行执行，最多接收 8 个正在处理或等待的任务。

## 使用

- 支持 PNG、JPEG、WebP、TIFF、BMP；最大 20 MiB、2500 万像素，TIFF 使用第一页。
- 一张输入图生成一页 PPTX，包含原生文字、形状、连线和允许保留的局部图片素材。
- 默认进行一轮模型修复，并保留必要时的有界追加修复。可以在 `.env` 中设置 `DECOMPOSER_REFINEMENT_ROUNDS=0` 关闭模型修复。
- PPTX 生成成功但视觉相似度未达到阈值时，界面会明确提示。复杂图、小字、公式和特殊字体请检查预览。
- 输入图片会发送给配置的模型服务商。API 密钥仅从环境读取；`.env`、上传文件和生成结果不会进入 Git。

仓库附带 `examples/example.png`，可直接上传试用。也可在本机使用命令行：

```bash
.venv/bin/python run.py --input examples/example.png --out data/example
```

输出为 `data/example/output/editable.pptx` 和 `preview.png`。每次转换应使用新的输出目录。

## 可选配置

| 变量 | 默认值 | 用途 |
|---|---|---|
| `DECOMPOSER_RESPONSE_MODE` | `json_schema` | `json_schema` / `json_object` / `prompt_only` |
| `DECOMPOSER_REASONING_EFFORT` | 空 | 仅在模型支持时设置 |
| `DECOMPOSER_API_TIMEOUT` | `900` | 每次模型请求超时秒数 |
| `DECOMPOSER_REFINEMENT_ROUNDS` | `1` | 模型修复轮数，范围 0–3 |
| `DECOMPOSER_OCR_LANG` | `eng` | Tesseract 语言，例如 `eng+chi_sim` |
| `DECOMPOSER_ACCESS_TOKEN` | 空 | 可选的浏览器/API 访问令牌 |
| `DECOMPOSER_HOST` | `127.0.0.1` | 本机监听地址 |
| `DECOMPOSER_PORT` | `7860` | 本机监听端口 |

Docker 镜像包含英文与简体中文 OCR。其他语言需在镜像中安装对应 Tesseract 语言包；本机也需安装所选语言包。字体影响文字测量和渲染：镜像提供 Liberation、DejaVu 和 Noto CJK；需要特殊字体时，在自定义镜像内安装有权使用的字体。

Compose 默认只向本机开放端口。远程使用可通过 SSH 端口转发：

```bash
ssh -L 7860:127.0.0.1:7860 user@your-host
```

若自行改为对外开放，请设置 `DECOMPOSER_ACCESS_TOKEN`，并由反向代理提供 HTTPS。访问令牌在页面的“访问令牌”处输入。

## 接口

同一个服务提供：

- `POST /api/jobs`：multipart 文件字段 `file`，返回任务 ID。
- `GET /api/jobs/{id}`：查询排队、阶段、成功或失败状态。
- `GET /api/jobs/{id}/pptx`：下载 PPTX。
- `GET /api/jobs/{id}/preview`：下载 PNG 预览。
- `GET /healthz`：健康检查。

配置了访问令牌时，除首页和健康检查外，请求需带 `Authorization: Bearer <token>`。

## 代码

`decomposer/` 是优化后的重建流程：Recognition、原生对象构建计划、确定性 Composition、字体测量校准、有接受/回滚检查的局部 Refinement，以及修复阶段使用的 memory/skill。

部署版实时处理新图片，使用随环境安装的本地 Tesseract OCR。默认不启用 SAM，不依赖远程检测服务器、旧实验缓存或论文数据；局部素材由视觉识别结果和素材策略共同决定。这里的预处理与使用历史 SAM/OCR 缓存的研究运行不同，不承诺逐像素复现历史结果。

目录只包含运行代码、提示词、默认配置、精简的修复知识、部署文件、示例和运行回归测试。没有论文、benchmark、服务器配置或历史实验产物。

开发验证：

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

完整烟测通过本地模拟视觉 API 实际执行 OCR、最新重建流程、Node 编译、LibreOffice 渲染、上传和下载，不消耗模型 API 额度。真实模型的兼容性和输出质量取决于配置的服务商。
