# Christmas Factory

梦幻紫色圣诞礼物工厂网站。此版本只调整粉丝端页面布局与文案，保留原有 Flask + Supabase PostgreSQL 数据表、登录注册、投票凭证上传、审核、原料累计、礼物兑换和管理员权限逻辑。

## Render 配置

- Runtime: Python 3
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app`
- Root Directory: 留空（仓库根目录直接放置 app.py）

环境变量：

- `DATABASE_URL`: Supabase PostgreSQL 连接串（使用你项目自己的连接串，不要把真实密码写进代码或公开仓库）
- `ADMIN_PASSWORD`: 高级审核员密码
- `AUDIT_PASSWORD`: 普通审核员密码
- `SECRET_KEY`: 一段足够长的随机字符串

## 重要说明

- 不需要重新创建 Supabase 项目。
- 不要运行清空数据库、DROP TABLE 或重置数据的 SQL。
- 本版本启动时只会按原逻辑创建缺失表/字段，并补齐四个活动会场默认配置；已存在的用户、投票凭证、审核结果、奖品及订单不会主动清空。
- 初始账号原料为 0；每 1 票审核通过，增加 1 份原料。
- 四个会场：粉丝团聚力场、星拍站姐光影场、粉丝IP元力场、超话大赏。前三个默认链接为 `http://t.cn/AXcF9tyj`，超话大赏为 `http://t.cn/AXTMhDZ8`。
- 用户密码支持英文字母和数字；个人提交记录仅本人登录后可见；榜单为全站共享。
- 普通审核员只能审核凭证；高级审核员可以管理奖品及会场设置。

## 更新现有 Render 服务

将 ZIP 解压后，把其中的 `app.py`、`requirements.txt`、`render.yaml`、`.env.example`、`README.md` 更新到原 GitHub 仓库 `christmas-factory` 对应目录（Render 的 Root Directory 已设置为 `christmas-factory-v2`，请将 ZIP 内该文件夹的内容覆盖仓库中的同名文件夹）。提交到 `main` 分支后，Render 会自动部署。保留现有 Render 环境变量，不要把 `.env.example` 上传成真实密钥。
