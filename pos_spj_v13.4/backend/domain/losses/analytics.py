"""Pure LOSS-20 KPI, Pareto and trend calculations."""
from dataclasses import dataclass
from decimal import Decimal
@dataclass(frozen=True,slots=True)
class LossKpis:
    case_count:int;gross_value:Decimal;recovered_value:Decimal;net_loss_value:Decimal;recovery_rate:Decimal;open_investigations:int;overdue_actions:int
@dataclass(frozen=True,slots=True)
class ParetoPoint:
    code:str;label:str;net_loss_value:Decimal;percent:Decimal;cumulative_percent:Decimal
def build_kpis(row):
    gross=Decimal(str(row["gross_value"] or 0));recovered=Decimal(str(row["recovered_value"] or 0));rate=Decimal("0") if gross==0 else recovered*Decimal("100")/gross
    return LossKpis(int(row["case_count"]),gross,recovered,Decimal(str(row["net_loss_value"] or 0)),rate,int(row["open_investigations"]),int(row["overdue_actions"]))
def build_pareto(rows):
    values=[(str(code),str(label),Decimal(str(value))) for code,label,value in rows];total=sum((v for _,_,v in values),Decimal("0"));running=Decimal("0");result=[]
    for code,label,value in values:
        percent=Decimal("0") if total==0 else value*Decimal("100")/total;running+=percent;result.append(ParetoPoint(code,label,value,percent,min(Decimal("100"),running)))
    return tuple(result)
