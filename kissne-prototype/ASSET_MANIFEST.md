# 素材清单 (ASSET_MANIFEST)

- **首次生成**：2026-09-17　|　**本次更新**：2026-09-19（原型版本 `20260919m`，线上已发布）
- **范围**：`锚点/`（视觉锚点）+ `视觉资产/成品素材/`（用户提供的成品素材）+ `prototype/assets/`（已接入原型的素材）。
  **不含 Android 正式 UI。**
- **操作原则**：非破坏性——未改动任何图片内容、未重绘角色、未重新生成角色；原图原地保留并登记 SHA-256。
- **角色映射**：叶青栩 = `yeqingxu`（小狐狸助手）；小羊 = `user_lamb` = 龙柯伊（用户角色）。
- **状态取值**：已有 / 待处理 / 待确认 / 缺失 / approved。
- **本次核对方式**：所有尺寸、格式、透明通道、哈希、体积均由脚本**现场扫描得出**，不是照抄旧记录。
  SHA-256 只登记**前 16 位**（完整值随文件走，需要时再补）。

> ⚠️ **与上一版（2026-09-17）的差别**：上一版记的是"锚点图待确认、成品素材一份都还没产出"。
> 现在用户已提供 55 个成品素材文件，其中 **5 个占位位已经接上真图**（详见第三节）。

---

## 一、视觉锚点 `锚点/`（3 张图 · **未改动**）

| 文件名 | 角色 | 尺寸(px) | 格式 | 透明背景 | 确认状态 | SHA-256(前16) | 体积 |
|---|---|---|---|---|---|---|---|
| 双人图.png | 叶青栩 + 龙柯伊(小羊) | 1254×1254 | PNG-RGB | 否（无 alpha 通道） | 待确认 | `8af66bfddd4ea272` | 1773 KB |
| 叶青栩.jpg | 叶青栩(小狐狸) | 1536×1024 | JPEG-RGB | 否 | 待确认 | `e21f2ffe5ca9f357` | 174 KB |
| 龙柯伊.jpg | 龙柯伊 / 小羊 | 1536×1024 | JPEG-RGB | 否 | 待确认 | `48e4c4af6faa2e66` | 175 KB |

> **未改动是可验证的**：三张的 SHA-256 与 2026-09-17 首版清单逐条一致（见上表）。
> 锚点仍为「待确认」——它们只作**构图与角色一致性参考**，不直接进产品。

---

## 二、用户提供的成品素材 `视觉资产/成品素材/`（55 个文件 · 49.62 MB）

### 2.1 功能入口页 — 首页两张星卡的插画（4 张）

| 文件名 | 内容 | 尺寸(px) | 格式 | 透明背景 | SHA-256(前16) | 体积 |
|---|---|---|---|---|---|---|
| renren-star-lamb-day.png | 人人星 · 小羊抱手机 + 太阳 | 1338×1176 | PNG-RGB | 否 | `b663100fb58aefef` | 2038 KB |
| renren-star-lamb-night.png | 人人星 · 小羊 + 夜空月亮 | 1338×1176 | PNG-RGB | 否 | `61283ee6e3efdbde` | 2122 KB |
| xiaoji-star-fox-day.png | 小机星 · 叶青栩抱手机 + 太阳 | 1338×1176 | PNG-RGB | 否 | `8fb30542e33ca554` | 2065 KB |
| xiaoji-star-fox-night.png | 小机星 · 叶青栩 + 夜空月亮 | 1338×1176 | PNG-RGBA | **alpha 是坏的** | `dd37b9015df2eceb` | 2437 KB |

> **文件名的对应关系就是身份的判据**：`renren-star-lamb` = 人人星 = 小羊；`xiaoji-star-fox` = 小机星 = 叶青栩。
> `xiaoji-star-fox-night.png` 的 alpha **既没有全透明像素、也几乎没有全不透明像素**（实测 0.0% / 0.0%），
> 是典型的坏通道数据 —— 合成到白底会**整幅蒙一层白雾**。生成器已按判据**自动拍平为不透明**。

### 2.2 通知与头像 `通知与头像/_原始生成/`（19 张）

#### 2.2.1 叶青栩聊天头像 7 张（= 7 种表情，头部特写）

