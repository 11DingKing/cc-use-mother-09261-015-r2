"""教材版本与交付业务层。

版本规则与身份权限只在本层定义，接口层不得自行裁剪：
- 版本一经发布即不可变，修订只能产生新版本；
- render 是唯一的内容裁剪入口，查询与交付都走它；
- 交付时把裁剪结果冻结进 Delivery，后续修订不改变已发出的内容；
- 交付历史可回放，审计列表只暴露元数据，不成为泄露入口。
"""
from dataclasses import dataclass,asdict
from datetime import datetime,timezone
import hashlib,json
SCOPES=("public","partner","internal")
ROLE_SCOPE={"public":"public","school":"partner","distributor":"partner","editor":"internal","admin":"internal"}
DEFAULT_SCOPE="public"
def _now(): return datetime.now(timezone.utc).isoformat()
def visible(scope,role):
 """唯一裁剪规则：身份可见自己级别及以下的内容，未知身份按最低级别。"""
 return SCOPES.index(scope)<=SCOPES.index(ROLE_SCOPE.get(role,DEFAULT_SCOPE))
def _digest(id,version,sections):
 payload=json.dumps({"id":id,"version":version,"sections":[asdict(s) for s in sections]},sort_keys=True,ensure_ascii=False)
 return hashlib.sha256(payload.encode()).hexdigest()
@dataclass(frozen=True)
class Section:
 id:str; title:str; body:str; scope:str="public"
 def __post_init__(self):
  if self.scope not in SCOPES: raise ValueError("unknown scope")
@dataclass(frozen=True)
class Edition:
 id:str; version:int; actor:str; created_at:str; sections:tuple
@dataclass(frozen=True)
class Delivery:
 id:str; edition:str; version:int; role:str; actor:str; created_at:str; digest:str; sections:tuple
class Catalog:
 """版本目录与交付记录，可选 SQLiteStore 持久化。"""
 def __init__(self,store=None):
  self.store=store; self.editions={}; self.deliveries={}; self.pub_keys={}; self.del_keys={}; self.seq=0
 def publish(self,id,sections,actor,key=None):
  """发布新版本（版本号单调递增），幂等键重复时返回原版本。"""
  if key and key in self.pub_keys:
   eid,ver=self.pub_keys[key]; return self.editions[eid][ver]
  rows=tuple(Section(**s) if isinstance(s,dict) else s for s in sections)
  if not rows: raise ValueError("empty sections")
  versions=self.editions.setdefault(id,{})
  ed=Edition(id,len(versions)+1,actor,_now(),rows); versions[ed.version]=ed
  if key: self.pub_keys[key]=(id,ed.version)
  self._persist(); return ed
 def render(self,id,version=None,role=None):
  """按身份裁剪指定版本（默认最新）；缺省身份按最低权限，同一版本同一身份结果恒定。"""
  ed=self._edition(id,version)
  return {"id":ed.id,"version":ed.version,"sections":tuple(asdict(s) for s in ed.sections if visible(s.scope,role))}
 def deliver(self,id,role,actor,version=None,key=None):
  """按当时版本交付并冻结裁剪结果；幂等键重复时返回原交付记录。"""
  if key and key in self.del_keys: return self.deliveries[self.del_keys[key]]
  ed=self._edition(id,version)
  secs=tuple(s for s in ed.sections if visible(s.scope,role))
  self.seq+=1
  d=Delivery("d%d"%self.seq,ed.id,ed.version,role,actor,_now(),_digest(ed.id,ed.version,secs),secs)
  self.deliveries[d.id]=d
  if key: self.del_keys[key]=d.id
  self._persist(); return d
 def replay(self,delivery_id):
  """回放历史交付，内容冻结于交付当时。"""
  return self.deliveries[delivery_id]
 def history(self,edition=None):
  """审计列表：只有元数据不含正文，避免审计入口成为泄露通道。"""
  rows=[d for d in self.deliveries.values() if edition in (None,d.edition)]
  return [{"id":d.id,"edition":d.edition,"version":d.version,"role":d.role,"actor":d.actor,"created_at":d.created_at,"digest":d.digest} for d in rows]
 def _edition(self,id,version=None):
  versions=self.editions.get(id)
  if not versions: raise KeyError(id)
  if version is None: version=max(versions)
  if version not in versions: raise KeyError(version)
  return versions[version]
 def _persist(self):
  if self.store: self.store.save(self._snapshot())
 def _snapshot(self):
  return {"editions":[asdict(e) for vs in self.editions.values() for e in vs.values()],"deliveries":[asdict(d) for d in self.deliveries.values()],"pub_keys":{k:list(v) for k,v in self.pub_keys.items()},"del_keys":dict(self.del_keys),"seq":self.seq}
 @classmethod
 def load(cls,store):
  """从仓储恢复，历史交付重启后仍可回放。"""
  c=cls(store); data=store.latest()
  if isinstance(data,dict):
   for raw in data.get("editions",[]):
    e=Edition(raw["id"],raw["version"],raw["actor"],raw["created_at"],tuple(Section(**s) for s in raw["sections"]))
    c.editions.setdefault(e.id,{})[e.version]=e
   for raw in data.get("deliveries",[]):
    d=Delivery(raw["id"],raw["edition"],raw["version"],raw["role"],raw["actor"],raw["created_at"],raw["digest"],tuple(Section(**s) for s in raw["sections"]))
    c.deliveries[d.id]=d
   c.pub_keys={k:tuple(v) for k,v in data.get("pub_keys",{}).items()}
   c.del_keys=data.get("del_keys",{}); c.seq=data.get("seq",0)
  return c
