"""业务层：版本规则与身份权限的唯一入口。

所有对外的内容视图都必须由 DeliveryService.render 产生，
接口层（JSON API、后台任务、未来的其他通道）只做协议转换，不得自行取舍内容。
"""
from .domain import (
    Delivery,
    Edition,
    IdempotencyConflict,
    Partner,
    SCOPES,
    Section,
    digest_of,
    utcnow,
)
from .store import DeliveryStore


class DeliveryService:
    def __init__(self, store: DeliveryStore | None = None, clock=utcnow):
        self.store = store or DeliveryStore()
        self.clock = clock

    # ---- 版本规则 ----

    def publish(self, textbook_id: str, sections, actor: str) -> Edition:
        """发布新版本：版本号按教材递增，旧版本永远保持原样可读。"""
        secs = tuple(Section(s["id"], s["scope"], s["body"]) for s in sections)
        edition = Edition(
            textbook_id=textbook_id,
            version=self.store.next_version(textbook_id),
            sections=secs,
            published_by=actor,
            published_at=self.clock(),
        )
        return self.store.save_edition(edition)

    def edition(self, textbook_id: str, version: int) -> Edition:
        return self.store.get_edition(textbook_id, version)

    # ---- 身份权限 ----

    def grant(self, partner_id: str, scopes, actor: str) -> Partner:
        """授予或调整合作方可见范围；只影响之后的渲染，不改写历史交付。"""
        unknown = set(scopes) - set(SCOPES)
        if unknown:
            raise ValueError(f"unknown scopes: {sorted(unknown)}")
        return self.store.save_partner(
            Partner(partner_id, frozenset(scopes), actor, self.clock())
        )

    def partner(self, partner_id: str) -> Partner:
        return self.store.get_partner(partner_id)

    # ---- 统一裁剪 ----

    def render(self, textbook_id: str, version: int, partner_id: str) -> dict:
        """按身份渲染指定版本：唯一允许产生对外内容视图的地方。

        同一 (版本, 身份) 的渲染结果稳定一致；不同身份各见其所当见。
        """
        edition = self.store.get_edition(textbook_id, version)
        partner = self.store.get_partner(partner_id)
        view = {
            "textbook_id": edition.textbook_id,
            "version": edition.version,
            "partner_id": partner.id,
            "sections": [
                {"id": s.id, "scope": s.scope, "body": s.body}
                for s in edition.sections
                if s.scope in partner.scopes
            ],
        }
        view["digest"] = digest_of(view)
        return view

    # ---- 交付与回放 ----

    def deliver(
        self, textbook_id, version, partner_id, actor, idempotency_key=None
    ) -> Delivery:
        """交付指定版本给合作方，并把当时裁剪出的内容原样留档。

        相同幂等键重复交付返回同一条记录；键被不同参数复用则拒绝。
        """
        if idempotency_key is not None:
            existing = self.store.find_delivery_by_key(idempotency_key)
            if existing is not None:
                same = (
                    existing.textbook_id == textbook_id
                    and existing.version == version
                    and existing.partner_id == partner_id
                )
                if not same:
                    raise IdempotencyConflict(idempotency_key)
                return existing
        payload = self.render(textbook_id, version, partner_id)
        return self.store.save_delivery(
            Delivery(
                id=None,
                textbook_id=textbook_id,
                version=version,
                partner_id=partner_id,
                actor=actor,
                payload=payload,
                digest=payload["digest"],
                idempotency_key=idempotency_key,
                delivered_at=self.clock(),
            )
        )

    def replay(self, delivery_id: int) -> dict:
        """回放历史交付：返回留档内容，不受后续修订与权限调整影响。"""
        return self.store.get_delivery(delivery_id).payload

    def deliveries(self, textbook_id=None, partner_id=None):
        """交付台账，可按教材或合作方过滤，用于追溯。"""
        return self.store.list_deliveries(
            textbook_id=textbook_id, partner_id=partner_id
        )