| 文件名 | 表情 | 尺寸(px) | 全透明占比 | SHA-256(前16) | 体积 |
|---|---|---|---|---|---|
| fox-chat-avatar (1).png | 平静微笑 | 373×467 | 26.2% | `81552b6815619a41` | 216 KB |
| fox-chat-avatar (2).png | 开心大笑（吐舌举爪） | 368×460 | 24.5% | `788e5bdf9134d603` | 211 KB |
| fox-chat-avatar (3).png | 托腮思考 + 问号 | 374×468 | 25.4% | `e990ce3ebf593121` | 225 KB |
| fox-chat-avatar (4).png | 疑问（O 嘴 + 大问号） | 375×469 | 26.3% | `e14d31cd2e78ca7c` | 220 KB |
| fox-chat-avatar (5).png | 委屈 / 难过（汗滴） | 398×498 | 27.3% | `5826b7d6bddca40b` | 240 KB |
| fox-chat-avatar (6).png | 睡着（闭眼 + Zzz） | 434×487 | 31.1% | `9c7ff31f1c0680c2` | 234 KB |
| fox-chat-avatar (7).png | 手忙脚乱 / 慌张 | 420×526 | 34.6% | `8bd7ce6a9e13db01` | 248 KB |

#### 2.2.2 叶青栩全身 5 张（留给星卡 / 状态插画，**目前未用**）

| 文件名 | 内容 | 尺寸(px) | 全透明占比 | SHA-256(前16) | 体积 |
|---|---|---|---|---|---|
| fox-transparent-01.png | 坐着平静 | 469×469 | 35.8% | `5595578ce4bd43f5` | 280 KB |
| fox-transparent-02.png | 趴桌上用笔记本 | 469×469 | 32.1% | `9bb7526ab4a48407` | 277 KB |
| fox-transparent-03.png | 整理文件夹 | 496×496 | 36.1% | `66337494dd890266` | 297 KB |
| fox-transparent-04.png | 举爪欢呼 | 473×473 | 34.7% | `6beef1eb50f828f5` | 288 KB |
| fox-transparent-05.png | 嘟嘴不安 | 461×461 | 32.2% | `9771d3313fcda0f7` | 274 KB |

#### 2.2.3 小羊（人人星 / 用户"我"）头像 7 张

| 文件名 | 表情 | 尺寸(px) | 全透明占比 | SHA-256(前16) | 体积 |
|---|---|---|---|---|---|
| user-avatar (1).png | 平静 | 396×417 | 32.2% | `30b9090c41efb899` | 224 KB |
| user-avatar (2).png | 大笑 | 393×432 | 33.2% | `f7017740992c8422` | 225 KB |
| user-avatar (3).png | 思考（泡泡） | 397×442 | 34.4% | `d9c1294b15d01954` | 236 KB |
| user-avatar (4).png | 疑问 | 392×436 | 34.7% | `2e2d52f5a18b87a8` | 231 KB |
| user-avatar (5).png | 委屈（汗滴） | 443×434 | 35.1% | `e5d05020f22cb065` | 252 KB |
| user-avatar (6).png | 睡着（闭眼 + Z） | 417×447 | 34.0% | `e38b930dda6195e1` | 240 KB |
| user-avatar (7).png | 慌张（头顶竖线） | 425×434 | 32.7% | `c39cdedfcbfe4cb6` | 246 KB |

> 小羊这 7 张与狐狸那 7 张**按同一套表情词表一一对应**（平静 / 大笑 / 思考 / 疑问 / 委屈 / 睡着 / 慌张）。
> 上一版清单里登记的 `视觉资产/成品素材/通知与头像/yeqingxu_avatar_idle_v01.png`
> **本次全工作区搜索已不存在**（该目录下现在只剩 `_原始生成/`）—— 已被用户提供的成品素材取代，不再登记。

### 2.3 聊天表情包 `聊天/表情包/`（32 张 · 36.60 MB）

#### 2.3.1 无配文 20 张 —— **已接入原型**

