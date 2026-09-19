# Android UI 规划 v0.1

这是施工规格，不是最终视觉稿。素材未 approved 前，不提交最终 UI。

## 页面优先级

1. 启动/连接检查
2. 配对页：输入一次性 pairing code，成功后保存 device token
3. 当前 Conversation 聊天页
4. 以后再做功能入口、小机星、记忆库、语音和工具页

## 聊天页结构

- 顶部：当前 Conversation 名称或明确的当前会话标识、连接状态。
- 中部：有界历史消息列表，进入 App 后直接显示当前 Conversation。
- 助手消息：使用叶青栩小狐狸头部头像；头像随状态改变表情/动作，不更换角色。
- 用户消息：简洁文本行或轻量容器，避免过重的气泡视觉。
- 底部：文本输入、发送、停止/取消、重试。
- 不显示 provider key、session_key、内部 cursor 或核心 pairing 细节。

## 协议状态到 UI

| 协议/业务状态 | UI 表现 | 可操作项 |
|---|---|---|
| connecting | 连接中提示，头像 idle | 等待 |
| ready | 可输入 | 发送 |
| pending | 头像思考，显示未完成状态 | 取消 |
| streaming/delta | 增量文字持续更新，不能显示完成标记 | 取消 |
| completed | 固化全文，显示完成态 | 继续发送 |
| cancelled | 保留已收到内容，标明已取消 | 继续发送/重试 |
| error | 明确失败，不伪装成完成 | 重试 |
| offline/reconnecting | 顶部离线/重连提示 | 重试或等待 |

## 硬验收对应

- 打开 App 后进入当前 Conversation，不凭空创建“只有手机”的新会话。
- 能区分 pending、未完成增量和 completed。
- 相同 `message_id` 重试不能产生第二个 turn。
- 取消后能看到 cancel acknowledgement 或等价的已取消状态。
- gateway 重启后令牌、游标和未确认回复可恢复。
- 断线期间不能静默丢掉回复。

## 当前不做

- 不做最终配色、字体、动效时长或品牌图形定稿。
- 不做小机星、记忆图、语音和工具页面的最终 UI。
- 不修改 core、Provider、Memory 真相或生产配置。
