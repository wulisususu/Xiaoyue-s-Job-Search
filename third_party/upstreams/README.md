# Upstream Reference Workspace

这个目录专门用于保存 Xiaoyue's Job Search 的上游项目参考信息。

## 目录约定

- `_local/`：完整上游源码快照，仅供本机/沙盒阅读与对照，**不提交到 Git**。
- `manifest.json`：记录本次快照来源、SHA256、许可证与主要用途。
- `ADOPTION_GUIDE.md`：记录哪些模块值得借鉴，以及应该通过什么边界接入本项目。
- `licenses/`：保存许可证来源说明。

## 本地快照路径

```text
third_party/upstreams/_local/
├── offer-harvester/
├── workfind/
└── xiaozhao-radar/
```

这些目录有意被忽略，避免把第三方完整仓库、二进制资源、未来可能出现的个人资料或缓存直接混进主仓库。

开发代码不要直接从 `_local/` import。正式接入必须经过 `integrations/` 或 `services/` 的明确接口，以便后续替换/升级上游而不污染核心域模型。

## 当前职责划分

| 上游 | 在本项目中的主要角色 |
|---|---|
| WorkFind | 企业主库、央企/地方国企关系、招聘入口与校招时间来源 |
| Xiaozhao Radar | 招聘事件流、岗位 Feed、实时招聘数据来源 |
| Offer Harvester | Browser Agent、Playwright 会话、表单探测/填写/上传、人工确认与投递追踪参考 |

> `job-application-skills` 暂未放入该目录；按当前架构，它主要作为 Workflow / Prompt / Resume Strategy 参考，不作为第二套 Browser Agent 运行时。

## 重新导入快照

如果以后重新下载了上游 ZIP，可以运行：

```powershell
python .\scripts\import_upstreams.py `
  --offer-harvester C:\path\offer-harvester-main.zip `
  --workfind C:\path\workfind-master.zip `
  --xiaozhao-radar C:\path\xiaozhao-radar-main.zip
```

脚本会安全解压并自动去掉 GitHub ZIP 的最外层目录。导入完成后请把输出的 SHA256 与 `manifest.json` 对照；如果上游版本更新，再单独更新 manifest 和适配代码。
