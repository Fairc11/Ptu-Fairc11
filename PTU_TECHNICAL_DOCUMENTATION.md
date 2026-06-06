# Ptu 技术文档入口

> 状态：历史入口文件，已降级为索引。
> 当前长期技术真相来源：`PTU_TECHNICAL_DOCUMENTATION底层数据记录.md`

本文件原本是 v1.1.0 阶段的定型技术文档。随着 Ptu 继续迭代到 v1.5.0，真实研发记录、失败路径、发布验证、风险红线和后续计划已经集中维护在：

`PTU_TECHNICAL_DOCUMENTATION底层数据记录.md`

后续 AI/Agent 或开发者接手项目时，请不要再把本文件当作完整技术文档；它只保留为兼容旧链接的入口。

## 必读顺序

1. `docs/superpowers/plans/2026-06-03-ptu-risk-control-policy.md`
2. `CLAUDE.md`
3. `PTU_TECHNICAL_DOCUMENTATION底层数据记录.md`
4. `docs/superpowers/plans/2026-06-03-ptu-v1.5-zero-prerequisites.md`
5. `docs/superpowers/plans/2026-06-03-ptu-v1.5-douyin-slideshow-feedback.md`

## 风险红线摘要

Ptu 是用户本机主动操作的桌面辅助工具，不是 DouyinCrawler 式全量采集器。

- 不做账号互动自动化。
- 不做关注、粉丝、喜欢、收藏、话题、搜索、音乐原声等大范围采集入口。
- 不后台自动刷页面，不自动翻页，不自动扫描主页或搜索结果。
- 不绕过验证码、人机校验、风控页或接口限制。
- 不保存账号密码，不上传 cookie，不把 cookie 写进日志、诊断包、安装包、Git 或 Release。
- 批量下载必须有限量、限并发、可取消；遇到 403、验证码、风控或连续失败必须停止并提示用户。

完整规则见：

`docs/superpowers/plans/2026-06-03-ptu-risk-control-policy.md`
