from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    level: str
    labels: list[str]
    block_model: bool
    response: str | None = None


SELF_HARM_TERMS = ("不想活", "自杀", "结束生命", "活着没意思", "去死")
SCAM_TERMS = ("转账", "验证码", "安全账户", "刷单", "投资群", "退款链接")
MEDICAL_TERMS = ("停药", "换药", "加药", "胸痛", "喘不上气", "昏倒", "中风")
EMERGENCY_MEDICAL_TERMS = ("胸痛", "喘不上气", "昏倒", "中风")


def classify_input(text: str) -> SafetyDecision:
    normalized = text.lower()
    if any(term in normalized for term in SELF_HARM_TERMS):
        return SafetyDecision(
            level="high",
            labels=["self_harm"],
            block_model=True,
            response=(
                "我很重视您刚才说的话。我是AI助手，不能独自处理这种紧急情况。"
                "请您现在先联系身边可信任的人，或拨打当地紧急援助电话；如果有立即危险，"
                "请直接联系急救或警方。我可以继续陪您，同时帮您准备联系家人的步骤。"
            ),
        )
    if any(term in normalized for term in SCAM_TERMS):
        return SafetyDecision(
            level="high",
            labels=["scam_or_transfer"],
            block_model=True,
            response=(
                "先不要转账，也不要提供验证码、银行卡号或屏幕共享。我是归音AI助手，"
                "建议您挂断陌生来电，并通过原有联系方式向家人或相关机构核实。"
            ),
        )
    if any(term in normalized for term in MEDICAL_TERMS):
        emergency = any(term in normalized for term in EMERGENCY_MEDICAL_TERMS)
        return SafetyDecision(
            level="high" if emergency else "medium",
            labels=["medical"],
            block_model=True,
            response=(
                "我不能诊断疾病，也不能建议您自行停药、换药或调整剂量。"
                + (
                    "这些症状可能需要立即处理，请马上联系身边的人并拨打当地急救电话。"
                    if emergency
                    else "请联系开药医生、药师或可信任家人核实。"
                )
            ),
        )
    return SafetyDecision(level="low", labels=[], block_model=False)


def sanitize_output(text: str) -> tuple[str, list[str]]:
    dangerous_claims = ("我就是你女儿", "我就是你儿子", "保证能治好", "立即转账")
    labels: list[str] = []
    output = text.strip()
    if any(claim in output for claim in dangerous_claims):
        labels.append("unsafe_identity_or_claim")
        output = (
            "我是归音AI助手，不是真实家人。刚才的回答不够可靠，已停止显示。"
            "如果事情涉及健康、钱款或紧急安全，请联系真实家人或专业人员。"
        )
    if "AI助手" not in output[:80]:
        output = "我是归音AI助手。" + output
    return output, labels
