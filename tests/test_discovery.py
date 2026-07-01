"""AI店长 v1.1 - 品类发现模块测试"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.modules.discovery import (
    DEFAULT_SEED_CATEGORIES,
    expand_categories,
    expand_to_flat_list,
    _call_suggest_api,
)


def _mock_suggest_response(keyword, timeout=10):
    """模拟淘宝建议 API 响应"""
    mock_data = {
        "玩具": ["玩具车", "玩具女孩", "玩具男孩", "益智玩具", "积木玩具"],
        "手机壳": ["手机壳华为", "手机壳苹果", "手机壳小米", "手机壳OPPO"],
        "收纳盒": ["收纳盒桌面", "收纳盒衣服", "收纳盒袜子"],
    }
    return mock_data.get(keyword, [f"{keyword}热门1", f"{keyword}热门2"])


class TestDiscovery(unittest.TestCase):

    @patch("src.modules.discovery._call_suggest_api", side_effect=_mock_suggest_response)
    def test_expand_categories(self, mock_api):
        result = expand_categories(seeds=["玩具", "手机壳"], max_per_seed=5)
        self.assertIn("玩具", result)
        self.assertIn("手机壳", result)
        self.assertEqual(len(result["玩具"]), 5)
        self.assertEqual(len(result["手机壳"]), 4)
        self.assertEqual(mock_api.call_count, 2)

    @patch("src.modules.discovery._call_suggest_api", side_effect=_mock_suggest_response)
    def test_expand_to_flat_list(self, mock_api):
        flat = expand_to_flat_list(seeds=["玩具", "收纳盒"], max_per_seed=5)
        # 种子词 + 扩展词，去重
        self.assertIn("玩具", flat)
        self.assertIn("收纳盒", flat)
        self.assertIn("玩具车", flat)
        self.assertIn("收纳盒桌面", flat)
        # 应该去重
        self.assertEqual(len(flat), len(set(flat)))

    @patch("src.modules.discovery._call_suggest_api", return_value=[])
    def test_expand_empty_api(self, mock_api):
        result = expand_categories(seeds=["不存在的品类"], max_per_seed=5)
        self.assertEqual(result["不存在的品类"], [])

    def test_default_seeds(self):
        self.assertEqual(len(DEFAULT_SEED_CATEGORIES), 30)
        self.assertIn("玩具", DEFAULT_SEED_CATEGORIES)
        self.assertIn("女装", DEFAULT_SEED_CATEGORIES)

    @patch("src.modules.discovery.requests.get")
    def test_call_suggest_api_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": [["玩具车", "100"], ["玩具女孩", "90"]]}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        kws = _call_suggest_api("玩具")
        self.assertEqual(kws, ["玩具车", "玩具女孩"])

    @patch("src.modules.discovery.requests.get")
    def test_call_suggest_api_failure(self, mock_get):
        import requests as req
        mock_get.side_effect = req.RequestException("network error")
        kws = _call_suggest_api("玩具")
        self.assertEqual(kws, [])


if __name__ == "__main__":
    unittest.main()
