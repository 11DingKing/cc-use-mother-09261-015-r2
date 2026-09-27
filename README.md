# 出版交付一致性

纯 Python 服务端基础项目，提供版本化状态、幂等命令、SQLite 持久化和 JSON API 边界。

## 业务层规则（service_09261_015/catalog.py）

- 版本一经发布即不可变，修订只能产生新版本（版本号单调递增）。
- 身份权限：public < partner < internal，未知身份一律按 public；裁剪只由 `render`/`deliver` 统一执行，接口层不含裁剪分支。
- 交付时把当时版本的裁剪结果冻结进 `Delivery`（含内容摘要 digest），后续修订不改变已发出的内容，可随时回放。
- 审计列表只含元数据（版本、身份、digest、时间），不含正文，审计入口不会泄露内容。

## API（service_09261_015/api.py）

- `POST /editions` `{id, sections, actor, idempotency_key?}` 发布新版本
- `GET /editions/{id}?role=` / `GET /editions/{id}/versions/{n}?role=` 按身份查看（缺省身份按最低权限）
- `POST /deliveries` `{edition, role, actor, version?, idempotency_key?}` 按当时版本交付并冻结
- `GET /deliveries` 审计元数据；`GET /deliveries/{id}` 回放历史交付

测试命令：python3 -m unittest discover -s tests -v

编译命令：python3 -m compileall -q service_09261_015 tests
