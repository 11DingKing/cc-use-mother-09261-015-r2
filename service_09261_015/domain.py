"""领域模型：教材版本、合作方身份与交付记录。

版本（Edition）一旦发布即不可变，修订只能产生新的版本号；
交付（Delivery）记录交付时刻的裁剪结果，之后的内容修订与权限调整都不会改写它。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256

# 内容范围分级：每个章节恰好属于一个范围，合作方只能看到自己被授予的范围。
SCOPES = ("public", "partner", "internal")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest_of(value) -> str:
    """稳定摘要：键排序、紧凑分隔，同样的内容永远得到同样的摘要。"""
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(blob.encode("utf-8")).hexdigest()


class UnknownEdition(LookupError):
    """教材版本不存在。"""


class UnknownPartner(LookupError):
    """合作方身份不存在。"""


class UnknownDelivery(LookupError):
    """交付记录不存在。"""


class IdempotencyConflict(ValueError):
    """幂等键被不同参数复用。"""


@dataclass(frozen=True)
class Section:
    id: str
    scope: str
    body: str

    def __post_init__(self):
        if self.scope not in SCOPES:
            raise ValueError(f"unknown scope: {self.scope}")


@dataclass(frozen=True)
class Edition:
    """不可变的教材版本。"""

    textbook_id: str
    version: int
    sections: tuple  # tuple[Section, ...]，保持发布时的章节顺序
    published_by: str
    published_at: str

    def to_dict(self) -> dict:
        return {
            "textbook_id": self.textbook_id,
            "version": self.version,
            "sections": [asdict(s) for s in self.sections],
            "published_by": self.published_by,
            "published_at": self.published_at,
        }

    @staticmethod
    def from_dict(data: dict) -> "Edition":
        return Edition(
            textbook_id=data["textbook_id"],
            version=data["version"],
            sections=tuple(Section(**s) for s in data["sections"]),
            published_by=data["published_by"],
            published_at=data["published_at"],
        )


@dataclass(frozen=True)
class Partner:
    """合作方身份及其可见范围。"""

    id: str
    scopes: frozenset
    updated_by: str
    updated_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "scopes": sorted(self.scopes),
            "updated_by": self.updated_by,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data: dict) -> "Partner":
        return Partner(
            id=data["id"],
            scopes=frozenset(data["scopes"]),
            updated_by=data["updated_by"],
            updated_at=data["updated_at"],
        )


@dataclass(frozen=True)
class Delivery:
    """一次交付的留痕：谁在何时把哪个版本按哪个身份交付，内容原样留存。"""

    id: int | None
    textbook_id: str
    version: int
    partner_id: str
    actor: str
    payload: dict
    digest: str
    idempotency_key: str | None
    delivered_at: str

    def to_dict(self, with_payload: bool = True) -> dict:
        data = {
            "id": self.id,
            "textbook_id": self.textbook_id,
            "version": self.version,
            "partner_id": self.partner_id,
            "actor": self.actor,
            "digest": self.digest,
            "idempotency_key": self.idempotency_key,
            "delivered_at": self.delivered_at,
        }
        if with_payload:
            data["payload"] = self.payload
        return data

    @staticmethod
    def from_dict(data: dict) -> "Delivery":
        return Delivery(**data)
