# Kissne Prototype · yeqingxu.cyou 同源部署

目标：**不改现有 HTML 原型 UI，不改 Kissne Mobile Adapter，不启用 CORS。**

部署后：

- UI：`https://yeqingxu.cyou/kissne/`
- API：同源根路径 `/pair`、`/bootstrap`、`/messages`、`/cancel`
- `transport.js` 在 HTTPS 页面下默认使用 `location.origin`，因此不需要额外填写 API 域名。
- 现有 Mobile Adapter 仍只负责四个公网接口；静态文件由 nginx 直接提供。

## 一次性接入

在服务器的**现有** `yeqingxu.cyou:443` 的 `server { ... }` 中加入：

```nginx
include /etc/nginx/snippets/kissne-prototype.conf;
```

不要创建第二个 `server_name yeqingxu.cyou`，也不要改已有四个 API 的反代 `location`。

然后在仓库根目录执行：

```bash
bash kissne-prototype/deploy/deploy.sh
```

脚本会：

1. 原样同步 `kissne-prototype/prototype/` 到 `/var/www/kissne-prototype/`；
2. 安装 `nginx-kissne-location.conf`；
3. 检查 nginx 是否实际加载该 location；
4. 执行 `nginx -t`；
5. reload nginx；
6. 回读 `/kissne/`，并验证 `/bootstrap /messages /cancel` 未认证请求仍为 401。

如果现网 nginx vhost 还没 include snippet，脚本会**停止在 reload 前**并输出需要加入的单行 include，不会猜配置文件或覆盖现有 vhost。
