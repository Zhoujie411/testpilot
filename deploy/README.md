# Ubuntu + Nginx + HTTPS 部署

以下命令默认仓库位于 `/home/ubuntu/testpilot`，域名已经解析到服务器公网 IP。

## 1. 后端环境

```bash
cd /home/ubuntu/testpilot/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```

`.env` 至少填写：

```env
TESTPILOT_SECRET_KEY=足够长且固定的随机值
TESTPILOT_ADMIN_USERNAME=admin
TESTPILOT_ADMIN_PASSWORD=至少12位的强密码
ACCESS_TOKEN_EXPIRE_HOURS=8
CORS_ORIGINS=https://YOUR_DOMAIN
```

## 2. systemd

```bash
sudo cp deploy/systemd/testpilot-api.service /etc/systemd/system/testpilot-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now testpilot-api
sudo systemctl status testpilot-api
curl http://127.0.0.1:8000/health
```

若服务器用户名或仓库路径不同，需要先修改 service 文件中的 `User`、`Group`、`WorkingDirectory`、`EnvironmentFile` 和 `ExecStart`。

## 3. 构建前端

生产环境前端通过同域名 `/api` 访问后端，无需开放 8000/8001 公网端口。

```bash
cd /home/ubuntu/testpilot/frontend
npm ci
npm run build
sudo mkdir -p /var/www/testpilot
sudo cp -r dist/. /var/www/testpilot/
```

## 4. Nginx 与 HTTPS

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
sudo cp deploy/nginx/testpilot.conf /etc/nginx/sites-available/testpilot
sudo sed -i 's/YOUR_DOMAIN/test.example.com/g' /etc/nginx/sites-available/testpilot
sudo ln -s /etc/nginx/sites-available/testpilot /etc/nginx/sites-enabled/testpilot
sudo nginx -t
sudo systemctl reload nginx
```

确认 HTTP 可访问后签发证书：

```bash
sudo certbot --nginx -d test.example.com --redirect
sudo certbot renew --dry-run
```

腾讯云轻量应用服务器防火墙只需放行 TCP `80` 和 `443`。确认 HTTPS 正常后，删除原来对公网开放的 `8000`、`8001` 规则。

## 5. 更新发布

```bash
cd /home/ubuntu/testpilot
git pull origin main

cd backend
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart testpilot-api

cd ../frontend
npm ci
npm run build
sudo cp -r dist/. /var/www/testpilot/
sudo nginx -t && sudo systemctl reload nginx
```

查看日志：

```bash
sudo journalctl -u testpilot-api -f
sudo tail -f /var/log/nginx/error.log
```
