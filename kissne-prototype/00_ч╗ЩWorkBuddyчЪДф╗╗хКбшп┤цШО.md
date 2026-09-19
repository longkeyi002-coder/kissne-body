# 给 WorkBuddy 的任务说明

## 任务

请在本地完成 Kissne Android 聊天页面的素材整理和 UI 施工准备，不提交最终 Android UI 代码。


## 必做

1. 复制原素材到 `assets_source/`，保留原文件名。
2. 为每个文件计算 SHA-256，生成 `ASSET_MANIFEST.md`。
3. 生成 `preview/contact_sheet.png`，按文件名标注缩略图。
4. 按 `01_素材需求清单.md` 标出：已有、待裁切、待确认、缺失。
5. 只做非破坏性整理：可裁切、去背景、统一画布，但必须保留原图和处理记录。
6. 生成 `DELIVERY_CHECKLIST.md`，列出已完成项、阻塞项和建议下一步。

## 严格禁止

- 不改动角色的脸、眼睛、耳朵、额头蓝色菱形、蝴蝶结、铃铛或整体比例。
- 不生成新的狐狸/小羊角色，不把其他角色风格套进来。
- 不把低清截图、emoji、文字头像、AI 临时生成图标记为 approved。
- 不修改 `kissne-body`、`kissne-soul`、`gateway`、核心代码、生产配置或 GitHub 内容。
- 不安装签名、不打包发布 APK，不处理密钥。
- 不在没有素材确认前提交最终 Android UI。

## 输出

请输出一个本地目录或 zip，至少包含：

```text
assets_source/       原始素材副本
assets_working/      非破坏性处理稿
preview/             contact_sheet.png 和必要的单项预览
ASSET_MANIFEST.md    文件、尺寸、格式、哈希、来源、状态
UI_NOTES.md          发现的问题和待确认项
DELIVERY_CHECKLIST.md
```

最终回复只需报告：素材总数、可直接使用数、待确认数、缺失数、是否发现角色不一致，以及 zip 路径。
