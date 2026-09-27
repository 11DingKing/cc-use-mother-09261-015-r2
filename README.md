# 出版交付一致性

纯 Python 服务端项目：教材版本规则与合作方身份权限统一在业务层，交付可回放、可追溯。

## 结构

- `domain.py` — 领域模型：不可变版本 `Edition`、身份 `Partner`、交付留档 `Delivery`
- `delivery.py` — 业务层 `DeliveryService`：唯一允许产生对外内容视图的地方
- `store.py` — SQLite 持久化：版本只增不改，交付记录只追加
- `api.py` — JSON API 适配器：只做协议解析，不含任何裁剪逻辑

## 不变量

- 版本一旦发布即不可变，修订只能产生新版本号
- 任何读取教材内容的入口都必须带合作方身份，由 `render` 统一裁剪
- 交付时把裁剪结果原样留档，回放不受后续修订与权限调整影响
- 同一幂等键重复交付返回同一条记录，键被不同参数复用则拒绝（409）

## API

- `POST /textbooks/{id}/editions` — 发布新版本
- `GET /textbooks/{id}/editions/{version}?partner={pid}` — 按身份渲染（无身份 400）
- `POST /partners` — 授予/调整合作方可见范围
- `POST /deliveries` — 交付指定版本（支持 `idempotency_key`）
- `GET /deliveries?textbook_id=&partner_id=` — 交付台账（元信息）
- `GET /deliveries/{id}` — 回放历史交付内容

测试命令：python3 -m unittest discover -s tests -v

编译命令：python3 -m compileall -q service_09261_015 tests
