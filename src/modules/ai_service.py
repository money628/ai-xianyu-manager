"""AI 服务层 — DeepSeek API"""
import json, logging, time, requests
from typing import Optional

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
API_KEY = None  # Will be loaded from config


def _get_key() -> str:
    global API_KEY
    if API_KEY:
        return API_KEY
    try:
        from config import load_config
        cfg = load_config("config.ini").as_dict()
        API_KEY = cfg.get("ai", {}).get("api_key", "")
    except Exception:
        pass
    return API_KEY
MAX_RETRIES = 3
_total_calls = 0
_total_tokens = 0


def get_usage() -> tuple:
    cost = _total_tokens / 1000 * 0.001
    return _total_calls, _total_tokens, round(cost, 4)


def _call(prompt: str, system: str = "", temperature: float = 0.7) -> Optional[str]:
    global _total_calls, _total_tokens
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(
                ENDPOINT,
                headers={"Authorization": f"Bearer {_get_key()}", "Content-Type": "application/json"},
                json={"model": "deepseek-chat", "messages": messages, "temperature": temperature, "max_tokens": 800},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            usage = data.get("usage", {})
            _total_tokens += usage.get("total_tokens", 0)
            _total_calls += 1
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(1 * (attempt + 1))
            else:
                logger.warning("AI call failed after %d attempts: %s", MAX_RETRIES, e)
                return None


def generate_listing_title(product_info: str) -> str:
    return _call(
        f"为以下商品生成一个闲鱼标题（20-30字，吸引人，别太广告化）：\n{product_info}",
        "你是闲鱼卖家，写标题要真实自然，不说官话假话。不要用emoji。"
    ) or product_info[:30]


def generate_listing_description(product_info: str, specs: str = "") -> str:
    prompt = f"为以下商品写一段闲鱼描述（100-200字，口语化，像真人在卖闲置）：\n商品：{product_info}"
    if specs:
        prompt += f"\n规格：{specs}"
    prompt += "\n\n要求：分点写、说明规格可选、发货时间、售后政策。别用emoji。"
    return _call(prompt, "你是闲鱼卖家，描述要真实自然接地气。") or ""


def generate_customer_scripts(product_info: str) -> dict:
    text = _call(
        f"为这个商品生成3个常见客服问答（价格、规格、发货各一个）：\n{product_info}",
        "简短回答，每个不超过30字。"
    )
    if not text:
        return {"价格": "直接拍下即可", "规格": "详情里有哦", "发货": "48小时内发货"}
    scripts = {}
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or len(line) < 3:
            continue
        if "：" in line:
            k, v = line.split("：", 1)
            scripts[k.strip()] = v.strip()
        elif ":" in line:
            k, v = line.split(":", 1)
            scripts[k.strip()] = v.strip()
    return scripts or {"常见问题": text[:100]}


def is_clothing(title: str) -> tuple:
    """AI 判断是否服装类，返回 (是服装, 原因)"""
    text = _call(
        f"判断以下商品标题是否属于服装/鞋帽/内衣/袜子/围巾/帽子类。只回答 yes 或 no，然后一句话说明。\n标题：{title}",
        "你是一个商品分类助手。",
        temperature=0.1,
    )
    if not text:
        return False, ""
    is_cloth = text.lower().startswith("yes") or "是" in text[:5]
    return is_cloth, text


def generate_family_name(variants: str) -> str:
    """为多个变体生成统一商品族名称"""
    return _call(
        f"为以下多个商品变体生成一个统一的商品族名称（15字以内，突出品牌和品类）：\n{variants}",
        "简短精炼，不废话。",
        temperature=0.3,
    ) or variants[:20]


def generate_traffic_advice(stats: str) -> str:
    """根据流量数据给出建议"""
    return _call(
        f"根据以下商品流量数据，给1-2条运营建议：\n{stats}",
        "你是电商运营专家，建议要具体可执行。不超过50字。",
        temperature=0.5,
    ) or ""


def quick_test():
    """快速验证 API 是否可用"""
    result = _call("回复 OK", temperature=0.1)
    print("API test:", "OK" if result else "FAILED", result[:20] if result else "")
    return bool(result)


if __name__ == "__main__":
    quick_test()
