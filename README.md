# chfs-py

**Lightweight file server similar to CuteHttpFileServer/chfs, built with FastAPI + Uvicorn + WebDAV**

一个功能类似 CuteHttpFileServer/chfs 的轻量文件服务器，基于 **FastAPI + Uvicorn**（主站 UI & REST）+ **WsgiDAV**（/webdav）技术栈，配置使用 **YAML**，支持打包为单个 EXE 文件。

## ✨ Features / 功能特性

### 核心功能
- 🌐 **Web 文件管理**: 列表、上传（multipart）、删除、重命名、新建目录、批量操作
- 🔐 **认证与授权**: Basic Auth + 基于规则的权限控制（R/W/D）
- 📁 **内置 WebDAV**: 挂载路径 `/webdav`，与主站共享权限系统
- ⚙️ **YAML 配置**: 监听地址/端口、TLS、共享根目录、日志、限速/并发、IP 过滤
- 📱 **响应式 UI**: 原生 HTML + Tailwind CDN，移动端友好
- 🔗 **文本快速分享**: 生成短链 `/t/<id>` 用于文本分享
- 🚀 **Windows 兼容**: 正确处理反斜杠与 UTF-8 文件名，防目录穿越
- 📥 **范围下载**: HTTP Range 支持，适合大文件和断点续传

### 中间件与可观测性
- 📊 **访问日志**: method、path、status、duration、ip、user
- 🛡️ **异常恢复**: 统一 JSON 结构：`{code,msg,data}`
- 🚦 **速率限制**: 令牌桶算法 + 并发限制（asyncio.Semaphore）
- 🔒 **IP 过滤**: CIDR 支持，allow 优先，再 deny
- 🎯 **路由白名单**: `/healthz`、`/metrics`、`/`(GET)、`/t/*`(GET)
- ❤️ **健康检查**: `/healthz` 端点
- 📈 **简单指标**: `/metrics` 端点（请求计数、活动请求数、上传/下载字节）

### 配置与热加载
- 🔄 **热更新**: 监听 `chfs.yaml` 变更后热更新规则、限流参数、IP 过滤
- 🎛️ **灵活配置**: 支持多共享目录、多用户、复杂权限规则

## 🚀 Quick Start / 快速开始

### Windows 环境

#### 1. 使用 Python 运行

```powershell
# 克隆项目
git clone https://github.com/your-repo/chfs-py.git
cd chfs-py

# 创建虚拟环境（推荐）
python -m venv venv
.\venv\Scripts\Activate.ps1

# 安装依赖
pip install -e .

# 运行开发服务器
.\scripts\run-dev.ps1

# 或直接使用 uvicorn
uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8080
```

#### 2. 使用 Docker

```powershell
# 构建并运行
docker-compose up -d

# 或仅运行主服务
docker run -d \
  -p 8080:8080 \
  -v ${PWD}/chfs.yaml:/app/chfs.yaml:ro \
  -v ${PWD}/data:/data \
  --name chfs-py \
  chfs-py:latest
```

#### 3. Windows 服务安装

```powershell
# 安装为 Windows 服务（需要 NSSM）
.\scripts\install-service.ps1 -StartService

# 查看服务状态
.\scripts\install-service.ps1 -Action status

# 卸载服务
.\scripts\install-service.ps1 -Action uninstall
```

### 访问服务

- **Web 界面**: http://127.0.0.1:8080
- **WebDAV**: http://127.0.0.1:8080/webdav
- **健康检查**: http://127.0.0.1:8080/healthz
- **指标**: http://127.0.0.1:8080/metrics

默认用户: `alice` / `alice123`

## 📁 Project Structure / 项目结构

