"""JSON API 适配器：只解析协议形状，裁剪与权限判断全在业务层。

任何读取教材内容的入口都必须带合作方身份，由 DeliveryService.render 统一裁剪；
本模块不产生任何内容视图，因此换查询入口不会绕过权限。
"""
from urllib.parse import parse_qs, urlsplit

from .delivery import DeliveryService
from .domain import IdempotencyConflict
from .workflow import Workflow


def dispatch(service, method, path, body=None):
    """统一路由，返回 (status, json_body)。

    service 为 DeliveryService（交付域）；传入 Workflow 时兼容旧的 /cases 路由。
    """
    if isinstance(service, Workflow):
        return _cases(service, method, path, body or {})
    return _deliveries(service, method, path, body or {})


def _cases(flow, method, path, body):
    if method == "POST" and path == "/cases":
        return 201, flow.create(body["id"], body["actor"], body.get("idempotency_key")).__dict__
    if method == "POST" and path.endswith("/move"):
        return 200, flow.move(path.split("/")[2], body["state"], body["actor"]).__dict__
    if method == "GET" and path == "/cases":
        return 200, flow.snapshot()
    return 404, {"error": "not_found"}


def _deliveries(service: DeliveryService, method, path, body):
    url = urlsplit(path)
    parts = [p for p in url.path.split("/") if p]
    query = {k: v[0] for k, v in parse_qs(url.query).items()}
    try:
        # 版本发布与按身份渲染
        if len(parts) >= 2 and parts[0] == "textbooks":
            textbook_id = parts[1]
            if len(parts) == 3 and parts[2] == "editions" and method == "POST":
                edition = service.publish(textbook_id, body["sections"], body["actor"])
                return 201, edition.to_dict()
            if len(parts) == 4 and parts[2] == "editions" and method == "GET":
                partner = query.get("partner")
                if not partner:
                    return 400, {"error": "partner_required"}
                return 200, service.render(textbook_id, int(parts[3]), partner)
        # 身份授权
        if parts == ["partners"] and method == "POST":
            return 200, service.grant(body["id"], body["scopes"], body["actor"]).to_dict()
        # 交付、回放与台账
        if parts == ["deliveries"]:
            if method == "POST":
                delivery = service.deliver(
                    body["textbook_id"],
                    body["version"],
                    body["partner_id"],
                    body["actor"],
                    body.get("idempotency_key"),
                )
                return 201, delivery.to_dict()
            if method == "GET":
                rows = service.deliveries(query.get("textbook_id"), query.get("partner_id"))
                return 200, [d.to_dict(with_payload=False) for d in rows]
        if len(parts) == 2 and parts[0] == "deliveries" and method == "GET":
            return 200, {"id": int(parts[1]), "payload": service.replay(int(parts[1]))}
        return 404, {"error": "not_found"}
    except KeyError as e:
        return 400, {"error": "missing_field", "field": e.args[0]}
    except LookupError as e:
        return 404, {"error": "not_found", "detail": str(e)}
    except IdempotencyConflict as e:
        return 409, {"error": "idempotency_conflict", "key": e.args[0]}
    except ValueError as e:
        return 400, {"error": "bad_request", "detail": str(e)}
