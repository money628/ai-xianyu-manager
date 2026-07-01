"""测试合规半自动铺货助手"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from modules.publisher import (
    PublishDraft, generate_publish_draft, mark_published,
    get_publish_stats, get_copy_text, check_rate_limit,
    _check_compliance,
)


def test_generate_basic_draft():
    """基础草稿生成"""
    opp = {
        "id": "test_001",
        "sell_title": "闪魔K80钢化膜防窥高清2片装",
        "buy_title": "闪魔K80钢化膜",
        "sell_price": 99.0, "buy_price": 12.8, "profit": 81.6, "roi": 637.5,
        "sell_image": "https://example.com/img.jpg",
        "buy_platform": "pdd",
    }
    draft = generate_publish_draft(opp)

    assert draft.source_item_id == "test_001"
    assert "K80" in draft.title
    assert draft.price == 99.0
    assert draft.publish_status in ("DRAFT_GENERATED", "NEEDS_REVIEW")
    assert len(draft.images) > 0
    print("test_generate_basic_draft PASS")


def test_low_confidence_triggers_review():
    """低置信度应设置 NEEDS_REVIEW"""
    opp = {
        "id": "test_002",
        "sell_title": "某手机膜",
        "sell_price": 50.0, "buy_price": 5.0, "profit": 40.0, "roi": 800,
        "match_confidence": 0.15,  # 很低
        "buy_platform": "pdd",
    }
    draft = generate_publish_draft(opp)
    assert draft.publish_status == "NEEDS_REVIEW"
    assert "low_match_confidence" in draft.compliance_flags
    print("test_low_confidence_triggers_review PASS")


def test_missing_model_triggers_review():
    """缺少型号应进入 NEEDS_REVIEW"""
    opp = {
        "id": "test_003",
        "sell_title": "手机膜钢化膜",
        "sell_price": 30.0, "buy_price": 5.0, "profit": 20.0, "roi": 400,
        "buy_platform": "pdd",
    }
    draft = generate_publish_draft(opp)
    assert draft.publish_status == "NEEDS_REVIEW"
    assert "missing_model" in draft.compliance_flags
    print("test_missing_model_triggers_review PASS")


def test_price_uncertain_flag():
    """价格不确定标记"""
    opp = {
        "id": "test_004",
        "sell_title": "闪魔K80钢化膜防窥",
        "sell_price": 99.0, "buy_price": 12.8, "profit": 81.6, "roi": 637.5,
        "price_confidence": 0.2,  # 很低
        "buy_platform": "pdd",
    }
    draft = generate_publish_draft(opp)
    assert "price_uncertain" in draft.risk_flags or "low_price_confidence" in draft.compliance_flags
    print("test_price_uncertain_flag PASS")


def test_image_uncertain_flag():
    """无图片时标记风险"""
    opp = {
        "id": "test_005",
        "sell_title": "闪魔K80钢化膜2片",
        "sell_price": 50.0, "buy_price": 10.0, "profit": 35.0, "roi": 350,
        "buy_platform": "pdd",
        # 无图片
    }
    draft = generate_publish_draft(opp)
    assert "image_source_uncertain" in draft.risk_flags
    assert "missing_image" in draft.compliance_flags
    print("test_image_uncertain_flag PASS")


def test_copy_text_format():
    """复制内容包含必要字段"""
    draft = PublishDraft(title="K80钢化膜", price=50.0,
                         description="个人闲置 K80钢化膜\n全新\n包邮",
                         condition="全新", shipping_note="包邮48h发货")
    texts = get_copy_text(draft)
    assert "K80" in texts["all"]
    assert "50" in texts["all"]
    assert "包邮" in texts["all"]
    print("test_copy_text_format PASS")


def test_rate_limit_tracks():
    """频率限制日志记录"""
    opp = {"id": f"rate_test_{os.getpid()}", "sell_title": "test", "sell_price": 10,
           "buy_price": 5, "profit": 2, "roi": 40, "buy_platform": "pdd"}
    draft = generate_publish_draft(opp)

    # 检查频率统计
    stats = get_publish_stats()
    assert stats["drafts_today"] >= 1
    assert stats["max_drafts"] == 10
    assert stats["max_published"] == 3
    print("test_rate_limit_tracks PASS")


def test_publish_log_is_written():
    """发布日志写入"""
    # 验证日志文件存在且包含有效 JSON
    log_path = os.path.join(os.path.dirname(__file__), "..", "data", "publish_log.jsonl")
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
        assert len(lines) > 0
        first = json.loads(lines[-1])
        assert "action" in first
        assert "timestamp" in first
        print("test_publish_log_is_written PASS")
    else:
        print("test_publish_log_is_written SKIP (no log yet)")


if __name__ == "__main__":
    test_generate_basic_draft()
    test_low_confidence_triggers_review()
    test_missing_model_triggers_review()
    test_price_uncertain_flag()
    test_image_uncertain_flag()
    test_copy_text_format()
    test_rate_limit_tracks()
    test_publish_log_is_written()
    print("\nALL TESTS PASSED")
