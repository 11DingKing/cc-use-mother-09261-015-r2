import unittest

from service_09261_015.api import dispatch
from service_09261_015.delivery import DeliveryService
from service_09261_015.domain import IdempotencyConflict, UnknownEdition, UnknownPartner

SECTIONS = [
    {"id": "intro", "scope": "public", "body": "前言"},
    {"id": "ch1", "scope": "partner", "body": "第一章"},
    {"id": "answers", "scope": "internal", "body": "教师答案"},
]


def make_service():
    clock = iter("2026-09-27T00:00:%02d+00:00" % i for i in range(100))
    service = DeliveryService(clock=lambda: next(clock))
    service.publish("math", SECTIONS, actor="editor")
    service.grant("school", ["public"], actor="admin")
    service.grant("vendor", ["public", "partner"], actor="admin")
    return service


class TestRender(unittest.TestCase):
    def test_scopes_decide_visibility(self):
        s = make_service()
        school = s.render("math", 1, "school")
        self.assertEqual([x["id"] for x in school["sections"]], ["intro"])
        vendor = s.render("math", 1, "vendor")
        self.assertEqual([x["id"] for x in vendor["sections"]], ["intro", "ch1"])

    def test_same_version_same_identity_is_stable(self):
        s = make_service()
        first = s.render("math", 1, "vendor")
        self.assertEqual(first, s.render("math", 1, "vendor"))
        self.assertEqual(first["digest"], s.render("math", 1, "vendor")["digest"])

    def test_unknown_version_or_partner(self):
        s = make_service()
        with self.assertRaises(UnknownEdition):
            s.render("math", 9, "school")
        with self.assertRaises(UnknownPartner):
            s.render("math", 1, "ghost")

    def test_bad_scope_rejected(self):
        s = make_service()
        with self.assertRaises(ValueError):
            s.publish("math", [{"id": "x", "scope": "secret", "body": "y"}], actor="e")
        with self.assertRaises(ValueError):
            s.grant("p", ["public", "secret"], actor="a")


class TestDeliveryReplay(unittest.TestCase):
    def test_replay_immune_to_revision(self):
        s = make_service()
        d = s.deliver("math", 1, "vendor", actor="ops", idempotency_key="d1")
        s.publish("math", [SECTIONS[0]], actor="editor")  # 修订产生 v2
        self.assertEqual(s.replay(d.id), d.payload)
        self.assertEqual(s.render("math", 1, "vendor"), d.payload)  # v1 不可变
        self.assertEqual(len(s.render("math", 2, "vendor")["sections"]), 1)

    def test_replay_immune_to_permission_change(self):
        s = make_service()
        d = s.deliver("math", 1, "school", actor="ops")
        s.grant("school", ["public", "partner", "internal"], actor="admin")
        self.assertEqual([x["id"] for x in s.replay(d.id)["sections"]], ["intro"])
        self.assertEqual(len(s.render("math", 1, "school")["sections"]), 3)

    def test_idempotent_delivery(self):
        s = make_service()
        a = s.deliver("math", 1, "vendor", actor="ops", idempotency_key="k")
        b = s.deliver("math", 1, "vendor", actor="ops", idempotency_key="k")
        self.assertEqual(a.id, b.id)
        self.assertEqual(len(s.deliveries()), 1)
        with self.assertRaises(IdempotencyConflict):
            s.deliver("math", 1, "school", actor="ops", idempotency_key="k")

    def test_traceability(self):
        s = make_service()
        s.deliver("math", 1, "school", actor="ops")
        s.deliver("math", 1, "vendor", actor="ops")
        rows = s.deliveries(partner_id="vendor")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].actor, "ops")
        self.assertEqual(rows[0].version, 1)
        self.assertTrue(rows[0].digest)
        self.assertTrue(rows[0].delivered_at)
        self.assertEqual(len(s.deliveries(textbook_id="math")), 2)


class TestApi(unittest.TestCase):
    def test_render_requires_partner(self):
        s = make_service()
        status, _ = dispatch(s, "GET", "/textbooks/math/editions/1")
        self.assertEqual(status, 400)  # 无身份入口一律拒绝，不给未裁剪视图
        status, body = dispatch(s, "GET", "/textbooks/math/editions/1?partner=school")
        self.assertEqual(status, 200)
        self.assertEqual([x["id"] for x in body["sections"]], ["intro"])

    def test_unknown_returns_404(self):
        s = make_service()
        self.assertEqual(dispatch(s, "GET", "/textbooks/math/editions/9?partner=school")[0], 404)
        self.assertEqual(dispatch(s, "GET", "/textbooks/math/editions/1?partner=ghost")[0], 404)
        self.assertEqual(dispatch(s, "GET", "/deliveries/42")[0], 404)

    def test_deliver_and_replay_via_api(self):
        s = make_service()
        status, body = dispatch(s, "POST", "/deliveries", {
            "textbook_id": "math", "version": 1, "partner_id": "vendor",
            "actor": "ops", "idempotency_key": "k1",
        })
        self.assertEqual(status, 201)
        s.publish("math", [SECTIONS[0]], actor="editor")  # 交付后修订
        status, replayed = dispatch(s, "GET", "/deliveries/%d" % body["id"])
        self.assertEqual(status, 200)
        self.assertEqual(replayed["payload"], body["payload"])
        status, rows = dispatch(s, "GET", "/deliveries?partner_id=vendor")
        self.assertEqual(status, 200)
        self.assertEqual(len(rows), 1)
        self.assertNotIn("payload", rows[0])  # 台账只给元信息，内容走回放

    def test_idempotency_conflict_status(self):
        s = make_service()
        dispatch(s, "POST", "/deliveries", {
            "textbook_id": "math", "version": 1, "partner_id": "vendor",
            "actor": "ops", "idempotency_key": "k",
        })
        status, _ = dispatch(s, "POST", "/deliveries", {
            "textbook_id": "math", "version": 1, "partner_id": "school",
            "actor": "ops", "idempotency_key": "k",
        })
        self.assertEqual(status, 409)

    def test_bad_scope_status(self):
        s = make_service()
        status, _ = dispatch(s, "POST", "/textbooks/math/editions", {
            "sections": [{"id": "x", "scope": "secret", "body": "y"}], "actor": "e",
        })
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