| 源文件 | 原型键名 | 中文标签 | 分组 | SHA-256(前16) | 体积 |
|---|---|---|---|---|---|
| 01-fox-cry-lamb-laugh.png | `duo-cry-laugh` | 叶青栩哭 · 小羊笑 | 双人 | `ae7a5a4ebfcc0c8a` | 953 KB |
| 02-fox-sleep-lamb-alarm.png | `duo-sleep-alarm` | 叶青栩睡 · 小羊叫早 | 双人 | `f43a3e650ca288fa` | 1109 KB |
| 03-fox-panic-lamb-tea.png | `duo-panic-tea` | 叶青栩慌 · 小羊递茶 | 双人 | `aa9858dc5abc54e6` | 1026 KB |
| 04-fox-smug-lamb-facepalm.png | `duo-smug-facepalm` | 叶青栩得意 · 小羊捂脸 | 双人 | `5759f90ed48ea76e` | 1281 KB |
| 05-fox-beg-lamb-ignore.png | `duo-beg-ignore` | 叶青栩求 · 小羊不理 | 双人 | `c61ae8e6b7e7e217` | 1268 KB |
| 06-fox-hide-lamb-protect.png | `duo-hide-protect` | 叶青栩躲 · 小羊罩着 | 双人 | `90264ca2b380d982` | 1071 KB |
| 07-fox-dance-lamb-deadpan.png | `duo-dance-deadpan` | 叶青栩嗨 · 小羊面无表情 | 双人 | `de3cc844faa4b884` | 1312 KB |
| 08-fox-hungry-lamb-snack.png | `duo-hungry-snack` | 叶青栩饿 · 小羊投喂 | 双人 | `435600c6318dfbd0` | 1237 KB |
| fox-cheer.png | `fox-cheer` | 叶青栩 · 欢呼 | 叶青栩 | `6a9503d01aa9838a` | 1077 KB |
| fox-confused.png | `fox-confused` | 叶青栩 · 疑惑 | 叶青栩 | `2f3e967a23eb7e65` | 1141 KB |
| fox-ok.png | `fox-ok` | 叶青栩 · 没问题 | 叶青栩 | `0fa3779987c278c9` | 1184 KB |
| fox-speechless.png | `fox-speechless` | 叶青栩 · 无语 | 叶青栩 | `ddb62f912f518771` | 1147 KB |
| fox-surprised.png | `fox-surprised` | 叶青栩 · 惊讶 | 叶青栩 | `a10ac45b362f91b2` | 1181 KB |
| fox-wave.png | `fox-wave` | 叶青栩 · 挥手 | 叶青栩 | `eeb3894d8d980592` | 1223 KB |
| lamb-cheer.png | `lamb-cheer` | 小羊 · 欢呼 | 小羊 | `b55db77d0b4a31ec` | 1238 KB |
| lamb-confused.png | `lamb-confused` | 小羊 · 疑惑 | 小羊 | `208c4793c2346068` | 1262 KB |
| lamb-ok.png | `lamb-ok` | 小羊 · 没问题 | 小羊 | `f98fecb17b15484a` | 1309 KB |
| lamb-speechless.png | `lamb-speechless` | 小羊 · 无语 | 小羊 | `80987fbcca4bdebe` | 1267 KB |
| lamb-surprised.png | `lamb-surprised` | 小羊 · 惊讶 | 小羊 | `875d30b80ec63017` | 1235 KB |
| lamb-wave.png | `lamb-wave` | 小羊 · 挥手 | 小羊 | `1a3c45c68d1e96ff` | 1275 KB |

#### 2.3.2 有配文 12 张 —— **已接入（原型里的分组名 = 「配文」）**

⚠️ **用户给的源文件名与画面/字幕对不上（部分错位）**，例如 `01-lamb-you-continue-captioned.png`
画面其实是「叶青栩 + 字幕 好的」。
→ **接入时按"看图核对过的字幕"重新命名**（下表左二列），**源文件名一律不要相信**。

| 源文件（名字不可信） | 接入后的键名 | 画面 | 图上的字幕 | SHA-256(前16) | 体积 |
|---|---|---|---|---|---|
| 01-lamb-you-continue-captioned.png | `cap-okay` | 叶青栩 · 眯眼微笑 | **好的** | `f20a90c88aa1e2ef` | 1052 KB |
| 02-fox-goodnight-captioned.png | `cap-help` | 叶青栩 · 慌乱出汗 | **救命** | `bb0b668e961e6f14` | 1075 KB |
| 03-fox-help-captioned.png | `cap-no-way` | 小羊 · 惊讶张嘴 | **不是吧** | `2f48abb7c852a9c5` | 1231 KB |
| 04-fox-laugh-captioned.png | `cap-laugh` | 叶青栩 · 大笑流泪 | **哈哈** | `08afe5ea5309dc0f` | 1064 KB |
| 05-fox-received-captioned.png | `cap-received` | 叶青栩 · 开心 | **收到** | `f18a60ae7bc6f06f` | 1276 KB |
| 06-fox-speechless-captioned.png | `cap-speechless` | 叶青栩 · 举牌无语 | **无语** | `643f5fa49b72a7e9` | 1100 KB |
| 07-fox-thanks-captioned.png | `cap-thanks` | 小羊 · 开心 | **谢谢** | `0821535f0ad2ce62` | 1142 KB |
| 08-lamb-hard-work-captioned.png | `cap-hard-work` | 小羊 · 喝茶 | **辛苦了** | `69d84bfbeb1333ac` | 1168 KB |
| 09-lamb-let-me-see-captioned.png | `cap-you-continue` | 小羊 · 温柔微笑 | **你继续** | `0076deaa0475ad8a` | 1149 KB |
| 10-lamb-no-thanks-captioned.png | `cap-no-thanks` | 小羊 · 闭眼拒绝 | **不约** | `d0d31855cbb96045` | 1117 KB |
| 11-lamb-no-way-captioned.png | `cap-goodnight` | 叶青栩 · 枕着月亮睡 | **晚安** | `b68e6d740891bb5e` | 1117 KB |
| 12-lamb-okay-captioned.png | `cap-let-me-see` | 小羊 · 举放大镜 | **让我看看** | `653fae65b02831a7` | 1173 KB |

