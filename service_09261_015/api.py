"""JSON API 适配器：只做解析与序列化，裁剪规则全部在业务层。"""
from dataclasses import asdict
from urllib.parse import urlparse,parse_qs
def _need(body,*names):
 missing=[n for n in names if n not in body]
 if missing: raise ValueError("missing "+",".join(missing))
 return [body[n] for n in names]
def dispatch(service,method,path,body=None):
 body=body or {}
 parts=urlparse(path); route=parts.path.strip("/").split("/"); q=parse_qs(parts.query)
 role=(q.get("role") or [body.get("role")])[0]
 try:
  if method=="POST" and route==["cases"]:
   id,actor=_need(body,"id","actor"); return 201,service.flow.create(id,actor,body.get("idempotency_key")).__dict__
  if method=="POST" and len(route)==3 and route[0]=="cases" and route[2]=="move":
   state,actor=_need(body,"state","actor"); return 200,service.flow.move(route[1],state,actor).__dict__
  if method=="GET" and route==["cases"]: return 200,service.flow.snapshot()
  if method=="POST" and route==["editions"]:
   id,sections,actor=_need(body,"id","sections","actor")
   return 201,asdict(service.catalog.publish(id,sections,actor,body.get("idempotency_key")))
  if method=="GET" and len(route)==2 and route[0]=="editions": return 200,service.catalog.render(route[1],role=role)
  if method=="GET" and len(route)==4 and route[0]=="editions" and route[2]=="versions": return 200,service.catalog.render(route[1],int(route[3]),role)
  if method=="POST" and route==["deliveries"]:
   edition,to,actor=_need(body,"edition","role","actor")
   return 201,asdict(service.catalog.deliver(edition,to,actor,body.get("version"),body.get("idempotency_key")))
  if method=="GET" and route==["deliveries"]: return 200,service.catalog.history((q.get("edition") or [None])[0])
  if method=="GET" and len(route)==2 and route[0]=="deliveries": return 200,asdict(service.catalog.replay(route[1]))
  return 404,{"error":"not_found"}
 except KeyError as e: return 404,{"error":"not_found","detail":str(e)}
 except ValueError as e: return 400,{"error":"bad_request","detail":str(e)}
