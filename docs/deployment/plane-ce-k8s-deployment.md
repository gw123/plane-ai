# Plane CE K8s 部署修复记录

## 问题背景

Plane CE v1.2.3 部署在 Kubernetes `plane` namespace，通过 Helm chart 安装。
初始访问 `https://plane-dev.inner.chj.cloud` 注册时报 **405 Not Allowed**。

---

## 根本原因分析

### 问题一：Ingress 未启用，各服务独立 LoadBalancer

Helm values 中 `ingress.enabled: false`，导致每个服务分别暴露 LoadBalancer IP。

前端 SPA（plane-ce-web）是纯 nginx 静态服务，nginx 配置如下：

```nginx
location / {
    root /usr/share/nginx/html;
    try_files $uri $uri/ /index.html;
}
```

没有任何 proxy_pass，所以浏览器发出的 `POST /auth/email-check/` 请求打到 web nginx 后返回 **405**。

### 问题二：域名解析指向错误 IP

域名 `plane-dev.inner.chj.cloud` 最初解析到 `plane-ce-web`（120.48.235.159），
所有 `/api/`、`/auth/` 请求都被 web nginx 处理，无法路由到 API 服务。

### 问题三：LiFE 网关路由规则未配置

尝试在 LiFE 内网负载均衡平台配置路由后，`/auth/` 路径返回 `{"error_msg":"404 Route Not Found"}`，
说明 LiFE 网关没有对应的后端路由规则，且配置复杂度较高。

### 问题四：god-mode 状态不一致

`is_setup_done: true` 但没有 admin 账号（或密码未知），god-mode 无法登录也无注册入口。

---

## 修复方案：部署 nginx 反向代理

### 方案选择原因

- 集群无 Ingress Controller（`kubectl get ingressclass` 权限不足/不存在）
- LiFE 网关路由配置复杂，路径路由无法正常工作
- 最快可落地：在 plane namespace 新增一个 nginx 代理 Pod

### 路由规则

```
plane-dev.inner.chj.cloud (120.48.235.154:80)
├── /api/          → plane-ce-api.plane.svc.cluster.local:8000
├── /auth/         → plane-ce-api.plane.svc.cluster.local:8000
├── /auth-token/   → plane-ce-api.plane.svc.cluster.local:8000
├── /social-auth/  → plane-ce-api.plane.svc.cluster.local:8000
├── /uploads/      → plane-ce-api.plane.svc.cluster.local:8000
├── /spaces/       → plane-ce-space.plane.svc.cluster.local:3000
├── /live/         → plane-ce-live.plane.svc.cluster.local:3000  (WebSocket)
├── /god-mode/     → plane-ce-admin.plane.svc.cluster.local:3000
└── /              → plane-ce-web.plane.svc.cluster.local:3000
```

### 部署资源

```bash
# ConfigMap + Deployment + Service (LoadBalancer)
kubectl apply -f /tmp/plane-nginx-proxy.yaml -n plane
```

资源名称：

- ConfigMap: `plane-nginx-proxy-config`
- Deployment: `plane-nginx-proxy`
- Service: `plane-nginx-proxy`（LoadBalancer IP: 120.48.235.154）

### DNS 更新

将 `plane-dev.inner.chj.cloud` 解析更新为 `120.48.235.154`（nginx 代理）。

---

## god-mode Admin 修复

由于 `is_setup_done: true` 但 admin 密码未知，通过 Django shell 重置密码：

```bash
kubectl exec -n plane deployment/plane-ce-api-wl -- python manage.py shell -c "
from plane.db.models import User
u = User.objects.get(email='gaowei7@lixiang.com')
u.set_password('Lixiang123!')
u.save()
"
```

god-mode 登录：`https://plane-dev.inner.chj.cloud/god-mode/`

---

## 注册流程

完成注册的完整步骤：

1. 访问 `https://plane-dev.inner.chj.cloud`
2. 输入邮箱 → Continue → 设置密码 → Create account
3. onboarding：填写名字 → 选择角色（可 Skip）→ 选择目标（可 Skip）→ 创建 Workspace
4. Workspace 名称填写后需选择团队规模才能启用 Create 按钮

最终账号：

- 邮箱：`gaowei@lixiang.com`
- 密码：`Lixiang123!`
- Workspace：`lixiang`

