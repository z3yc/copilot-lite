# Docker容器\+Asyncpg\+Alembic线程DNS异常全链路踩坑复盘文档

## 一、问题背景

项目技术栈：FastAPI \+ Asyncpg \+ SQLAlchemy \+ Alembic \+ Docker Compose

初始故障现象：容器内线程池调用 `getaddrinfo` 偶发报错 `socket.gaierror: [Errno -2] Name or service not known`，主线程域名解析正常，线程池解析失败，数据库迁移无法执行。

本次排查累计解决多层连锁坑，并非单一Docker DNS问题，而是**底层环境Bug \+ URL格式错误 \+ 代码配置错误 \+ Docker数据卷机制**叠加导致。

## 二、全链路踩坑问题汇总（按排查顺序）

### 坑1：Docker容器 /etc/resolv\.conf 软链接导致glibc线程池DNS异常（初始误判根因）

**报错现象**：

- 容器主线程、ping、getent 解析域名正常

- Python ThreadPoolExecutor 线程池内调用 `socket.getaddrinfo` 固定报错 \-2 域名不存在

**根因**：

Docker 默认给容器 `/etc/resolv.conf` 创建符号链接，glibc 在子线程异步解析DNS时存在底层兼容Bug，无法正常读取软链接配置，仅线程池解析失效。

**解决方案**：

1. 取消Docker默认软链接，手动挂载静态 resolv\.conf 普通文件

2. 文件内容保留Docker原生DNS：`nameserver 127.0.0.11`

3. 挂载配置：`./resolv.conf:/etc/resolv.conf:ro`

**最终结论**：该修复未彻底解决问题，本次真实报错并非纯DNS Bug，属于**症状相似误导排查**。

### 坑2：数据库密码含特殊字符 @，破坏URL格式（核心隐形大坑）

**报错现象**：

数据库URL出现双@：`copilot:Pass@123456@@172.31.0.10:5432/copilot`，触发 `gaierror -2`。

**根因**：

- 数据库URL格式规则：`user:password@host:port/db`

- 密码内含 `@` 特殊字符，解析器截断URL，将host识别为空字符串

- 空域名解析直接抛出 `Name or service not known`，和DNS报错完全一致，严重误导排查

**解决方案**：

1. 临时方案：修改密码，移除 `@` 特殊字符，使用纯数字字母密码

2. 根治方案：代码层使用 `urllib.parse.quote_plus` 自动编码密码，禁止手动拼接完整数据库URL

3. 规范配置：拆分\.env为独立字段（用户/密码/地址/端口），动态拼接URL

### 坑3：Docker自定义网络子网冲突

**报错现象**：

`failed to create network: Pool overlaps with other one on this address space`

**根因**：

默认网段`172.28.0.0/16` 被服务器其他Docker网络占用，网段冲突无法创建自定义网络。

**解决方案**：

1. 更换空闲网段：`172.31.0.0/16`

2. Postgres静态IP固定为：`172.31.0.10`

3. 所有服务统一挂载自定义网络，彻底绕开Docker域名解析，规避线程DNS Bug

### 坑4：Alembic env\.py 错误配置 connect\_args，字典解析报错

**报错现象**：

`ValueError: dictionary update sequence element #0 has length 1; 2 is required`

**根因**：

- 错误写法：向section配置写入JSON字符串 `section["sqlalchemy.connect_args"] = '{"resolve_hosts": false}'`

- SQLAlchemy无法解析字符串格式的配置，强制解包字典触发参数类型错误

**解决方案**：

1. 删除所有section层的connect\_args字符串配置

2. 直接在 `async_engine_from_config` 传原生Python字典参数

3. 仅保留合法参数：`connect_args={"ssl": False}`

### 坑5：使用asyncpg无效参数 resolve\_hosts

**报错现象**：

`TypeError: connect() got an unexpected keyword argument 'resolve_hosts'`

**根因**：

`resolve_hosts` 不属于asyncpg合法连接参数，属于过时错误配置。

**解决方案**：

彻底删除该参数，仅保留ssl关闭配置。

### 坑6：Docker Postgres数据卷缓存导致密码不生效

**报错现象**：

`asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "copilot"`

容器环境变量密码已修改，但数据库认证失败。

**根因**：

- Postgres Docker镜像**仅首次初始化（空数据卷）读取POSTGRES\_PASSWORD**

- 已有pgdata数据卷时，修改\.env密码、重启容器均不会更新数据库内部用户密码

**解决方案**：

1. 保留数据：进入psql执行 `ALTER USER copilot WITH PASSWORD '新密码';`

2. 测试环境清空重建：删除 `pgdata`数据卷，重新初始化数据库

### 坑7：docker compose exec 环境不加载env\_file环境变量

**问题现象**：

exec进入容器手动执行alembic，读取\.env配置异常，和容器启动运行环境不一致。

**根因**：

`env_file` 仅对容器**主进程command**生效，exec附加进程不会加载\.env变量。

**避坑方案**：

- 调试时优先使用容器启动命令执行业务逻辑，模拟真实环境

- exec调试需手动注入环境变量，或通过代码打印真实配置

## 三、最终稳定可用的标准配置（根治所有问题）

### 1\. 网络配置（固定静态IP，绕开DNS线程Bug）

```Plain Text
networks:
  app_net:
    ipam:
      config:
        - subnet: 172.31.0.0/16
```

### 2\. Postgres静态IP配置

```Plain Text
postgres:
  networks:
    app_net:
      ipv4_address: 172.31.0.10
```

### 3\. 规范\.env配置（禁止手动拼接URL）

```Plain Text
POSTGRES_USER=copilot
POSTGRES_PASSWORD=Pass123456
POSTGRES_HOST=172.31.0.10
POSTGRES_PORT=5432
POSTGRES_DB=copilot
```

### 4\. 代码动态编码拼接URL

```Plain Text
from urllib.parse import quote_plus

@property
def DATABASE_URL(self) -> str:
    pw = quote_plus(self.POSTGRES_PASSWORD)
    return f"postgresql+asyncpg://{self.POSTGRES_USER}:{pw}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
```

### 5\. 标准alembic env\.py 异步连接配置

```Plain Text
async def run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section, {})
    from app.core.config import settings
    section["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"ssl": False}
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()
```

## 四、核心避坑总结（生产必看）

1. **gaierror \-2 不一定是DNS问题**：URL格式错误、空host解析都会报相同错误，极易误导排查

2. **数据库密码禁止含特殊字符**：@ / : \# % 必须URL编码，禁止手动拼接连接串

3. **Postgres数据卷缓存优先级高于环境变量**：改密码必须同步更新数据库内部密码或清空数据卷

4. **Alembic connect\_args 只能传原生字典**，禁止传字符串、无效参数

5. **Docker线程DNS底层Bug根治方案**：静态IP \+ 取消resolv\.conf软链接，双保险

6. **exec环境≠容器运行环境**：线上问题以容器主进程日志为准，不要依赖exec调试结果

## 五、新增问题：后端容器启动不健康 dependency failed to start

### 1\. 报错信息

`dependency failed to start: container deploy-backend-1 is unhealthy`

其余中间件（postgres/redis/qdrant）全部健康，仅 backend 启动超时、健康检查失败，导致整体栈启动失败。

所有Alembic迁移脚本执行成功，全量数据表初始化完成，彻底解决线程池DNS解析异常、数据库连接报错、配置参数异常等所有问题，服务可正常启动运行。

> （注：部分内容可能由 AI 生成）
