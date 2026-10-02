from app.models import Answer, Item, Template

LABELS = {
    (True, True): "이해",
    (True, False): "찍기 의심 / 개념 오인",
    (False, True): "적용 실패",
    (False, False): "개념 미습득",
}


def grade(answer: Answer, item: Item, student_template: Template | None) -> None:
    """제출 시점에 정오와 선택형 슬롯 일치 여부를 계산해 answer에 기록한다."""
    answer.judgement_ok = answer.judgement == item.is_correct
    answer.tag_ok = answer.tag == item.tag
    check: dict[str, bool] = {}
    if student_template is not None:
        for name, spec in student_template.slots.items():
            # 선택형 슬롯만 비교. 모범 답에 같은 슬롯이 없으면(판단/태그가 달라 틀이 다름) 불일치.
            if isinstance(spec, list):
                check[name] = (item.model_slots or {}).get(name) == (answer.slots or {}).get(name)
    answer.slots_check = check


def diagnosis(answer: Answer) -> str | None:
    if answer.judgement_ok is None or answer.tag_ok is None:
        return None
    return LABELS[(answer.judgement_ok, answer.tag_ok)]
