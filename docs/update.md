# 观澜更新指南

本文档写给正在维护本地安装的 Agent。观澜第一版以 GitHub 源码安装为主，更新以拉取可信仓库后重装为准。

## GitHub 源码更新

确认你位于观澜仓库根目录后，先拉取最新代码，再重装：

```bash
git pull --ff-only
```

然后执行：

```bash
pipx install --force .
guanlan doctor --trace
```

如果使用虚拟环境安装：

```bash
source ~/.guanlan-venv/bin/activate
pip install --upgrade .
guanlan doctor --trace
```

## Skill 更新

如果用户已经安装过 Agent skill，更新包后同步一次：

```bash
guanlan skill --install
```

## 可选工具更新

观澜会尽量通过 `doctor` 给出缺失提示。只有用户确实需要对应渠道时，再更新外部工具：

```bash
pipx upgrade twitter-cli
pipx upgrade rdt-cli
pipx upgrade xiaohongshu-cli
pipx upgrade bilibili-cli
npm update -g mcporter
```

这些命令可能因为安装方式不同而失败。失败时不要强行清理用户环境，先运行 `guanlan doctor --trace` 看当前渠道状态。

## 版本检查

`guanlan check-update` 会尝试读取 GitHub Release 信息。第一版早期如果维护者还没有创建 release，检查失败不代表本地安装损坏。

公开发布源接入后，可以使用：

```bash
guanlan check-update
```

## 更新后核对

运行：

```bash
guanlan version
guanlan doctor --trace
```

向用户报告：

- 当前版本号。
- 哪些渠道可用。
- 哪些渠道需要重新登录、补 Cookie、配置代理或补 API Key。
- 本次是否只更新了观澜本体，还是也更新了外部工具。

## 注意事项

- 不主动删除旧工具；用户可能仍依赖它们。
- 不读取 Cookie 或钥匙串来“验证更新成功”。
- 不在用户项目目录里生成临时文件。
- 如果更新涉及系统权限，先向用户说明原因和影响。