```
chfs-py/
├── app/                    # 主应用代码
│   ├── main.py            # 应用工厂
│   ├── config.py          # 配置管理
│   ├── models.py          # 数据模型
│   ├── auth.py            # 认证系统
│   ├── rules.py           # 权限规则
│   ├── ipfilter.py        # IP 过滤
│   ├── fs.py              # 文件系统操作
│   ├── ui.py              # Web 界面
│   ├── api.py             # REST API
│   ├── webdav.py          # WebDAV 支持
│   ├── middleware.py      # 中间件
│   ├── metrics.py         # 指标收集
│   └── utils.py           # 工具函数
├── templates/             # HTML 模板
│   ├── index.html         # 主界面
│   └── text.html          # 文本分享页面
├── static/                # 静态文件（可选）
├── scripts/               # PowerShell 脚本
│   ├── run-dev.ps1        # 开发服务器
│   ├── e2e_smoke.ps1      # 端到端测试
│   └── install-service.ps1 # 服务安装
├── tests/                 # 单元测试
├── chfs.yaml              # 配置文件示例
├── pyproject.toml         # 项目配置
├── Dockerfile             # Docker 构建
├── docker-compose.yml     # Docker Compose
└── README.md              # 本文档
```

## ⚙️ Configuration / 配置

### chfs.yaml 示例

```yaml
# 服务器配置
server:
  addr: "0.0.0.0"
  port: 8080
  tls:
    enabled: false
    certfile: ""
    keyfile: ""

# 共享目录
shares:
  - name: "public"
    path: "C:\\chfs-data\\public"
  - name: "home"
    path: "C:\\chfs-data\\home"

# 用户账户
users:
  - name: "alice"
    pass: "alice123"
    pass_bcrypt: false
  - name: "admin"
    pass: "$2b$12$KIXWCnqvs1.JX8qBZjQgXOzGvF8Ey5qJ8YvF9Qw1Xv2Z3A4B5C6D7"
    pass_bcrypt: true

# 访问控制规则
rules:
  - who: "alice"
    allow: ["R", "W", "D"]
    roots: ["public", "home"]
    paths: ["/"]
    ip_allow: ["*"]
  
  - who: "admin"
    allow: ["R", "W", "D"]
    roots: ["*"]
    paths: ["/"]
    ip_allow: ["192.168.0.0/16", "127.0.0.1/32"]

# 日志配置
logging:
  json: true
  file: "C:\\chfs-data\\logs\\chfs.log"
  level: "INFO"

# 速率限制
rateLimit:
  rps: 50
  burst: 100
  maxConcurrent: 32

# IP 过滤
ipFilter:
  allow:
    - "127.0.0.1/32"
    - "192.168.0.0/16"
    - "::1/128"
  deny:
    - "0.0.0.0/0"

# UI 配置
ui:
  brand: "chfs-py"
  title: "chfs-py File Server"
  textShareDir: "C:\\chfs-data\\public\\_text"
  # maxUploadSize: 104857600  # Optional upload cap (bytes); omit for unlimited uploads

# WebDAV 配置
dav:
  enabled: true
  mountPath: "/webdav"
```

## 🔐 Security / 安全性

### 路径安全
- 所有相对路径拼接后使用 `pathlib.Path.resolve()` 校验
- 严格防止目录穿越攻击（`../` 等）
- Windows 路径分隔符正确处理

### 认证授权
- HTTP Basic Authentication
- 支持明文密码和 bcrypt 哈希
- 基于规则的细粒度权限控制（READ/WRITE/DELETE）
- IP 地址过滤（CIDR 支持）

### 文件上传
- 可配置文件大小限制
- 安全的文件名处理
- 防止恶意文件上传

## 🛠️ Development / 开发

### 环境要求
- Python 3.11+
- Windows 10+ / Windows Server 2019+
- PowerShell 5.1+

### 开发设置

```powershell
# 克隆项目
git clone https://github.com/your-repo/chfs-py.git
cd chfs-py

# 创建虚拟环境
python -m venv venv
.\venv\Scripts\Activate.ps1

# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 运行开发服务器（带自动重载）
.\scripts\run-dev.ps1 -Reload -Debug

# 端到端测试
.\scripts\e2e_smoke.ps1 -Verbose
```

### API 接口

#### 文件操作
- `GET /api/list?root=<name>&path=<rel>` - 列出目录内容
- `POST /api/upload` - 上传文件 (multipart form-data)
- `POST /api/mkdir` - 创建目录 (JSON: {root, path})
- `POST /api/rename` - 重命名文件/目录 (JSON: {root, path, newName})
- `POST /api/delete` - 删除文件/目录 (JSON: {root, paths: []})
- `GET /api/download?root=<name>&path=<rel>` - 下载文件（支持 Range）

