from fastapi import APIRouter

from app.finance.engine import calculate
from app.finance.schemas import FinanceRequest, FinanceResult

router = APIRouter(prefix="/api/v1/finance", tags=["finance"])


@router.post("/calculate", response_model=FinanceResult)
def financial_calculation(request: FinanceRequest) -> FinanceResult:
    return calculate(request)
