# 画像织谱 (ProfileWeaver)

`astrbot_plugin_profile_weaver` 是一个更安全的用户画像记忆插件。它基于上游项目 [Luna-channel/astrbot_plugin_soulmap](https://github.com/Luna-channel/astrbot_plugin_soulmap) 做了重构式 fork，并且已经更换插件名、显示名、数据目录和代码标识符，用来避免与原插件并装时发生冲突。

## 上游说明

- 上游项目：[`Luna-channel/astrbot_plugin_soulmap`](https://github.com/Luna-channel/astrbot_plugin_soulmap)
- 本 fork 的目标不是“轻微改皮”，而是把原本依赖隐藏标签 `[Profile: ...]` / `[ProfileDelete: ...]` 的写入方式，升级成 AstrBot 推荐的 `FunctionTool` 工作流。
- 插件目录名和 `metadata.yaml` 里的 `name` 已改为 `astrbot_plugin_profile_weaver`，避免和原插件的 `astrbot_plugin_soulmap` 冲突。

## 这版做了什么

- 改成显式 LLM 工具：画像增删改不再靠隐藏标签，而是通过 `FunctionTool` 直接操作。
- 支持 LLM 自己扩展画像字段：当现有字段确实不够表达时，LLM 可以为“当前用户”创建专属自定义字段。
- 自定义字段按用户隔离：不是全局乱加字段，而是每个用户各自维护，避免字段污染整个画像系统。
- 增加身份护栏：只有当前消息发送者明确在说“自己”时，才允许 LLM 写入画像。
- 增加审计日志：每次画像变更都会记录操作者、来源、前后值，便于管理员追踪误写和恶意利用。
- 增加手动指令：用户可以自己设置/删除画像；管理员可以修改、删除、清空其他人的画像。
- 真正自动兼容旧插件目录：会主动探测 `data/plugin_data/astrbot_plugin_soulmap/user_profiles.json` 这类旧目录数据，并做一次性签名迁移与字段级合并，不要求你先手工拷文件。
- 增加低开销自动提取：如果主对话这轮没主动调用画像工具，但当前消息很像“高置信自述”，插件会额外跑一个极短的后台工具循环补提取。

## 为什么比上游更稳

原插件最大的风险，是让 LLM 在自然回复里偷偷输出隐藏标签，然后插件再去解析这些标签修改画像。这样会把“模型有没有理解对当前说话人”这个问题直接变成数据写入问题。

这版的策略是：

- LLM 只能通过 `profileweaver_*` 工具改画像。
- 工具要求提供 `evidence`，而且这段证据必须能在当前用户本轮消息里直接找到。
- 如果当前消息同时提到其他人、@ 群友、转述别人，却没有明确自述，工具会拒绝写入。
- 如果当前消息提到了别人，那么 `evidence` 本身也必须带有明确自述，避免截取出“喜欢猫”“生日是 1 月”这种会写错对象的歧义片段。
- LLM 默认只能修改“当前消息发送者”的画像，不能借工具顺手把别人记混。
- 删除和更正也会走同样的校验链路。

这不能保证所有模型在任何提示词攻击下都 100% 完美，但已经把风险从“模型说错一句就写脏数据”，收敛成“工具侧二次判定，不符合条件就拒绝执行”。

## 功能概览

### 1. 用户画像字段

默认内置字段：

- 昵称
- 性别
- 年龄
- 所在地
- 生日
- 爱吃
- 忌口
- 爱好
- 职业
- 重要节日
- 恐惧/弱点
- 作息规律
- 技能水平
- 健康状况
- 宠物
- 备注

除此之外，LLM 或用户命令还可以为当前用户新增自定义字段，比如：

- 学校
- MBTI
- 常用语言
- 追番偏好

### 2. LLM 工具

插件会向 AstrBot 注册 3 个工具：

- `profileweaver_view_profile`
  - 查看当前发送者的画像摘要、基础字段和已有自定义字段。
- `profileweaver_remember_field`
  - 写入或更新当前发送者的画像。
- `profileweaver_forget_field`
  - 删除当前发送者的一条画像字段，或删除某条备注。

### 3. 自动提取现在是什么策略

和上游那种“靠聊天里顺手打隐藏标签”的模式不同，这版自动提取是一个**后置、补充型**流程：

- 先让主对话正常回复。
- 如果主对话这轮已经自己调用了画像工具，就不再补第二次。
- 只有当当前消息像“明确在介绍自己”的短消息时，才会额外触发一次小型工具循环。
- 这次补提取只看当前用户本轮消息，不带长历史，默认最多 2 步，所以 token 开销是**小幅增加，但不是零**。
- 如果消息太长、像命令、像转述、像多人物对话，或者风险偏高，就直接跳过，不为了“多记一点”去牺牲安全性。

## 指令

### 用户指令

| 指令 | 说明 | 示例 |
| --- | --- | --- |
| `我的画像` | 查看自己的画像 | `我的画像` |
| `画像字段` | 查看当前可用字段 | `画像字段` |
| `设置画像 <字段> <内容>` | 手动设置自己的画像字段 | `设置画像 学校 复旦` |
| `删除画像 <字段>` | 删除自己的某个字段 | `删除画像 学校` |
| `删除画像 备注:2` | 删除自己的第 2 条备注 | `删除画像 备注:2` |
| `清空画像` | 清空自己的画像 | `清空画像` |

### 管理员指令

| 指令 | 说明 | 示例 |
| --- | --- | --- |
| `查询画像 <用户ID>` | 查看指定用户画像 | `查询画像 12345` |
| `修改画像 <用户ID> <字段> <内容>` | 修改或新增指定用户画像字段 | `修改画像 12345 学校 复旦` |
| `删除画像字段 <用户ID> <字段>` | 删除指定用户某个字段 | `删除画像字段 12345 学校` |
| `清空用户画像 <用户ID>` | 清空指定用户画像 | `清空用户画像 12345` |
| `画像审计 <用户ID> [条数]` | 查看最近变更日志 | `画像审计 12345 5` |
| `画像统计` | 查看系统画像覆盖情况 | `画像统计` |

## 配置项

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| `session_based` | 是否按会话隔离画像 | `false` |
| `default_fields` | 默认基础字段列表 | 见上文 |
| `max_notes_count` | 备注保留条数 | `5` |
| `llm_tools_enabled` | 是否启用 LLM 工具 | `true` |
| `proactive_extraction_enabled` | 是否启用低开销自动提取 | `true` |
| `proactive_extraction_min_message_length` | 自动提取最短消息长度 | `4` |
| `proactive_extraction_max_message_length` | 自动提取最长消息长度 | `120` |
| `proactive_extraction_max_steps` | 自动提取最大工具步数 | `2` |
| `allow_llm_custom_fields` | 是否允许 LLM 为当前用户创建自定义字段 | `true` |
| `allow_user_custom_fields` | 是否允许用户通过命令创建自定义字段 | `true` |
| `strict_identity_guard` | 是否启用“当前说话人身份护栏” | `true` |
| `custom_field_name_max_length` | 自定义字段最大长度 | `16` |
| `field_value_max_length` | 单字段值最大长度 | `160` |
| `allow_profile_in_group` | 是否允许在群聊里查看 `我的画像` | `false` |
| `group_profile_denied_msg` | 群聊查看画像时的拒绝提示 | 自带默认值 |
| `profile_prompt_template` | 注入到 LLM 的画像提示模板 | 自带默认值 |
| `debug_log_level` | 插件调试日志级别 | `INFO` |

## 安全建议

如果你更在意安全性而不是画像丰富度，推荐这样配：

- `strict_identity_guard = true`
- `proactive_extraction_enabled = true`
- `proactive_extraction_max_steps = 1` 或 `2`
- `allow_llm_custom_fields = false`
- `allow_user_custom_fields = true`
- `allow_profile_in_group = false`

这样会让 LLM 更难写脏数据，但用户和管理员依旧可以通过命令补充画像。

## 数据文件

插件数据保存在 `data/plugin_data/astrbot_plugin_profile_weaver/` 下，主要包括：

- `profiles.json`：画像主数据
- `audit_log.jsonl`：画像变更审计日志
- `migration_state.json`：旧插件目录导入状态与签名记录，避免每次启动都重复迁移

## 兼容与迁移

- 如果旧插件目录里存在 `user_profiles.json`，新版会主动探测并自动导入，兼容常见目录名如 `astrbot_plugin_soulmap` / `SoulMap` / `soulmap`。
- 迁移不是简单覆盖，而是做字段级合并：较新的字段优先保留，`备注` 会做去重合并。
- 新版默认不再依赖 `[Profile: ...]` 或 `[ProfileDelete: ...]` 隐藏标签。
- 如果你之前给上游插件写过专门的标签提示词，请一起移除，避免模型继续输出已经失效的标记。
