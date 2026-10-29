# 浙城文创展示

首版产品目录，目标域名 `zhecheng.aiarrival.cn`。纯静态 HTML/CSS/JS，无服务端进程、数据库和第三方字体或图片依赖。

## 文件

- `dist/`：可发布网页。
- `catalog-draft/`：独立设计工作副本。
- `backups/placeholder-20261029/`：原始占位页备份。
- `scripts/extract_catalog.py`：读取源表 Sheet1，按 WPS DISPIMG ID 解析图片，生成产品数据及 WebP 图片。不会改动源表。
- `deploy/zhecheng.aiarrival.cn.http.conf`：独立 HTTP 站点配置草稿，需核对服务器配置加载方式后安装。

## 内容

源文件《城院文创-实时更新.xlsx》，39 件产品、49 个图片引用；产品名称、品牌、规格、工艺、价格和各款条码均保留。分类为网页导航整理，价格数值用于排序，详情保留原表标价文字。原表没有额外的长篇产品介绍，页面未补写产品卖点。原始表格及本地备份不上传到仓库。

此版本是导入表格的静态快照，不会随源表自动更新。更新表格后需重新提取并发布。收藏只保存在访问者当前浏览器，不涉及账户或服务器数据。

## 本地预览

在项目目录运行 `python3 -m http.server 8765 --bind 127.0.0.1 --directory dist`，访问 `http://127.0.0.1:8765/`。

提取更新的源表：`python3 scripts/extract_catalog.py "/path/to/城院文创-实时更新.xlsx"`（需要 Pillow）。输出到独立的 `catalog-draft/`，核对后再将更新的数据和图片同步到 `dist/`；提取脚本不会覆盖页面设计文件。

## 部署边界

服务器操作由用户执行。目标为独立目录 `/var/www/zhecheng.aiarrival.cn/`，采用 `releases/<version>/` 及 `current` 软链接管理版本；独立 Nginx 虚拟主机、独立日志，不修改其他站点或全局配置。先用只读检查核对 include 路径、域名冲突、证书工具，再提供安装命令。每次加载前运行 `nginx -t`，通过后使用平滑 reload。Nginx 仍为共享基础服务，不能声称完全物理隔离。

站点配置写入 `/etc/nginx/sites-enabled/zz-zhecheng.aiarrival.cn.conf`，在现有站点之后加载，避免新配置因先被加载而改变隐式默认站点。加载前后除检查已知域名状态，还会比较 IPv4/IPv6 默认站点的完整响应；默认站点内容发生变化会撤回新站配置。

HTTPS 证书尚未配置，DNS 与公网可达性尚未确认。不得将本地预览或配置草稿视为已部署。

## 通过 Git 部署首版

仓库：`https://github.com/Sahaquiel-10th/zhecheng.git`。提交包含 `dist/`，服务器无需安装 Node 或构建依赖。先克隆到独立的用户目录，然后从已确认的提交打包 `dist/`，把生成的包交给安装脚本。

```bash
git clone --branch main --single-branch https://github.com/Sahaquiel-10th/zhecheng.git "$HOME/zhecheng-deploy"
cd "$HOME/zhecheng-deploy"
git rev-parse HEAD
# 将已确认的完整提交 SHA 替换到下面两处。
git archive --format=tar.gz --output=/tmp/zhecheng-web.tar.gz COMMIT_SHA:dist
sudo bash deploy/install-zhecheng.sh /tmp/zhecheng-web.tar.gz
```

`install-zhecheng.sh` 默认用于首次安装：目标目录或配置已存在时停止。它先备份 `/etc/nginx`，检查域名冲突，创建该域名自己的静态文件目录及配置，检查语法，再平滑加载。验收请求通过 `--noproxy '*'` 直连本机，最多尝试 12 次，以等待平滑加载完成；必须同时匹配新站专属响应头及完整 HTML，其他站点的 HTTP 200 不会通过。已知其他项目加载前后 HTTP 状态变化也会触发撤下新站配置。加载或新站验证失败时撤下本次新增配置，并保留诊断响应文件。现有项目的状态对比属于辅助检查，不能代替完整业务验收。

对于首次安装已回退、仅保留项目文件的情形，可显式使用 `sudo bash deploy/install-zhecheng.sh /tmp/zhecheng-web.tar.gz --resume-after-rollback`。只有同域名配置不存在、没有其他 Nginx 配置引用该目录、`current` 指向本项目版本目录，且保留的所有发布文件与指定 Git 包逐字节一致时才允许恢复；不重写保留的发布文件或软链接。

部署验收回归检查：`python3 -m unittest discover -s tests -v`，使用本机隔离的临时 HTTP 服务模拟平滑加载及其他站点响应，不访问生产服务器。

首版脚本只开通 HTTP。HTTPS 使用 `certbot certonly --webroot` 为新域名单独签发，核验 DNS 和 HTTP 公网可达性后，再单独配置本项目的 443 虚拟主机。