---

## 关键命令备忘

```bash
# 查看所有 pod 状态
kubectl get pods -n plane

# 查看服务 IP
kubectl get svc -n plane

# 查看 nginx 代理日志
kubectl logs -n plane deployment/plane-nginx-proxy

# 查看 API 日志
kubectl logs -n plane deployment/plane-ce-api-wl --tail=50

# 重置 admin 密码
kubectl exec -n plane deployment/plane-ce-api-wl -- python manage.py shell -c "
from plane.db.models import User
u = User.objects.get(email='<email>')
u.set_password('<new_password>')
u.save()
"

# 查看实例状态
kubectl exec -n plane deployment/plane-ce-api-wl -- python manage.py shell -c "
from plane.license.models import Instance
i = Instance.objects.first()
print('setup_done:', i.is_setup_done)
"

# 重新部署 nginx 代理（如配置更新）
kubectl rollout restart deployment/plane-nginx-proxy -n plane
```

---

## god-mode 登录失败 Bug 分析（已修复）

### 现象

浏览器访问 `https://plane-dev.inner.chj.cloud/god-mode/` 登录时，始终报
`ADMIN_AUTHENTICATION_FAILED`（error_code=5175），而相同账号密码用 curl 却能成功。

### 根本原因：两个独立问题叠加

#### 原因一：WEB_URL 配置为 http（协议错误）

Helm 部署时 ConfigMap `plane-ce-app-vars` 中 `WEB_URL` 默认为：

```
WEB_URL: http://plane-dev.inner.chj.cloud
```

Plane 的 `InstanceAdminSignInEndpoint` 登录成功后通过 `base_host()` 函数生成跳转地址：

```python
# plane/utils/host.py
base_origin = settings.WEB_URL  # → http://plane-dev.inner.chj.cloud
url = urljoin(base_origin + "/god-mode/", "general/")
return HttpResponseRedirect(url)  # → http://...
```

**影响：**

- 登录成功后 302 跳转到 `http://` 地址
- API 在 302 响应中设置了 `admin-session-id` cookie（带 `Secure` flag）
- LiFE 网关将 302 转发给浏览器时，部分中间层可能丢弃 `Secure` cookie 在 HTTP redirect 场景下的传递
- 浏览器跳转到 `http://` 后，`Secure` cookie 无法随 HTTP 请求发送，导致 session 失效

**修复：**

```bash
kubectl patch configmap plane-ce-app-vars -n plane \
  --type merge \
  -p '{"data":{"WEB_URL":"https://plane-dev.inner.chj.cloud","CORS_ALLOWED_ORIGINS":"https://plane-dev.inner.chj.cloud"}}'
kubectl rollout restart deployment/plane-ce-api-wl -n plane
```

#### 原因二：密码含特殊字符 `!` 在浏览器 form 提交时失败

登录视图读取密码方式为 Django 标准 form 数据：

```python
password = request.POST.get("password", False)
if not user.check_password(password):
    return redirect(error_url)  # → ADMIN_AUTHENTICATION_FAILED
```

**现象对比：**
| 方式 | 密码 | 结果 |
|---|---|---|
| curl `--data-urlencode` | `Lixiang123!` | ✅ 登录成功 |
| 浏览器 form 提交 | `Lixiang123!` | ❌ check_password 失败 |
| 浏览器 form 提交 | `Lixiang123` | ✅ 登录成功 |

**可能机制：**
浏览器 form 提交时 `!` 被编码为 `%21`，经过 LiFE 网关 → nginx proxy → Django 的请求链路，
某层对 `%21` 进行了二次处理（double decode 或 escape），导致 Django 收到的实际密码字符串
与数据库存储的 hash 不匹配。

curl 使用 `--data-urlencode` 直接构造请求体，绕过了浏览器的 form encoding，因此不受影响。

**注意：此问题仅影响 god-mode admin 登录**（使用 Django session + form POST）。
主应用用户登录（`/auth/sign-in/`）走 JSON API，不受 form encoding 影响，`!` 密码正常工作。

**修复：**
god-mode admin 密码避免使用 `!` 等特殊字符，或通过 Django shell 设置：

