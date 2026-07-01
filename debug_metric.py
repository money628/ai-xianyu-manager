"""Debug: capture actual HTML output from metric_card"""
import sys, os, tempfile
sys.path.insert(0, 'src')
sys.path.insert(0, '.')

from pages import icon, ICON_MAP

# Test 1: icon function returns emoji, NOT html
results = []
for key in ['today', 'trending_up', 'local_fire_department', 'notifications_active',
            'inventory_2', 'sell', 'rate_review']:
    val = icon(key)
    results.append(f"icon({key}) = {repr(val)}  starts_with_lt = {val.startswith('<')}")

with open('debug_icon.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))

# Test 2: simulate what metric_card generates
def test_metric_card_html(label, value, icon_name=""):
    icon_html = icon(icon_name) if icon_name else ""
    html = f"""<div class="kpi-metric">
    <div class="kpi-label">{icon_html} {label}</div>
    <div class="kpi-value">{value}</div>
    </div>"""
    return html

# Test with integer value
h1 = test_metric_card_html("test", 42, "today")
# Test with string value
h2 = test_metric_card_html("test", "3.5%", "trending_up")
# Test with zero
h3 = test_metric_card_html("test", 0, "sell")

with open('debug_metric.txt', 'w', encoding='utf-8') as f:
    f.write("=== HTML for value=42 ===\n")
    f.write(h1 + '\n\n')
    f.write("=== HTML for value='3.5%' ===\n")
    f.write(h2 + '\n\n')
    f.write("=== HTML for value=0 ===\n")
    f.write(h3 + '\n')
