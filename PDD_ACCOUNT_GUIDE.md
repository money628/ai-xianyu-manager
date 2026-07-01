# PDD 开放平台注册 + 授权流程

## 1. 注册开发者账号

浏览器打开: https://open.pinduoduo.com

点击右上角"注册" → 用**另一个手机号**注册（不能用已有账号的手机号）

注意事项：
- 必须实名认证（身份证 + 银行卡/支付宝）
- 一个身份证只能实名一个账号（需要借家人/朋友的身份证）
- 如果自己实名了第一个，第二个需要用别人身份证

## 2. 创建应用

登录后 → 控制台 → 应用管理 → 创建应用

- 应用名称: 随便填（如"选品助手2"）
- 应用类型: 多多客推广工具
- 填写基本信息后提交审核（通常几分钟到几小时通过）

## 3. 获取 client_id 和 client_secret

应用审核通过后 → 应用详情 → 复制:
- **client_id** (应用ID)
- **client_secret** (应用密钥)

## 4. 获取 access_token

用刚拿到的 client_id 拼接授权 URL（在浏览器打开）:

```
https://mms.pinduoduo.com/open.html?response_type=code&client_id=你的client_id&redirect_uri=https://open.pinduoduo.com&state=test
```

在弹出页面点"同意授权" → 跳转后地址栏里 code= 后面那串就是授权码。

然后用 Python 换 token:

```python
import requests
r = requests.post("https://open-api.pinduoduo.com/oauth/token", data={
    "client_id": "你的client_id",
    "client_secret": "你的client_secret",
    "grant_type": "authorization_code",
    "code": "地址栏里的code",
})
print(r.json())
# 返回 access_token 和 refresh_token
```

## 5. 配置到项目

打开 config.ini，把 `pdd_accounts` 段改成:

```ini
[pdd_accounts]
count = 2

# 账号1
account_1_client_id = "5faa6042b15e47a9b069ecb4bc341e99"
account_1_client_secret = "15b3790d5bac81b2c1b20a89396e4dbca073fb9a"
account_1_access_token = "9803dfce4cd34710b9b23898f6d90a7971cc91a3"
account_1_refresh_token = "c70dac263c564e5d9421c518f1d37b7b88017f11"
account_1_pid = "44528269_316642966"

# 账号2（新注册的）
account_2_client_id = "新client_id"
account_2_client_secret = "新client_secret"
account_2_access_token = "新access_token"
account_2_refresh_token = "新refresh_token"
account_2_pid = "新pid（在多多客推广位创建）"
```

## 6. 验证

```bash
python data_source_health.py
```

看 PDD 账号池应该显示 2 个可用账号。