> 画面归属：`cap-okay / cap-help / cap-laugh / cap-received / cap-speechless / cap-goodnight` 是**叶青栩**；
> `cap-no-way / cap-thanks / cap-hard-work / cap-you-continue / cap-no-thanks / cap-let-me-see` 是**小羊**。
> 与 2.3.1 的 20 张相比，这 12 张是**同一画风 + 底部烧入了一句中文**，定位更像"可以直接发出去的回话"。
> **2026-09-19 已接入**（用户确认「追加成新的一组」），表情包页在「小羊」之后多出一个「**配文 12 张**」段落。

> ⚠️ **这两组表情包源图都是"白底、没有 alpha 通道"**（四角纯白、白底占画面七成），
> 而叶青栩和小羊**本身就大面积是白的** —— 所以**不能全局抠白**，会把它们的身体抠漏。
> 生成器用的是「只吃与画面四边连通的那片白」的办法（详见第五节）。

---

## 三、已接入原型的素材 `prototype/assets/real/`（51 个文件 · 3.63 MB）

**这些是"处理后的产物"**，可由 `python tools/gen-assets.py` 从 `assets/_inbox/` 重跑得到，
所以此处登记体积/尺寸，不重复登记 SHA-256。

| 占位代码 | 用途 | 产出文件 | 尺寸 | 格式 | 体积 |
|---|---|---|---|---|---|
| `FOX_CHAT_AVATAR` | 叶青栩聊天头像（AI 一侧） | `fox-chat-avatar.png` + 7 个状态 | 256×256 | PNG-RGBA 真透明 | 77–83 KB |
| `USER_AVATAR` | 小羊头像（"我"这一侧） | `user-avatar.png` + 6 个状态 | 256×256 | PNG-RGBA 真透明 | 89–98 KB |
| `SHEEP_CHARACTER_RESERVED` | **人人星**首页星卡（左卡） | `sheep-home-card-day/night.jpg` | 720×633 | JPEG | 63 / 68 KB |
| `FOX_HOME_CHARACTER` | **小机星**首页星卡（右卡） | `fox-home-card-day/night.jpg` | 720×633 | JPEG | 65 / 62 KB |
| `STICKER_PACK` | 表情包 | `stickers/*.png` **32 张**（双人 8 / 叶青栩 6 / 小羊 6 / **配文 12**） | 256×256 | PNG-RGBA 真透明 | 2.11 MB |

**状态词表**（`assets/_inbox/<基础名>-<state>.png`，state 名就是这套）：

| state | 含义 | 叶青栩 | 小羊 |
|---|---|---|---|
| `idle` | 平静（**同时是兜底图**） | ✓（基础名） | ✓（基础名） |
| `happy` | 开心 / 大笑 | ✓ | ✓ |
| `think` | 思考中 | ✓ | ✓ |
| `confused` | 疑惑 / 没听懂 | ✓ | ✓ |
| `sad` | 委屈 / 难过 | ✓ | ✓ |
| `sleep` | 睡着 | ✓ | ✓ |
| `panic` | 慌张 / 手忙脚乱 | ✓ | ✓ |
| `work` | 干活中 | ✓（借 `panic` 那张，无正脸"在忙"素材） | — |

**什么情况会换哪张脸**（页面逻辑，不是素材本身）：

- 叶青栩：`思考(think) → 干活(work) → 说话(talk=兜底) → 开心(happy)`，由 `runTurn()` 按顺序演一遍。
- 小羊（用户侧）：**离线 / 断网 → `sleep`；上一条没发出去 → `sad`；其余 `idle`。**

---

## 四、仍是占位的素材（10 个代码）

