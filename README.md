# Ant Design MCP Server (Python)

This Model Context Protocol (MCP) server fetches and structures Ant Design v4 (Chinese) component documentation into JSON so AI agents can perform analysis.

## Features
- Fetch overview page and individual component pages.
- Extract component metadata: name, description, examples.
- Classify API tables automatically (props / events / methods / other).
- Cache fetched HTML locally.
- Export all components into a single JSON file.
- MCP tools exposed over JSON-RPC stdio.

## Tools
- list_components(force?)
- get_component(name, force?)
- search_components(query)
- export_all(force?, filepath?)

## Environment Setup
Choose one method (requirements are inside `src/requirements.txt`):

### venv (built-in)
```
python -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
```

### pyenv + venv
```
brew install pyenv
pyenv install 3.11.8
pyenv local 3.11.8
python -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
```

### Conda
```
conda create -n antd-mcp python=3.11 -y
conda activate antd-mcp
pip install -r src/requirements.txt
```

## Run Server (Source Checkout)
Flat layout now exposes modules directly under `src/`:
```
python -m server
# or explicit path
python src/server.py
```

Console scripts (after install or via pipx):
```
antd-mcp --once '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
antd-mcp-server --once '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## JSON-RPC Examples
```
# List tools
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m server

# List components
echo '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_components","arguments":{}}}' | python -m server

# Get one component
echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_component","arguments":{"name":"Button"}}}' | python -m server

# Search components
echo '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"search_components","arguments":{"query":"form"}}}' | python -m server

# Export all component data
echo '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"export_all","arguments":{}}}' | python -m server
```

## Export Output
Default file: `src/exports/antd_components_all.json`
Structure:
```
{
  "generated_at": <timestamp>,
  "count": <number_of_components>,
  "components": [
    {
      "name": "Button",
      "title": "Button 按钮",
      "intro": [...],
      "props": [...],
      "events": [...],
      "methods": [...],
      "other_tables": [...],
      "table_summary": {"props":1,"events":0,...},
      "examples": [...],
      "source_url": "https://4x.ant.design/..."
    }
  ]
}
```

## TODO / Roadmap
- More precise table classification rules (column semantics).
- Parallel fetching & retry with backoff.
- Version / language (en vs cn) selection.
- CLI wrapper.
- Optional rate limiting.

## License
MIT (add if needed)

## 安装 (发布后)

```bash
pip install antd-mcp-server
# 或使用 pipx 隔离运行
pipx install antd-mcp-server
```

安装后命令行入口（两个脚本等价）：

```bash
antd-mcp --once '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
antd-mcp-server --once '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

长会话（stdin 流式 JSON-RPC）：
```bash
antd-mcp
```
然后向 stdin 逐行发送 JSON 请求。

## 本地构建与发布

```bash
# 构建
python -m build
# 上传到 PyPI
python -m twine upload dist/*
```

### 自动化脚本

提供 `scripts/release.sh` 简化发布流程：

```bash
# 正常发布新版本 0.1.1
./scripts/release.sh 0.1.1

# 仅构建 + 校验 (不上传、不推送 tag)
./scripts/release.sh 0.1.1 --dry-run
```

依赖:
- 已安装 `build` 与 `twine` (`pip install build twine`)
- 已通过测试 (`pytest -q`)；脚本会先跑测试。
- PyPI 凭证 (推荐 Token):
  ```bash
  export TWINE_USERNAME="__token__"
  export TWINE_PASSWORD="pypi-xxxxx"  # 在 PyPI 创建的 token
  ```

脚本步骤:
1. 检查 git 工作区是否干净
2. 运行测试
3. 更新 `pyproject.toml` 中版本号
4. 提交并打 tag `v<version>`
5. 构建 (wheel + sdist)
6. `twine check` 验证
7. 上传 (跳过若 dry-run)
8. 推送 commit 与 tag

注意事项:
- 使用 `sed` 简单替换版本号行，保持现有格式。
- 若需要预发行版本，可传入 `0.2.0rc1` 等。
- 若需要撤销，可删除 tag 并重置 commit：`git tag -d v0.1.1 && git reset --hard HEAD~1`。

## 供 AI 工具使用的 mcp.json 示例

```jsonc
{
  "version": 1,
  "servers": {
    "antd_mcp": {
      "command": "antd-mcp",
      "args": [],
      "timeoutSeconds": 60
    }
  }
}
```

## 环境变量

- `ANTD_MCP_CACHE_DIR` 自定义缓存目录。
- `MCP_PRETTY` / `MCP_COLOR` 控制输出格式。

## 版本

当前版本: 0.1.0

## 常见问题 (FAQ)

1. ModuleNotFoundError: `No module named 'antd_mcp'`
  - 已改为平铺布局，使用 `python -m server` 或安装后使用 `antd-mcp`。
2. 输出出现多行 JSON 导致解析报错
  - 仅解析第一行或使用流模式逐行处理。
3. 想加速批量抓取
  - 可后续新增并行与重试（Roadmap 中）。
4. 如何发布新版本?
  - 运行 `./scripts/release.sh <version>`，确保环境变量与权限正确。
5. 如何进行试发布(dry run)?
  - 增加 `--dry-run` 参数，不上传、不推送。

# antd-mcp
