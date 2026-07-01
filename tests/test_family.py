"""测试商品族聚合"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from modules.family_aggregator import (
    group_variants_into_families, generate_family_publish_draft,
    _normalize_title,
)


def test_normalize_title_removes_models():
    result = _normalize_title("iPhone17磨砂钢化膜")
    assert len(result) > 3
    print(f"test_normalize_title: '{result}'")
    print("test_normalize_title_removes_models PASS")


def test_same_url_grouped():
    opps = [
        {"buy_product_id": "", "buy_url": "https://item.pdd.com/123",
         "buy_title": "闪魔iPhone17钢化膜", "buy_price": 10, "sell_price": 50,
         "profit": 37, "roi": 370, "buy_platform": "pdd"},
        {"buy_product_id": "", "buy_url": "https://item.pdd.com/123",
         "buy_title": "闪魔iPhone16Pro钢化膜", "buy_price": 12, "sell_price": 55,
         "profit": 40, "roi": 333, "buy_platform": "pdd"},
    ]
    families = group_variants_into_families(opps)
    assert len(families) == 1, f"Expected 1 family, got {len(families)}"
    assert families[0].model_count == 2
    print("test_same_url_grouped PASS")


def test_same_item_id_grouped():
    opps = [
        {"buy_product_id": "abc123", "buy_url": "",
         "buy_title": "闪魔K80钢化膜", "buy_price": 5, "sell_price": 30,
         "profit": 22, "roi": 733, "buy_platform": "pdd"},
        {"buy_product_id": "abc123", "buy_url": "",
         "buy_title": "闪魔K90钢化膜", "buy_price": 6, "sell_price": 32,
         "profit": 23, "roi": 533, "buy_platform": "pdd"},
    ]
    families = group_variants_into_families(opps)
    assert len(families) == 1
    print("test_same_item_id_grouped PASS")


def test_different_urls_not_grouped():
    opps = [
        {"buy_product_id": "", "buy_url": "https://a.com/1",
         "buy_title": "闪魔iPhone17膜", "buy_price": 10, "sell_price": 50,
         "profit": 37, "roi": 370, "buy_platform": "pdd"},
        {"buy_product_id": "", "buy_url": "https://b.com/2",
         "buy_title": "闪魔iPhone16膜", "buy_price": 10, "sell_price": 50,
         "profit": 37, "roi": 370, "buy_platform": "pdd"},
    ]
    families = group_variants_into_families(opps)
    assert len(families) == 2
    print("test_different_urls_not_grouped PASS")


def test_family_has_variants():
    opps = [
        {"buy_product_id": "x1", "buy_url": "",
         "buy_title": "闪魔iPhone17防窥膜2片装", "buy_price": 12, "sell_price": 99,
         "profit": 84, "roi": 700, "buy_platform": "pdd"},
    ]
    families = group_variants_into_families(opps)
    assert len(families) == 1
    assert len(families[0].variants) >= 1
    print("test_family_has_variants PASS")


def test_low_confidence_skips_generation():
    opps = [
        {"buy_product_id": "low1", "buy_url": "",
         "buy_title": "某手机膜", "buy_price": 1, "sell_price": 10,
         "profit": 6, "roi": 150, "buy_platform": "pdd",
         "price_confidence": 0.2},
    ]
    families = group_variants_into_families(opps)
    draft = generate_family_publish_draft(families[0])
    assert draft["status"] != "DRAFT_GENERATED"  # 价格置信度低
    print("test_low_confidence_skips_generation PASS")


def test_draft_no_fake_words():
    opps = [
        {"buy_product_id": "ok1", "buy_url": "",
         "buy_title": "闪魔K80钢化膜防窥", "buy_price": 8, "sell_price": 50,
         "profit": 39, "roi": 487, "buy_platform": "pdd",
         "match_confidence": 0.7, "price_confidence": 0.8},
        {"buy_product_id": "ok1", "buy_url": "",
         "buy_title": "闪魔K90钢化膜防窥", "buy_price": 9, "sell_price": 52,
         "profit": 40, "roi": 444, "buy_platform": "pdd",
         "match_confidence": 0.7, "price_confidence": 0.8},
    ]
    families = group_variants_into_families(opps)
    family = families[0]
    # 等级应为 A 或 B
    assert family.family_grade in ("A", "B")
    draft = generate_family_publish_draft(family)
    assert draft["status"] == "DRAFT_GENERATED"
    # 不能包含 "个人闲置" "自用" "换新" "未拆封"
    desc = draft.get("description", "")
    for bad_word in ["个人闲置", "自用", "换新", "未拆封"]:
        assert bad_word not in desc, f"Found '{bad_word}' in draft"
    print("test_draft_no_fake_words PASS")


def test_grade_assignment():
    # 高性能 → A
    high = [
        {"buy_product_id": "h1", "buy_url": "",
         "buy_title": "闪魔K80钢化膜", "buy_price": 8, "sell_price": 50,
         "profit": 39, "roi": 487, "buy_platform": "pdd",
         "match_confidence": 0.8, "price_confidence": 0.9},
        {"buy_product_id": "h1", "buy_url": "",
         "buy_title": "闪魔K90钢化膜", "buy_price": 9, "sell_price": 52,
         "profit": 40, "roi": 444, "buy_platform": "pdd",
         "match_confidence": 0.8, "price_confidence": 0.9},
    ]
    families = group_variants_into_families(high)
    assert families[0].family_grade == "A"
    print("test_grade_assignment PASS")


if __name__ == "__main__":
    test_normalize_title_removes_models()
    test_same_url_grouped()
    test_same_item_id_grouped()
    test_different_urls_not_grouped()
    test_family_has_variants()
    test_low_confidence_skips_generation()
    test_draft_no_fake_words()
    test_grade_assignment()
    print("\nALL TESTS PASSED")