| 占位代码 | 用途 | 出现位置 |
|---|---|---|
| `FOX_SPLASH_CHARACTER` | 开屏页 · 蓝狐狸角色 | 入口页 · logo 动画后左侧 |
| `SHEEP_SPLASH_CHARACTER` | 开屏页 · 绿羊角色 | 入口页 · logo 动画后右侧 |
| `FOX_NOTIFICATION_AVATAR` | 叶青栩通知头像 | 通知与弹窗 / 设置页账号 |
| `FOX_STATE_EMOTION` | 叶青栩状态表情 | 聊天页 · 空状态 |
| `FOX_PIXEL_SPRITE` | 叶青栩像素小人 | 小机星页 · 像素场景（当前纯色块拼） |
| `MEMORY_EMPTY_ILLUSTRATION` | 记忆空状态插画 | 记忆库页 · 空状态 |
| `CONNECTION_SUCCESS_ILLUSTRATION` | 连接成功插画 | 连接成功页 · 顶部 |
| `OFFLINE_ILLUSTRATION` | 离线状态插画 | 首页离线区 / 聊天页离线条 |
| `EARTH_STATE` / `AI_WORLD_STATE` | 两颗星球素材 | **当前未放置**（小机星页已改为像素场景） |

> 顺带说明：`FOX_HOME_CHARACTER` / `SHEEP_CHARACTER_RESERVED` / `STICKER_PACK` 的**兜底图**仍是占位 SVG，
> 但它们**实际用到的状态图（日/夜、20 张表情）都已经是真图**，所以不列在上表。

---

## 五、素材接入规则（换图不用改页面代码）

**通道**：把文件放进 `prototype/assets/_inbox/`，跑 `python tools/gen-assets.py`。
页面代码**一行都不用动**（页面通过 `assets/_manifest.js` 这个清单按代码取图）。

| 素材类型 | 生成器自动做的事 |
|---|---|
| **透明底**（带 alpha） | 颜色向外"渗"一圈**防黑边** → 补**正方形**透明画布居中 → 存 **PNG** |
| **不透明整幅图** | 不留方形白边 → 存 **JPEG(q84 progressive)**（2MB → 约 65KB） |
| **alpha 通道坏掉** | 判据「全透明 < 0.5% 且 全不透明 < 1%」→ **拍平为不透明**并打印提示 |
| **白底无 alpha 的表情包** | **只吃与四边连通的那片白**（膨胀 ∩ 白底掩膜），被轮廓围住的白保留 → 裁主体外框 → 补正方 → 留 7% 边 → 缩到 256px |
| **首页星卡整幅插画** | `CARD_COMPOSE` 按代码登记：**左右翻转** + **缩到 92% 居中** + 四周用最外一圈像素向外拉伸补齐（防止 18px 圆角把太阳/月亮啃掉） |
| 尺寸上限 | `REAL_MAX_SIDE`：头像 **256** / 星卡 **720** / 像素图 **None（绝不缩放，会糊）** |

**命名铁律**：`<基础名>.png` 是兜底图；`<基础名>-<state>.png` 是按状态换图 —— **`-` 后面是状态名，不是版本号**。

---

## 六、关键结论

1. **锚点 3 张未改动**（SHA-256 与首版一致），仍为「待确认」，只作参考、不直接进产品。
2. 用户已提供 **55 个成品素材文件（49.62 MB）**，覆盖 首页星卡 / 聊天头像 / 小羊头像 / 表情包 四类。
3. **已接入原型的 5 个位置**：`FOX_CHAT_AVATAR`(8 图) / `USER_AVATAR`(7 图) / `SHEEP_CHARACTER_RESERVED`(昼夜 2 图) /
   `FOX_HOME_CHARACTER`(昼夜 2 图) / `STICKER_PACK`(**32 图**)，处理产物合计 **3.63 MB**。
4. **12 张"有配文"表情包已于 2026-09-19 接入**（用户确认「追加成新的一组」，**不替换**原有 20 张）：
   按字幕重命名后键名为 `cap-*`，原型里的分组名 = 「**配文**」，排在「双人 → 叶青栩 → 小羊」之后。
   ⚠ 源文件名与画面/字幕错位，接入前的逐张核对记录见 §2.3.2，**不要按源文件名推断内容**。
5. 仍是占位的 **10 个代码**（开屏角色、通知头像、状态表情、像素小人、三张插画、两颗星球）—— 等素材。
6. **发布时不要把 `prototype/assets/_inbox/` 带上去**：它只是收件箱（**52 个文件 / 48.49 MB**，
   装着表情包与星卡的原始大图），页面完全不引用它。做法 = 发布前移出、发布后放回，
   并实测线上返回 404（2026-09-19 两次发布都按此执行并通过）。
