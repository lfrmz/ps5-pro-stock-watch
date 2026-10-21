import unittest
from unittest.mock import patch

from monitor import looks_like_ps5_pro, parse_page, update_report, offer_state


def item(mode=None):
    d = dict(id='demo', name='PlayStation 5 Pro Console',
             retailer='Example AU retailer', condition='new',
             url='https://example.com/ps5-pro')
    if mode:
        d.update(mode=mode, match='PS5 PlayStation 5 Pro Console')
    return d


class StockParserTests(unittest.TestCase):
    def test_out_of_stock_overrides_hidden_buy_button(self):
        page = '<h1>PlayStation 5 Pro Console</h1><div>$1,399</div><p>Out of stock</p><button>Add to cart</button>'
        r = parse_page(item(), page)
        self.assertEqual('out_of_stock', r['status'])
        self.assertEqual(1399.0, r['price_aud'])

    def test_preorder_not_in_stock(self):
        page = '<div>PRE-ORDER Article 104141</div><h1>PlayStation 5 Pro Console</h1><b>$1399</b><button>Pre-order</button>'
        self.assertEqual('preorder', parse_page(item(), page)['status'])

    def test_active_add_to_basket(self):
        page = '<h1>PlayStation 5 Pro Console</h1><p>$1398</p><button>Add To Basket</button>'
        self.assertEqual('in_stock', parse_page(item(), page)['status'])

    def test_unknown_if_only_nav_contains_button(self):
        page = '<nav><button>Add to Cart</button></nav><h1>PlayStation 5 Pro Console</h1><p>Some product info</p>'
        self.assertEqual('unknown', parse_page(item(), page)['status'])

    def test_unknown_if_product_missing(self):
        page = '<h1>PS5 Slim Console</h1><button>Add to Cart</button>'
        self.assertEqual('unknown', parse_page(item(), page)['status'])

    def test_json_ld_product_only(self):
        page = '''<h1>PlayStation 5 Pro Console</h1>
        <script type="application/ld+json">{"@type":"Product","name":"PlayStation 5 Pro Console",
        "offers":{"@type":"Offer","availability":"https://schema.org/InStock","price":"1299.95"}}</script>'''
        r = parse_page(item(), page)
        self.assertEqual('in_stock', r['status'])
        self.assertEqual(1299.95, r['price_aud'])

    def test_listing_doesnt_include_next_preorder(self):
        page = '<h1>PlayStation 5 Consoles</h1><p>PS5 PlayStation 5 Pro Console</p><span>Limit one per customer</span><div>Compare</div><p>PS5 GTA VI Bundle PRE-ORDER</p>'
        self.assertNotEqual('preorder', parse_page(item('listing'), page)['status'])

    def test_ps5_slim_and_ps4_pro_excluded(self):
        self.assertFalse(looks_like_ps5_pro('PlayStation 5 Slim'))
        self.assertFalse(looks_like_ps5_pro('PS4 Pro'))
        self.assertTrue(looks_like_ps5_pro('PS5 Pro Digital Console'))


class AlertTests(unittest.TestCase):
    def obs(self, status):
        return {**item(), 'status': status, 'checked_at': '2026-10-22T00:00:00Z',
                'reason': 'example', 'price_aud': 1399.0}

    @patch('monitor.send_notification', return_value=True)
    def test_one_alert_when_stock_remains(self, send):
        report = update_report([], {}, [self.obs('in_stock')], False, 't1')
        self.assertTrue(report['items'][0]['alerted'])
        report = update_report([], report, [self.obs('in_stock')], False, 't2')
        self.assertEqual(1, send.call_count)

    @patch('monitor.send_notification', return_value=True)
    def test_unknown_doesnt_reset_suppression(self, send):
        report = update_report([], {}, [self.obs('in_stock')], False, 't1')
        report = update_report([], report, [self.obs('unknown')], False, 't2')
        report = update_report([], report, [self.obs('in_stock')], False, 't3')
        self.assertEqual(1, send.call_count)

    @patch('monitor.send_notification', return_value=True)
    def test_restock_after_confirmed_outage_alerts_again(self, send):
        report = update_report([], {}, [self.obs('in_stock')], False, 't1')
        report = update_report([], report, [self.obs('out_of_stock')], False, 't2')
        report = update_report([], report, [self.obs('in_stock')], False, 't3')
        self.assertEqual(2, send.call_count)

    @patch('monitor.send_notification', return_value=True)
    def test_preorders_are_displayed_but_not_alerted_by_default(self, send):
        report = update_report([], {}, [self.obs('preorder')], False, 't1')
        self.assertFalse(report['items'][0]['alerted'])
        send.assert_not_called()

    @patch('monitor.send_notification', return_value=False)
    def test_retry_after_alert_delivery_failure(self, send):
        report = update_report([], {}, [self.obs('in_stock')], False, 't1')
        self.assertFalse(report['items'][0]['alerted'])
        report = update_report([], report, [self.obs('in_stock')], False, 't2')
        self.assertEqual(2, send.call_count)


if __name__ == '__main__':
    unittest.main()
