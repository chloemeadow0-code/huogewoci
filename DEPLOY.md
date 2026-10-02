# 雾梣学期：云端部署

这一版参考 [潮汐岛 allotment-relay](https://github.com/sue1231511/allotment-relay) 的部署与接入结构：
一个服务运行一个共享世界，网页领取凭证，人和 AI 使用独立账号，Streamable HTTP MCP，
SQLite 持久卷，平台 `PORT` 与 `/health`。实现保留 LoreKit 的存档、NPC 记忆、区域和时钟，
新增代码独立实现；没有复制潮汐岛 NPC、剧情或游戏代码，也不修改潮汐岛仓库。

## Zeabur

把这个项目目录作为一个 GitHub 仓库的根目录部署，Zeabur 自动读取根 `Dockerfile`。
若放进另一个仓库的子目录，把 Root Directory 设为该目录（例如 `outputs/lorekit`）。
部署压缩包 `hogwarts-deploy.zip` 解压后，其根目录就是这里的部署根。

1. 在 Zeabur 新建服务，连接上传了本项目的 GitHub 仓库。
2. 创建持久卷，挂载点 **`/app/server/data`**。
3. 添加域名，填写以下环境变量，再启动 / 重新部署。
4. 检查 `/health` 返回 `status: ok`，打开 `/register` 领凭证，再打开 `/play`。

| 环境变量 | 值 / 作用 |
|---|---|
| `HOST` | `0.0.0.0`，明确允许容器接受平台网络请求 |
| `PORT` | 平台注入；Docker 默认 `8080` |
| `DATA_DIR` | `/app/server/data`，与持久卷挂载点相同 |
| `MCP_ALLOWED_HOSTS` | 你的完整域名，例如 `my-hogwarts.zeabur.app`；多个域名用逗号隔开，本地带端口 |
| `MCP_ALLOWED_ORIGINS` | 对应来源，例如 `https://my-hogwarts.zeabur.app`；多个用逗号隔开 |
| `REGISTRATION_OPEN` | `true` 开放网页领取凭证；以后改 `false` 关闭注册，旧账号照常玩 |

没有配置公网域名时，程序拒绝公网监听；默认仅 `127.0.0.1`。主机校验始终开启。
平台提供 HTTPS 终止。HTTP MCP 的 `/mcp` 和 `/mcp/` 均直接响应，不经重定向。
健康检查 `/health` 可被平台探针访问，不返回学生或世界信息。
容器启动时设置数据目录所有权，随后以 UID/GID `10001` 运行服务，解决新挂载卷的写入权限。
只运行 **一个副本、一个 worker**；共享校园动作通过进程锁串行写入 SQLite。

## Docker Compose

```bash
cp .env.example .env
docker compose up -d --build
```

然后访问 `http://localhost:8080/`。
示例 `.env` 明确开启注册，端口默认只绑定本机。
持久数据在命名卷 `hogwarts-data`，普通重启和重新构建保留数据；不要删除这个卷。
服务器公网部署时配置实际域名和 HTTPS 反向代理，再按需设置 `BIND_ADDRESS`；
Zeabur 使用上节的服务网络配置即可。

不使用 Compose 的例子：

```bash
docker build -t hogwarts-mcp .
docker run -d --name hogwarts -p 127.0.0.1:8080:8080 \
  -e HOST=0.0.0.0 \
  -e MCP_ALLOWED_HOSTS=localhost:8080 \
  -e MCP_ALLOWED_ORIGINS=http://localhost:8080 \
  -e REGISTRATION_OPEN=true \
  -v hogwarts-data:/app/server/data hogwarts-mcp
```

## 本机直接运行

Windows 已有可用虚拟环境，在项目目录：

```powershell
$env:REGISTRATION_OPEN = 'true'
.\start-hogwarts.ps1 -Mode http
```

打开 `http://127.0.0.1:8080/`。
在另一台 Windows 或 Linux 机器创建新的环境：

```bash
python -m venv .venv
# Linux:
.venv/bin/python -m pip install -r systems/hogwarts/requirements-deploy.txt
REGISTRATION_OPEN=true .venv/bin/python run-hogwarts.py
# Windows: 使用 .venv\Scripts\python.exe 安装和运行；环境变量用 PowerShell 设置。
```

无需 `pip install -e .`，无需安装整个 LoreKit 的模型依赖，默认不需 LLM API key。
本机默认保存到启动工作目录的 `data/`，需要改变时设置 `DATA_DIR`。

## 人和 AI 怎么接入

1. 人打开 `/register`，填写学生名，领取人类凭证；在 `/play` 登录自己的学生。
2. 点击「创建 AI 学生」，填写另一个名字，领取独立的 AI 专用凭证。
3. 保存人类与 AI 两份凭证。创建 AI 不会切换网页账号，不会复制人类的背包或进度。
4. 将 AI 注册弹窗中的接入地址配置到 AI 客户端，类型选择 **Streamable HTTP**：
   `https://你的域名/mcp/?api_key=hw_sk_AI专用凭证`。
5. 支持请求头方式：地址 `https://你的域名/mcp/`，
   `Authorization: Bearer hw_sk_AI专用凭证`。

**服务端强制区分入口**：人类凭证访问 MCP 返回 403；AI 凭证访问网页状态 / 动作接口返回 403。
每张凭证绑定一个独立学生，账号类型创建后固定，玩家工具不能更改类型或切换身份。
账号表只保存凭证 SHA256 摘要，凭证不作为 MCP 工具参数传递。
旧版本已有凭证自动归为人类账号，名字与学生进度保留；请为 AI 新建账号。
没有自动找回凭证或将旧进度复制给 AI 的操作。

例如客户端配置（具体字段可能略有不同）：

```json
{
  "mcpServers": {
    "hogwarts": {
      "type": "http",
      "url": "https://你的域名/mcp/",
      "headers": {"Authorization": "Bearer hw_sk_AI专用凭证"}
    }
  }
}
```

网页只展示公开人物、自己的状态与已知事实，同校名册只有名字、学院和地点。
两种账号仍在同一校园生活，共用地点、物体、NPC 和叙事时钟。

## 共享校园的边界

- 全员共享地点、物体、NPC、世界时钟。某人解锁的普通练习箱，其他人也能看到已解锁。
- 每个学生的背包、金币、体力、魔咒、课程、许可、违规和已知事实独立。
- 世界时间是 **行动推进** 的叙事时间，不按真实时间自动前进。
  一位学生上课、等待或睡眠会推进整个校园时间；巡查会处理所有留在外面的学生。
- NPC 记忆共用 LoreKit 表，但按互动学生识别旧相识；玩家看不到 NPC 原始记忆。
- 存档保存整个校园。操作者回档影响全员，操作前须停服务；账号凭证表不随世界回档删除。
- 没有跨玩家交易、多人聊天、独立 LLM NPC、自定义角色或多服务副本支持。

## 接口

| 路径 | 用途 |
|---|---|
| `/`、`/register`、`/play` | 注册 / 登录与实际游玩，支持手机 |
| `/manual` | 人类校园手册 |
| `POST /api/register` | `{"name":"名字","kind":"human"}` 或 `kind:"ai"`，类型默认 human |
| `GET /api/state` | 当前凭证的公开校园视图与自己状态 |
| `POST /api/action` | `{"tool":"move","arguments":{"destination":"hall"}}`；同一套玩家规则 |
| `/mcp/` | 18 工具 Streamable HTTP MCP，需凭证 |
| `/health`、`/healthz` | 数据库可用性检查 |

游戏动作精确为：look、move、inspect、talk、ask、give、check_status、check_schedule、
check_inventory、attend_class、study、practice_spell、cast_spell、use_item、read、search、sleep、wait。
没有管理员工具，网页动作不能传入玩家 ID 来切换身份。

## 数据、验证和当前部署状态

`DATA_DIR/accounts.db` 保存凭证摘要与身份；`DATA_DIR/hogwarts.db` 保存世界、人物、记忆、
进度、分支存档。**两份都要持久化和备份**。一致性备份可停止服务后备份整个持久卷；
不要在服务运行时只复制一个 SQLite 主文件而忽略 WAL。

本次在 Windows / Python 3.12.10 实测 **35 项测试全部通过**，包含真实 stdio 和 HTTP MCP
完整 Demo、查询参数和 Bearer 两种认证、两个账号并发隔离、共享物体、个人知识、
关闭注册后旧账号续玩、重启恢复，以及共享时钟下对非当前玩家的宵禁巡查。
本机测试有两个提示：上游 D20 test_config 检测提示、Starlette 的 httpx 测试适配器弃用提示。
无测试失败或跳过。远端验证以本仓库 Actions 的实际结果为准。

现有 Chrome 的端到端检查也通过：注册、起床、移动、NPC 对话、刷新继续账号；
桌面与 390px 手机布局无横向溢出、无 JavaScript 错误。截图和本机验证报告保存在开发工作区，
不作为部署运行文件上传。

**代码已上传到 `chloemeadow0-code/huogewoci` 的 `main` 分支**。
首次提交 `747c9a6` 对应的 [GitHub Actions 检查](https://github.com/chloemeadow0-code/huogewoci/actions/runs/36987529060)
已成功：Linux 功能测试、Docker 构建、健康检查以及持久卷重启恢复均通过。
仍没有部署到公网；连接 Zeabur 后按上面的配置创建自己的服务。
本机没有 Docker / Podman，因此容器验证证据来自实际执行的云端 CI。

部署包包含上游 Apache-2.0 LICENSE / NOTICE 与所需 LoreKit 源码，不包含本机 `.venv`、
任何玩家数据库、账号凭证或本机绝对路径 MCP 配置。详细玩法见 `HOGWARTS.md` 和 `/manual`。

### 学院选择

注册页面可选四大学院。旧账号此前被默认分到拉文克劳，可通过现有玩家工具一次性确认学院：`use_item(item="admission:Hufflepuff")`。原有进度保留，确认后不能重复分院。AI 可先用 `check_status` 查看提示。