```bash
kubectl exec -n plane deployment/plane-ce-api-wl -- python manage.py shell -c "
from plane.db.models import User
u = User.objects.get(email='gaowei7@lixiang.com')
u.set_password('Lixiang123')   # 不含特殊字符
u.save()
print('ok:', u.check_password('Lixiang123'))
"
```

### 最终账号信息（修复后）

| 类型           | 邮箱                  | 密码          |
| -------------- | --------------------- | ------------- |
| god-mode admin | `gaowei7@lixiang.com` | `Lixiang123`  |
| 主应用用户     | `gaowei@lixiang.com`  | `Lixiang123!` |

---

---

## 图片上传 Mixed Content Bug（已修复）

### 现象

上传图片时浏览器报错并拦截请求：

```
Mixed Content: The page at 'https://plane-dev.inner.chj.cloud/...' was loaded over HTTPS,
but requested an insecure XMLHttpRequest endpoint 'http://plane-dev.inner.chj.cloud/uploads'.
This request has been blocked; the content must be served over HTTPS.
```

### 根本原因

**问题一：`/uploads` 路由指向了 API 而非 MinIO**

nginx 代理的 `/uploads/` 路由打到了 `plane-ce-api:8000`，但上传图片是浏览器用 S3 预签名 POST 直接打到 MinIO bucket，需要路由到 `plane-ce-minio:9000`。

**修复：** 更新 nginx 配置，新增 MinIO upstream 并将 `/uploads` 路由指向 MinIO：

```nginx
upstream minio { server plane-ce-minio.plane.svc.cluster.local:9000; }

location /uploads {
    proxy_pass http://minio;
    proxy_set_header Host plane-ce-minio.plane.svc.cluster.local:9000;
}
```

**问题二：预签名 URL 生成为 `http://`，触发 Mixed Content**

API 生成 MinIO 预签名上传 URL 的逻辑（`apps/api/plane/settings/storage.py:41-51`）：

```python
if os.environ.get("MINIO_ENDPOINT_SSL") == "1":
    endpoint_protocol = "https"
else:
    endpoint_protocol = request.scheme  # ← 取请求的 scheme
endpoint_url = f"{endpoint_protocol}://{request.get_host()}"
```

请求链路：`浏览器(HTTPS) → LiFE(SSL终止) → nginx(HTTP) → API(HTTP)`

LiFE 做了 HTTPS 终止，API 收到的 `request.scheme = "http"`，导致生成预签名 URL 为 `http://plane-dev.inner.chj.cloud/uploads/...`。页面是 HTTPS 加载的，浏览器判定为 Mixed Content，直接拦截。

**修复：** 设置 `MINIO_ENDPOINT_SSL=1`，跳过 `request.scheme` 判断，强制使用 `https`：

```bash
kubectl patch configmap plane-ce-app-vars -n plane \
  --type merge \
  -p '{"data":{"MINIO_ENDPOINT_SSL":"1"}}'
kubectl rollout restart deployment/plane-ce-api-wl -n plane
```

### 关键配置项

| 配置项               | 值             | 说明                      |
| -------------------- | -------------- | ------------------------- |
| `MINIO_ENDPOINT_SSL` | `1`            | 强制预签名 URL 使用 https |
| nginx `/uploads`     | → `minio:9000` | 直传 MinIO bucket         |

### 注意事项

1. **nginx 代理配置更新**：修改 ConfigMap 后需 rollout restart 才生效
2. **WebSocket 支持**：`/live/` 路径已配置 `Upgrade` 和 `Connection` header
3. **上传文件大小**：nginx 代理设置了 `client_max_body_size 100m`，API 侧限制为 5MB（`doc_upload_size_limit: 5242880`）
4. **HTTPS**：LiFE 平台处理 SSL 终止，nginx 代理监听 HTTP 80 端口
5. **god-mode 地址**：`https://plane-dev.inner.chj.cloud/god-mode/`
6. **WEB_URL 必须为 https**：否则登录后 session cookie 无法在浏览器中正常保存
7. **god-mode 密码避免特殊字符**：`!`、`#`、`&` 等字符在 form 提交经过多层代理时可能被错误处理
8. **MINIO_ENDPOINT_SSL 必须为 1**：LiFE 做 SSL 终止后内部是 HTTP，若不设此项，预签名 URL 会生成 http:// 触发 Mixed Content
