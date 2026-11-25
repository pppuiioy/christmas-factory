# 冬日心愿·圣诞礼物工厂
1. 解压，将 app.py、requirements.txt、render.yaml 上传到新的 GitHub 仓库。
2. Supabase 新建项目，在 Connect 中选择 Session pooler 的 PostgreSQL URI，替换数据库密码（特殊字符需 URL 编码），作为 DATABASE_URL。建议 URI 包含 sslmode=require。
3. Render 新建 Web Service，连接 GitHub 仓库，Runtime Python，Build Command: pip install -r requirements.txt，Start Command: gunicorn app:app。
4. Environment 添加 DATABASE_URL、ADMIN_PASSWORD（高级审核员密码）、AUDIT_PASSWORD（普通审核员密码，须不同）、SECRET_KEY（随机长字符串）。选择可用套餐并部署。首次启动自动建表，无需手动执行 SQL。
5. 打开 Render 提供的 HTTPS 地址，页面底部管理员入口登录，检查已预设的四个投票入口，新增奖品及库存。
6. 注册测试账号，上传 JPG/PNG 截图或 MP4/MOV 录屏，后台审核，检查仓库、排行榜和兑换。确认后再公开链接。
注意：截图存储于 PostgreSQL，单次请求上限50MB；大量截图会占用数据库空间。只检查同账号同会场完全相同的截图，管理员仍需人工识别重复或累计截图。奖品下架保留历史订单。发货联系方式需线下收集。密码无固定长度，仅允许英文及数字，建议至少8位。公开榜单展示微博ID及票数。请使用独立数据库项目并保管环境变量。此版本未连接真实数据库进行端到端测试；正式上线前请测试。生产环境建议补充登录限流及备份。
