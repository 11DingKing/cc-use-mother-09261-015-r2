"""出版交付一致性服务端包。"""
PROJECT_CODE="service_09261_015"
from .workflow import Workflow
from .catalog import Catalog
class Service:
 """接口层入口：聚合工作流与版本目录，带仓储时自动恢复历史。"""
 def __init__(self,store=None):
  self.flow=Workflow()
  self.catalog=Catalog.load(store) if store else Catalog()
