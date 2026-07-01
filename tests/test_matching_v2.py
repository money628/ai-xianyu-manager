"""测试 v2.0 结构化匹配引擎"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from modules.matcher import (
    parse_product_title, match_products_v2, ProductAttrs, MatchResult,
    validate_match_v2, detect_risks,
)


def test_parse_basic():
    """基础解析测试"""
    attrs = parse_product_title("闪魔适用红米K80手机膜钢化膜防窥高清2片装")
    assert attrs.product_brand == "闪魔", f"brand: {attrs.product_brand}"
    assert "红米" in attrs.device_brands or "redmi" in attrs.device_brands
    assert "k80" in attrs.models, f"models: {attrs.models}"
    assert attrs.category == "screen_protector", f"category: {attrs.category}"
    assert "防窥" in attrs.features
    assert attrs.quantity == 2, f"quantity: {attrs.quantity}"
    print("test_parse_basic PASS")


def test_parse_iphone():
    """iPhone型号解析"""
    attrs = parse_product_title("图拉斯iPhone16ProMax钢化膜AR膜防摔")
    assert attrs.product_brand == "图拉斯"
    assert "iphone16promax" in attrs.models or "iphone16pro" in attrs.models or len(attrs.models) > 0
    assert attrs.category == "screen_protector"
    print("test_parse_iphone PASS")


def test_fixtures():
    """测试 fixture 中的 20 个 case"""
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "matching_cases.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    passed = 0
    failed = 0

    for case in cases:
        xy_item = {"title": case["xy_title"], "price": case["xy_price"]}
        pdd_item = {"title": case["pdd_title"], "price": case["pdd_price"]}

        result = match_products_v2(xy_item, pdd_item)

        name = case["name"]
        ok = True
        errors = []

        if result.decision != case["expect_decision"]:
            if case["expect_decision"] == "reject_or_low_grade":
                if result.grade in ("C", "D") and result.decision != "reject":
                    pass  # 可接受的低置信度，不报错
                else:
                    ok = False
                    errors.append(f"low grade case: got {result.decision}/{result.grade}")
            else:
                ok = False
                errors.append(f"decision: got {result.decision}/{result.grade}, expected {case['expect_decision']}")

        if "expect_grade_min" in case and result.grade < case["expect_grade_min"]:
            ok = False
            errors.append(f"grade too low: {result.grade} < {case['expect_grade_min']}")

        if "expect_grade_max" in case and result.grade > case["expect_grade_max"]:
            ok = False
            errors.append(f"grade too high: {result.grade} > {case['expect_grade_max']}")

        if "expect_risk" in case and case["expect_risk"] not in result.risk_flags:
            ok = False
            errors.append(f"missing risk: {case['expect_risk']}, got {result.risk_flags}")

        if ok:
            passed += 1
        else:
            failed += 1
            print(f"FAIL: {name}")
            for e in errors:
                print(f"  {e}")
            print(f"  闲鱼: {case['xy_title'][:40]}")
            print(f"  PDD: {case['pdd_title'][:40]}")
            print(f"  grade={result.grade} score={result.final_score:.2f} reasons={result.reasons}")
            print(f"  xy_attrs: brand={result.parsed_xianyu.product_brand} models={result.parsed_xianyu.models} cat={result.parsed_xianyu.category}")
            print(f"  pdd_attrs: brand={result.parsed_pdd.product_brand} models={result.parsed_pdd.models} cat={result.parsed_pdd.category}")
            print()

    print(f"\n=== Results: {passed}/{len(cases)} passed, {failed} failed ===")
    assert failed == 0, f"{failed} test cases failed"


def test_risk_detection():
    """风险检测测试"""
    # 低价引流
    xy = parse_product_title("K80钢化膜")
    pdd = parse_product_title("K80钢化膜")
    risks = detect_risks(xy, pdd, 0.5, [8.0, 0.5, 12.0])
    assert "low_price_teaser" in risks
    assert "sku_price_uncertain" in risks
    print("test_risk_detection PASS")


def test_negative_models():
    """否定型号测试"""
    attrs = parse_product_title("红米K80钢化膜不适用K80Pro")
    assert "k80pro" in attrs.negative_models, f"negative: {attrs.negative_models}"
    assert "k80" in attrs.models
    print("test_negative_models PASS")


if __name__ == "__main__":
    test_parse_basic()
    test_parse_iphone()
    test_risk_detection()
    test_negative_models()
    all_pass = test_fixtures()

    if all_pass:
        print("\nALL TESTS PASSED")
    else:
        print("\nSOME TESTS FAILED")
        sys.exit(1)