#### 文本分享
- `POST /api/textshare` - 创建文本分享 (JSON: {text})
- `GET /t/<id>` - 访问文本分享

#### 系统接口
- `GET /healthz` - 健康检查
- `GET /metrics` - 系统指标

### 权限映射
- **READ**: list, download, WebDAV PROPFIND/GET
- **WRITE**: upload, mkdir, rename, WebDAV PUT/MKCOL/MOVE/COPY  
- **DELETE**: delete, WebDAV DELETE

## 🐳 Docker Deployment / Docker 部署

### 基本部署

```bash
# 构建镜像
docker build -t chfs-py .

# 运行容器
docker run -d \
  --name chfs-py \
  -p 8080:8080 \
  -v $(pwd)/chfs.yaml:/app/chfs.yaml:ro \
  -v $(pwd)/data:/data \
  chfs-py
```

### Docker Compose

```bash
# 启动所有服务
docker-compose up -d

# 仅启动主服务
docker-compose up -d chfs-py

# 启动开发环境
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# 启动带监控的环境
docker-compose --profile monitoring up -d
```

## 📦 Building Executable / 构建可执行文件

### PyInstaller 打包

```powershell
# 安装构建依赖
pip install pyinstaller

# 打包为单个 EXE
pyinstaller --onefile --name chfs-py \
  --add-data "templates;templates" \
  --add-data "static;static" \
  --hidden-import uvicorn.lifespan.on \
  --hidden-import uvicorn.lifespan.off \
  --hidden-import uvicorn.protocols.websockets.auto \
  app/main.py

# 输出文件: dist/chfs-py.exe
```

### 使用构建的 EXE

```powershell
# 直接运行
.\dist\chfs-py.exe --config chfs.yaml

# 安装为服务
.\scripts\install-service.ps1 -UseExe -ExePath .\dist\chfs-py.exe -StartService
```

## 🔧 TLS/SSL Configuration / TLS 配置

### 生成自签名证书

```powershell
# 使用 OpenSSL
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes

# 配置 chfs.yaml
server:
  tls:
    enabled: true
    certfile: "cert.pem"
    keyfile: "key.pem"
```

### 转换 PFX 到 PEM

```powershell
# 提取私钥
openssl pkcs12 -in certificate.pfx -nocerts -out key.pem -nodes

# 提取证书
openssl pkcs12 -in certificate.pfx -nokeys -out cert.pem
```

## 📊 Monitoring / 监控

### 内置指标
访问 `/metrics` 端点获取以下指标：
- 请求总数和活动请求数
- 按方法和状态码分类的请求统计
- 上传/下载字节数
- 错误计数（认证失败、速率限制等）
- WebDAV 请求统计
- 平均响应时间

### Prometheus + Grafana
使用 Docker Compose 监控配置：

```bash
# 启动带监控的环境
docker-compose --profile monitoring up -d

# 访问
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000 (admin/admin)
```

## 🧪 Testing / 测试

### 运行测试

```powershell
# 单元测试
pytest

# 带覆盖率
pytest --cov=app --cov-report=html

# 端到端测试
.\scripts\e2e_smoke.ps1

# 特定测试
pytest tests/test_rules.py -v
```

### 测试覆盖
- 权限规则评估 (`test_rules.py`)
- 文件系统路径安全 (`test_fs_path.py`)
- HTTP Range 解析 (`test_range.py`)
- IP 过滤 (`test_ipfilter.py`)

## 🤝 Contributing / 贡献

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开 Pull Request

## 📝 License / 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 Acknowledgments / 致谢

- [CuteHttpFileServer](https://github.com/lishuai2016/CuteHttpFileServer) - 原始灵感来源
- [FastAPI](https://fastapi.tiangolo.com/) - 现代 Python Web 框架
- [WsgiDAV](https://github.com/mar10/wsgidav) - WebDAV 服务器实现
- [Tailwind CSS](https://tailwindcss.com/) - 实用优先的 CSS 框架

## 🆘 Support / 支持

如果你遇到问题或有建议：

1. 查看 [Issues](https://github.com/your-repo/chfs-py/issues)
2. 创建新的 Issue
3. 参考文档和示例配置
4. 运行端到端测试确认环境正常

---

**Made with ❤️ for the file sharing community**
