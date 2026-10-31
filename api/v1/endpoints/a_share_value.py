"""Explicit value research actions under the original assistant auth boundary."""
from fastapi import APIRouter, HTTPException
from src.schemas.a_share_value import PrepareValueRequest, GenerateValueRequest, SaveValueRequest, EvaluateValueRequest, SupplementValueRequest
from src.services.a_share_value_service import ValueConflict

router = APIRouter()


def invoke(code, action):
    from api.v1.endpoints.a_share_market import service
    svc = service()
    with svc._settings_lock:
        if svc.market.repo.stock(svc.settings.mode, code) is None:
            raise HTTPException(404, '当前目录中没有该股票')
        try:
            return action(svc.value)
        except ValueConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc


@router.get('/stocks/{code}/value-research')
def value_research(code: str):
    return invoke(code, lambda s: s.get(code))


@router.post('/stocks/{code}/value-data')
def value_data(code: str, body: PrepareValueRequest):
    return invoke(code, lambda s: s.prepare(code, body.peer_offset, body.refresh))


@router.post('/stocks/{code}/value-research')
def generate_value(code: str, body: GenerateValueRequest):
    return invoke(code, lambda s: s.generate(code, body))


@router.put('/stocks/{code}/value-assumptions')
def value_assumptions(code: str, body: SaveValueRequest):
    return invoke(code, lambda s: s.save_assumptions(code, body))


@router.post('/stocks/{code}/value-evaluate')
def value_evaluate(code: str, body: EvaluateValueRequest):
    return invoke(code, lambda s: s.evaluate(code, body))


@router.post('/stocks/{code}/value-supplement')
def value_supplement(code: str, body: SupplementValueRequest):
    return invoke(code, lambda s: s.supplement(code, body))
