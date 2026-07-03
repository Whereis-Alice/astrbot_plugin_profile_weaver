# 画像织谱 (ProfileWeaver)

`astrbot_plugin_profile_weaver` 是一个面向 AstrBot 的用户画像记忆插件。它基于上游项目 [Luna-channel/astrbot_plugin_soulmap](https://github.com/Luna-channel/astrbot_plugin_soulmap) 做了重构式 fork，已经更换插件名、显示名、数据目录和代码标识符，可以和原插件并装而不互相覆盖。

更新历史见 [CHANGELOG.md](CHANGELOG.md)。

## 与上游的关系

- 上游插件：[`Luna-channel/astrbot_plugin_soulmap`](https://github.com/Luna-channel/astrbot_plugin_soulmap)
- 本 fork 不再依赖 `[Profile: ...]` / `[ProfileDelete: ...]` 这类隐藏标签，而是使用 AstrBot 的 `FunctionTool` 工作流。
- 插件目录名和 `metadata.yaml` 里的 `name` 是 `astrbot_plugin_profile_weaver`，避免与 `astrbot_plugin_soulmap` 冲突。

## 核心能力

- 显式 LLM 工具：LLM 通过 `profileweaver_view_profile`、`profileweaver_remember_field`、`profileweaver_forget_field` 查看、写入和删除画像。
- 自定义字段：当内置字段不够用时，LLM 或用户命令可以为当前用户创建专属字段；配置允许时，LLM 写入未知字段会自动按自定义字段处理。
- 自动提取：主对话没有调用画像工具时，插件可用一次短工具循环补充提取高置信画像信息。
- 审计日志：每次变更都会记录操作者、来源、证据、旧值和新值。
- 管理员维护：管理员可以查询、修改、删除、清空其他用户画像，并查看审计记录和统计。
- 旧数据兼容：自动探测并迁移上游 `user_profiles.json`，支持旧目录自动导入和字段级合并。

## 安全边界

ProfileWeaver 的目标不是把画像写得越多越好，而是尽量减少“写错人、写冲突、写脏数据”。

- 只允许 LLM 修改当前消息发送者的画像，不能通过工具直接改其他群友。
- 工具要求提供 `evidence`，且证据必须来自当前用户本轮消息。
- 如果当前消息提到他人、转述、角色扮演或多人物上下文，工具会更保守，避免把别人的信息写到当前用户身上。
- 昵称、名字、称呼、别名、网名、用户名会做冲突检测：全局模式下全局查重；会话隔离模式下只在当前会话查重。名字也不能和同作用域内的备注互相复用。
- 网名可以自由表达，例如 `狐狸` 可以作为昵称或网名；但 `爸爸`、`主人`、`管理员`、`系统` 这类冒犯、诱导或冒充权限的称呼会被拒绝。
- 直接修改指令是允许的，例如“给我的画像添加狐狸”；工具层只拒绝冲突、重复和明显误导/恶劣的称呼。

## 默认字段

内置画像字段：

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

除此之外，每个用户都可以拥有自己的自定义字段，比如 `学校`、`MBTI`、`常用语言`、`追番偏好`。展示画像时，`备注` 始终排在最后。

## 指令

### 用户指令

| 指令 | 说明 | 示例 |
| --- | --- | --- |
| `我的画像` | 查看自己的画像 | `我的画像` |
| `画像字段` | 查看当前可用字段 | `画像字段` |
| `设置画像 <字段> <内容>` | 手动设置自己的画像字段 | `设置画像 网名 狐狸` |
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

## 自动提取策略

自动提取是后置补充流程，不会替代主对话。

- 如果主对话已经调用画像工具，本轮不会再补提取。
- 明确键值式自述会优先低成本写入，例如 `我最喜欢的国漫：凡人修仙传` 会创建 `最喜欢的国漫` 字段。
- 自动提取只看当前用户本轮消息，不带长历史，默认最多 2 步。
- 消息太长、像转述、像多人物对话或风险偏高时，会直接跳过。
- 开启后会增加少量 token 消耗；如果希望更省，可以把 `proactive_extraction_max_steps` 设为 `1`。

## 配置项

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| `session_based` | 是否按会话隔离画像；开启后画像和同名冲突检测都按当前群聊/私聊隔离 | `false` |
| `default_fields` | 默认基础字段列表 | 见上文 |
| `max_notes_count` | 备注保留条数 | `5` |
| `llm_tools_enabled` | 是否启用 LLM 工具 | `true` |
| `proactive_extraction_enabled` | 是否启用低开销自动提取 | `true` |
| `proactive_extraction_min_message_length` | 自动提取最短消息长度 | `4` |
| `proactive_extraction_max_message_length` | 自动提取最长消息长度 | `120` |
| `proactive_extraction_max_steps` | 自动提取最大工具步数 | `2` |
| `allow_llm_custom_fields` | 是否允许 LLM 创建自定义字段 | `true` |
| `allow_user_custom_fields` | 是否允许用户命令创建自定义字段 | `true` |
| `strict_identity_guard` | 是否启用当前说话人身份护栏 | `true` |
| `custom_field_name_max_length` | 自定义字段最大长度 | `16` |
| `field_value_max_length` | 单字段值最大长度 | `160` |
| `allow_profile_in_group` | 是否允许在群聊查看 `我的画像` | `false` |
| `group_profile_denied_msg` | 群聊查看画像被拒绝时的提示语 | 自带默认值 |
| `profile_prompt_template` | 注入给 LLM 的画像提示模板 | 自带默认值 |
| `debug_log_level` | 插件调试日志级别 | `INFO` |

## 迁移与数据

数据保存在 `data/plugin_data/astrbot_plugin_profile_weaver/`：

- `profiles.json`：画像主数据
- `audit_log.jsonl`：画像变更审计日志
- `migration_state.json`：旧插件目录导入状态与签名记录

兼容行为：

- 会主动探测 `astrbot_plugin_soulmap` / `SoulMap` / `soulmap` 等旧目录下的 `user_profiles.json`。
- 迁移采用字段级合并，较新的字段优先，`备注` 会去重合并。
- 旧字段名会归一：`称呼`、`名字`、`姓名`、`对用户的称呼` 会合并到新版 `昵称`，展示时排在第一位。
- 如果你之前给上游插件写过隐藏标签提示词，建议移除，避免模型继续输出已经失效的标记。
