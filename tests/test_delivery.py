import unittest
from service_09261_015 import Service
from service_09261_015.catalog import Catalog
from service_09261_015.store import SQLiteStore
from service_09261_015.api import dispatch
SECTIONS=[
 {"id":"s1","title":"导言","body":"公开导言","scope":"public"},
 {"id":"s2","title":"教师手册","body":"合作方教案","scope":"partner"},
 {"id":"s3","title":"审读意见","body":"内部批注","scope":"internal"},
]
def make():
 c=Catalog(); c.publish("bk1",SECTIONS,"editor"); return c
class TestPermission(unittest.TestCase):
 def test_role_scopes(self):
  c=make()
  self.assertEqual([s["id"] for s in c.render("bk1",1,"public")["sections"]],["s1"])
  self.assertEqual([s["id"] for s in c.render("bk1",1,"distributor")["sections"]],["s1","s2"])
  self.assertEqual([s["id"] for s in c.render("bk1",1,"editor")["sections"]],["s1","s2","s3"])
 def test_unknown_role_gets_minimum(self):
  c=make()
  self.assertEqual([s["id"] for s in c.render("bk1",1,"stranger")["sections"]],["s1"])
  self.assertEqual([s["id"] for s in c.render("bk1",1)["sections"]],["s1"])
 def test_render_is_deterministic(self):
  c=make(); self.assertEqual(c.render("bk1",1,"distributor"),c.render("bk1",1,"distributor"))
 def test_delivery_respects_role(self):
  c=make(); d=c.deliver("bk1","distributor","ship")
  self.assertEqual([s.id for s in d.sections],["s1","s2"])
  self.assertNotIn("内部批注",str(d.sections))
class TestVersioning(unittest.TestCase):
 def test_revision_does_not_rewrite_history(self):
  c=make(); d1=c.deliver("bk1","editor","ship")
  c.publish("bk1",[{"id":"s1","title":"导言","body":"改写后的导言","scope":"public"}],"editor")
  again=c.replay(d1.id)
  self.assertEqual(again.sections,d1.sections); self.assertEqual(again.digest,d1.digest)
  self.assertIn("公开导言",[s["body"] for s in c.render("bk1",1,"editor")["sections"]])
  self.assertEqual([s["body"] for s in c.render("bk1",2,"editor")["sections"]],["改写后的导言"])
 def test_version_numbers_monotonic(self):
  c=make(); e2=c.publish("bk1",SECTIONS,"editor")
  self.assertEqual(e2.version,2); self.assertEqual(c.render("bk1")["version"],2)
 def test_bad_scope_rejected(self):
  with self.assertRaises(ValueError):
   Catalog().publish("bk1",[{"id":"s","title":"t","body":"b","scope":"top-secret"}],"ed")
class TestDelivery(unittest.TestCase):
 def test_idempotent_delivery(self):
  c=make(); a=c.deliver("bk1","distributor","ship",key="k1"); b=c.deliver("bk1","distributor","ship",key="k1")
  self.assertEqual(a.id,b.id); self.assertEqual(len(c.deliveries),1)
 def test_idempotent_publish(self):
  c=Catalog(); e1=c.publish("bk1",SECTIONS,"ed",key="p"); e2=c.publish("bk1",SECTIONS,"ed",key="p")
  self.assertEqual(e1.version,e2.version); self.assertEqual(len(c.editions["bk1"]),1)
 def test_same_content_same_digest(self):
  c=make(); a=c.deliver("bk1","distributor","x"); b=c.deliver("bk1","distributor","y")
  self.assertEqual(a.digest,b.digest)
 def test_history_hides_bodies(self):
  c=make(); c.deliver("bk1","editor","ship")
  row=c.history()[0]
  self.assertIn("digest",row); self.assertNotIn("sections",row); self.assertNotIn("内部批注",str(row))
  self.assertEqual(c.history("bk1"),c.history()); self.assertEqual(c.history("other"),[])
class TestApi(unittest.TestCase):
 def setUp(self):
  self.s=Service(); dispatch(self.s,"POST","/editions",{"id":"bk1","actor":"ed","sections":SECTIONS})
 def test_query_and_delivery_agree(self):
  _,view=dispatch(self.s,"GET","/editions/bk1/versions/1?role=distributor")
  _,sent=dispatch(self.s,"POST","/deliveries",{"edition":"bk1","role":"distributor","actor":"ship"})
  self.assertEqual(view["sections"],sent["sections"])
 def test_replay_route_returns_frozen_content(self):
  _,sent=dispatch(self.s,"POST","/deliveries",{"edition":"bk1","role":"editor","actor":"ship","idempotency_key":"k"})
  dispatch(self.s,"POST","/editions",{"id":"bk1","actor":"ed","sections":[SECTIONS[0]]})
  _,again=dispatch(self.s,"GET","/deliveries/"+sent["id"])
  self.assertEqual(again,sent); self.assertEqual(again["version"],1)
 def test_audit_route_has_no_bodies(self):
  dispatch(self.s,"POST","/deliveries",{"edition":"bk1","role":"editor","actor":"ship"})
  code,rows=dispatch(self.s,"GET","/deliveries")
  self.assertEqual(code,200); self.assertNotIn("内部批注",str(rows))
 def test_unknown_version_404_and_bad_body_400(self):
  self.assertEqual(dispatch(self.s,"GET","/editions/bk1/versions/9?role=editor")[0],404)
  self.assertEqual(dispatch(self.s,"POST","/deliveries",{"edition":"bk1"})[0],400)
class TestPersistence(unittest.TestCase):
 def test_reload_replays_deliveries(self):
  store=SQLiteStore(); c=Catalog(store)
  c.publish("bk1",SECTIONS,"ed"); d=c.deliver("bk1","distributor","ship")
  c.publish("bk1",[SECTIONS[0]],"ed")
  again=Catalog.load(store).replay(d.id)
  self.assertEqual(again.sections,d.sections); self.assertEqual(again.digest,d.digest)
  self.assertEqual([s.id for s in again.sections],["s1","s2"])
if __name__=="__main__": unittest.main()
