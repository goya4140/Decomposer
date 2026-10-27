# Decomposer

[English](README.md) | 简体中文

## Docker 启动

安装 Git、Docker 和 Docker Compose，然后执行：

```bash
git clone https://github.com/goya4140/Decomposer.git
cd Decomposer
cp .env.example .env
```

在 `.env` 中填写支持图片输入的模型 API：

```dotenv
DECOMPOSER_BASE_URL=https://your-provider.example/v1
DECOMPOSER_API_KEY=your-api-key
DECOMPOSER_MODEL=your-vision-model
```

API 地址不要包含 `/chat/completions`。如果服务商不支持 `json_schema`，设置 `DECOMPOSER_RESPONSE_MODE=json_object`。

启动：

```bash
./deploy.sh --docker
```

打开 [http://127.0.0.1:7860](http://127.0.0.1:7860)。

## 本机启动

安装 Python 3.12–3.13、Node.js 20+、LibreOffice、Poppler 和 Tesseract。按上面的方法配置 `.env`，然后执行：

```bash
./deploy.sh
```

打开 [http://127.0.0.1:7860](http://127.0.0.1:7860)。
