"""AI店长 v1.2 - 拼多多开放平台 API 抓取器

使用 pdd.ddk.goods.search 接口直接获取商品数据，
绕过网页反爬虫限制。

签名算法：MD5(secret + 排序参数拼接 + secret)
"""
import hashlib
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

# PDD OAuth Token 刷新端点
PDD_OAUTH_TOKEN_URL = "https://open-api.pinduoduo.com/oauth/token"


class ScraperPddApi:
    """拼多多开放平台 API 抓取器"""

    PLATFORM_NAME = "pdd"
    PLATFORM_KEY = "pdd"

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "ScraperPddApi":
        """从配置字典创建实例（支持多账号池）"""
        pdd_cfg = config.get("pdd_api", {})
        if not pdd_cfg:
            pdd_cfg = config
        scraper = cls(
            client_id=pdd_cfg.get("client_id", ""),
            client_secret=pdd_cfg.get("client_secret", ""),
            api_url=pdd_cfg.get("api_url", "https://gw-api.pinduoduo.com/api/router"),
            pid=pdd_cfg.get("pid", ""),
            access_token=pdd_cfg.get("access_token", ""),
            refresh_token=pdd_cfg.get("refresh_token", ""),
            custom_parameters=pdd_cfg.get("custom_parameters", ""),
        )
        # 加载账号池作为备用
        pool_cfg = config.get("pdd_accounts", {})
        count = int(pool_cfg.get("count", 0))
        for i in range(1, count + 1):
            prefix = f"account_{i}"
            aid = pool_cfg.get(f"{prefix}_client_id", "")
            # 跳过和主账号相同的
            if aid and aid != pdd_cfg.get("client_id", ""):
                scraper._pool_accounts.append({
                    "client_id": aid,
                    "client_secret": pool_cfg.get(f"{prefix}_client_secret", ""),
                    "access_token": pool_cfg.get(f"{prefix}_access_token", ""),
                    "refresh_token": pool_cfg.get(f"{prefix}_refresh_token", ""),
                    "pid": pool_cfg.get(f"{prefix}_pid", ""),
                })
        if scraper._pool_accounts:
            logger.info("[pdd_api] loaded %d backup accounts", len(scraper._pool_accounts))
        return scraper

    def __init__(self, client_id: str, client_secret: str,
                 api_url: str = "https://gw-api.pinduoduo.com/api/router",
                 pid: str = "", access_token: str = "",
                 custom_parameters: str = "",
                 refresh_token: str = ""):
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_url = api_url
        self.pid = pid
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.custom_parameters = custom_parameters
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/x-www-form-urlencoded",
        })
        # 禁用代理 - PDD API 必须直连
        self.session.trust_env = False
        self._pool_accounts: list = []  # 备用账号列表
        self._used_pool_indices: set = set()  # 本轮已轮换过的索引

    def refresh_access_token(self) -> bool:
        """使用 refresh_token 刷新 access_token

        Returns:
            刷新成功返回 True
        """
        if not self.refresh_token:
            logger.error("[pdd_api] 无 refresh_token，无法刷新")
            return False

        try:
            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            }

            response = self.session.post(
                PDD_OAUTH_TOKEN_URL,
                data=data,
                timeout=15
            )
            response.raise_for_status()
            result = response.json()

            if "error" in result:
                logger.error("[pdd_api] Token 刷新失败: %s", result.get("error_description"))
                return False

            # 更新 tokens
            self.access_token = result.get("access_token", "")
            self.refresh_token = result.get("refresh_token", "")

            if self.access_token:
                logger.info("[pdd_api] Token 刷新成功，新 access_token: %s...",
                            self.access_token[:20])
                return True

            logger.error("[pdd_api] Token 刷新失败: 未获取到 access_token")
            return False

        except requests.RequestException as e:
            logger.error("[pdd_api] Token 刷新请求失败: %s", e)
            return False

    def _save_token_to_config(self) -> bool:
        """将新 token 保存到 config.ini"""
        try:
            import configparser
            import os

            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                "config.ini"
            )

            if not os.path.exists(config_path):
                logger.warning("[pdd_api] config.ini 不存在: %s", config_path)
                return False

            config = configparser.ConfigParser()
            config.read(config_path, encoding='utf-8')

            if 'pdd_api' not in config:
                config['pdd_api'] = {}

            config['pdd_api']['access_token'] = self.access_token
            config['pdd_api']['refresh_token'] = self.refresh_token

            with open(config_path, 'w', encoding='utf-8') as f:
                config.write(f)

            logger.info("[pdd_api] Token 已保存到 config.ini")
            return True

        except Exception as e:
            logger.error("[pdd_api] 保存 token 到 config.ini 失败: %s", e)
            return False

    def _generate_sign(self, params: Dict[str, Any]) -> str:
        """生成 API 签名

        签名算法：MD5(secret + 排序参数拼接 + secret)
        """
        sorted_params = sorted(params.items(), key=lambda x: x[0])
        param_str = self.client_secret
        for k, v in sorted_params:
            param_str += f"{k}{v}"
        param_str += self.client_secret

        return hashlib.md5(param_str.encode("utf-8")).hexdigest().upper()

    def _rotate_account(self) -> bool:
        """切换到下一个未使用的备用账号"""
        for idx, acc in enumerate(self._pool_accounts):
            if idx in self._used_pool_indices:
                continue
            self.client_id = acc["client_id"]
            self.client_secret = acc["client_secret"]
            self.access_token = acc["access_token"]
            self.refresh_token = acc.get("refresh_token", "")
            self.pid = acc.get("pid", "")
            self._used_pool_indices.add(idx)
            logger.info("[pdd_api] rotated to backup account %d: %s...", idx, self.client_id[:15])
            return True
        logger.warning("[pdd_api] ALL accounts rate-limited")
        return False

    def search(self, keyword: str, page: int = 1,
               page_size: int = 20, sort_type: int = 0) -> List[Dict[str, Any]]:
        """搜索商品

        Args:
            keyword: 搜索关键词
            page: 页码
            page_size: 每页数量（最大100）
            sort_type: 排序方式（0=综合, 1=销量, 2=价格升序, 3=价格降序）

        Returns:
            商品列表
        """
        params = {
            "type": "pdd.ddk.goods.search",
            "client_id": self.client_id,
            "timestamp": str(int(time.time())),
            "keyword": keyword,
            "page": str(page),
            "page_size": str(max(min(page_size, 100), 10)),
            "sort_type": str(sort_type),
            "with_coupon": "false",
        }

        # 添加 access_token（如果有）
        if self.access_token:
            params["access_token"] = self.access_token

        # 添加推广位ID（如果有的话）
        if self.pid:
            params["pid"] = self.pid

        # 添加自定义参数（如果有的话）
        if self.custom_parameters:
            params["custom_parameters"] = self.custom_parameters

        # 生成签名
        params["sign"] = self._generate_sign(params)

        try:
            response = self.session.post(self.api_url, data=params, timeout=15)
            response.raise_for_status()
            result = response.json()

            # 检查错误
            if "error_response" in result:
                error = result["error_response"]
                error_code = error.get("error_code")
                error_msg = error.get("error_msg", "")

                # 限流错误 (50001, 50002)：优先切换账号
                if error_code in (50001, 50002):
                    if self._rotate_account():
                        logger.info("[pdd_api] switched to backup, retrying...")
                        return self.search(keyword, page, page_size, sort_type)
                    logger.warning("[pdd_api] no backup, waiting 65s...")
                    time.sleep(65)
                    try:
                        params["timestamp"] = str(int(time.time()))
                        params.pop("sign", None)
                        params["sign"] = self._generate_sign(params)
                        response = self.session.post(self.api_url, data=params, timeout=15)
                        response.raise_for_status()
                        result = response.json()
                        if "error_response" in result:
                            logger.error("[pdd_api] 限流重试失败: %s", result["error_response"])
                            return []
                        goods_response = result.get("goods_search_response", {})
                        goods_list = goods_response.get("goods_list", [])
                        logger.info("[pdd_api] 限流重试成功，'%s' 返回 %d 个商品",
                                    keyword, len(goods_list))
                        return [self._parse_goods(g) for g in goods_list]
                    except requests.RequestException as e:
                        logger.error("[pdd_api] 限流重试失败: %s", e)
                        return []

                # Token 过期错误 (7201)，自动刷新
                if error_code == 7201 or "access_token" in error_msg:
                    logger.warning("[pdd_api] Token 过期 (7201)，尝试自动刷新...")
                    if self.refresh_access_token():
                        # 保存到 config.ini
                        self._save_token_to_config()
                        # 重试请求（仅重试一次）
                        params["access_token"] = self.access_token
                        params.pop("sign", None)  # 移除旧签名
                        params["sign"] = self._generate_sign(params)
                        try:
                            response = self.session.post(self.api_url, data=params, timeout=15)
                            response.raise_for_status()
                            result = response.json()
                            if "error_response" in result:
                                logger.error("[pdd_api] 重试失败: %s", result["error_response"])
                                return []
                            # 重试成功，继续解析
                            goods_response = result.get("goods_search_response", {})
                            goods_list = goods_response.get("goods_list", [])
                            logger.info("[pdd_api] Token 刷新后搜索 '%s' 返回 %d 个商品",
                                        keyword, len(goods_list))
                            return [self._parse_goods(g) for g in goods_list]
                        except requests.RequestException as e:
                            logger.error("[pdd_api] 重试请求失败: %s", e)
                            return []
                    else:
                        logger.error("[pdd_api] Token 刷新失败，无法继续")
                        return []

                logger.error("[pdd_api] API 错误: %s - %s", error_code, error_msg)
                return []

            # 提取商品列表
            goods_response = result.get("goods_search_response", {})
            goods_list = goods_response.get("goods_list", [])

            logger.info("[pdd_api] 搜索 '%s' 返回 %d 个商品",
                        keyword, len(goods_list))

            return [self._parse_goods(g) for g in goods_list]

        except requests.RequestException as e:
            logger.error("[pdd_api] 请求失败: %s", e)
            return []
        except (KeyError, ValueError) as e:
            logger.error("[pdd_api] 解析响应失败: %s", e)
            return []

    def _parse_goods(self, goods: Dict[str, Any]) -> Dict[str, Any]:
        """解析商品数据为统一格式"""
        # 价格单位是分，需要转换为元
        min_group_price = goods.get("min_group_price", 0)
        min_normal_price = goods.get("min_normal_price", 0)
        price = min_group_price if min_group_price > 0 else min_normal_price
        price_yuan = price / 100 if price > 0 else 0

        # 提取店铺信息
        mall_name = goods.get("mall_name", "")
        mall_id = goods.get("mall_id", "")

        # 构建商品链接
        goods_id = goods.get("goods_id", "")
        goods_sign = goods.get("goods_sign", "")
        product_url = f"https://mobile.yangkeduo.com/goods.html?goods_id={goods_id}"

        # 构建店铺链接
        store_url = ""
        if mall_id:
            store_url = f"https://mobile.yangkeduo.com/store.html?mall_id={mall_id}"

        # 图片链接
        image_url = goods.get("goods_image_url", "")
        if not image_url:
            image_url = goods.get("hd_thumb_url", "")

        # 销量
        sales = goods.get("sales_tip", "")
        sales_count = 0
        if "万" in sales:
            try:
                sales_count = int(float(sales.replace("万", "")) * 10000)
            except ValueError:
                pass
        elif sales.isdigit():
            sales_count = int(sales)

        # 优惠券
        coupon_discount = goods.get("coupon_discount", 0)
        if isinstance(coupon_discount, (int, float)):
            coupon_discount = coupon_discount / 100
        else:
            coupon_discount = 0

        # 地区/品类
        region = goods.get("opt_name", "") or goods.get("category_name", "")

        # 描述
        desc = goods.get("goods_desc", "")[:200] if goods.get("goods_desc") else ""

        # 好评率
        goods_rating = goods.get("goods_eval_score", 0)

        return {
            "platform": "pdd",
            "product_id": str(goods_id),
            "title": goods.get("goods_name", ""),
            "price": price_yuan,
            "original_price": min_normal_price / 100 if min_normal_price > 0 else price_yuan,
            "sales_count": sales_count,
            "sales_tip": sales,
            "seller_name": mall_name,
            "seller_id": str(mall_id),
            "seller_credit": "",
            "product_url": product_url,
            "store_url": store_url,
            "image_url": image_url,
            "region": region,
            "coupon_discount": coupon_discount,
            "has_coupon": coupon_discount > 0,
            "description": desc,
            "goods_rating": goods_rating,
            "raw_data": goods,
        }

    def fetch(self, keyword: str, max_items: int = 20) -> List[Dict[str, Any]]:
        """抓取商品（兼容 ScraperPdd 接口）"""
        self._used_pool_indices.clear()  # 每次搜索重置轮换
        all_items = []
        page = 1
        page_size = min(max_items, 100)

        while len(all_items) < max_items:
            items = self.search(keyword, page=page, page_size=page_size)
            if not items:
                break

            all_items.extend(items)
            page += 1

            # 避免请求过快
            time.sleep(0.5)

        return all_items[:max_items]

    def _has_login_state(self) -> bool:
        return bool(self.client_id and self.client_secret and self.access_token)

    def health_check(self) -> bool:
        try:
            items = self.search("test", page=1, page_size=10)
            return len(items) > 0
        except Exception:
            return False


__all__ = ["ScraperPddApi"]
