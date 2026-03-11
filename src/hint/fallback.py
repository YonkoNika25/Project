"""Static fallback hints for each diagnosis category."""
from typing import Dict
from src.models import DiagnosisLabel, HintLevel

FALLBACK_HINTS: Dict[DiagnosisLabel, str] = {
    DiagnosisLabel.ARITHMETIC_ERROR: "Hãy kiểm tra lại các bước tính toán của em nhé. Có vẻ có một sai sót nhỏ trong phép tính đấy.",
    DiagnosisLabel.QUANTITY_RELATION_ERROR: "Em hãy xem kỹ mối quan hệ giữa các đại lượng trong đề bài. Liệu chúng ta nên cộng, trừ, nhân hay chia nhỉ?",
    DiagnosisLabel.TARGET_MISUNDERSTANDING: "Hãy đọc lại câu hỏi của đề bài một lần nữa. Đề bài đang yêu cầu tìm đại lượng nào vậy em?",
    DiagnosisLabel.UNPARSEABLE_ANSWER: "Thầy chưa hiểu rõ cách trình bày của em. Em có thể viết lại đáp án rõ ràng hơn được không?",
    DiagnosisLabel.UNKNOWN_ERROR: "Có vẻ bài toán này hơi lắt léo. Em hãy thử đọc lại đề bài và thực hiện từng bước một nhé.",
}

def get_static_fallback_hint(label: DiagnosisLabel) -> str:
    """Retrieve a generic pedagogical hint based on the error label."""
    return FALLBACK_HINTS.get(label, "Hãy thử suy nghĩ kỹ hơn về đề bài này nhé.")
