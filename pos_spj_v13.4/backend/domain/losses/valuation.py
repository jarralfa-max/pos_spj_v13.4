"""LOSS-18 cost references and exact loss valuation policy."""
from dataclasses import dataclass
from decimal import Decimal,InvalidOperation
from enum import Enum
from backend.domain.losses.exceptions import LossInvariantError
class CostReferenceType(str,Enum):
    INVENTORY_AVERAGE="INVENTORY_AVERAGE";LOT_RECEIPT="LOT_RECEIPT";PURCHASE_RECEIPT="PURCHASE_RECEIPT";MANUAL_AUTHORIZED="MANUAL_AUTHORIZED"
class CostBasis(str,Enum): QUANTITY="QUANTITY";WEIGHT="WEIGHT"
def exact(value,field):
    if isinstance(value,(bool,float)):raise LossInvariantError(f"{field} debe usar Decimal, nunca float")
    try: result=Decimal(str(value))
    except (InvalidOperation,ValueError):raise LossInvariantError(f"{field} inválido") from None
    if not result.is_finite() or result<0:raise LossInvariantError(f"{field} debe ser finito y no negativo")
    return result
@dataclass(frozen=True,slots=True)
class ValuedLine:
    line_id:str;reference_type:CostReferenceType;reference_id:str;basis:CostBasis;basis_amount:Decimal;unit_cost:Decimal;gross_value:Decimal;recovered_value:Decimal=Decimal("0");net_loss_value:Decimal=Decimal("0")
@dataclass(frozen=True,slots=True)
class LossValuation:
    currency_code:str;lines:tuple[ValuedLine,...];gross_value:Decimal;recovered_value:Decimal;net_loss_value:Decimal
class LossValuationPolicy:
    def calculate(self,*,currency_code,lines,approved_recovery):
        if len(str(currency_code or ""))!=3:raise LossInvariantError("La moneda debe usar código ISO de tres letras")
        if not lines:raise LossInvariantError("La valuación requiere líneas")
        valued=[]
        for item in lines:
            amount=exact(item.basis_amount,"basis_amount");cost=exact(item.unit_cost,"unit_cost")
            if amount<=0:raise LossInvariantError("La base de costo debe ser positiva")
            valued.append(ValuedLine(item.line_id,CostReferenceType(item.reference_type),item.reference_id,CostBasis(item.basis),amount,cost,amount*cost))
        gross=sum((item.gross_value for item in valued),Decimal("0"));recovered=exact(approved_recovery,"approved_recovery")
        if recovered>gross:raise LossInvariantError("La recuperación aprobada no puede exceder el valor bruto")
        allocated=[];running=Decimal("0")
        for index,item in enumerate(valued):
            share=(recovered-running if index==len(valued)-1 else (Decimal("0") if gross==0 else recovered*item.gross_value/gross));running+=share
            allocated.append(ValuedLine(item.line_id,item.reference_type,item.reference_id,item.basis,item.basis_amount,item.unit_cost,item.gross_value,share,item.gross_value-share))
        return LossValuation(str(currency_code).upper(),tuple(allocated),gross,recovered,gross-recovered)
