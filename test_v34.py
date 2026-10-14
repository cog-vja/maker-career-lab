import io,unittest,zipfile
import edinet_v34 as v

def blob(rows):
    data='要素ID\t項目名\tコンテキストID\t相対年度\t連結・個別\t期間・時点\tユニットID\t単位\t値\n'+''.join(f'{e}\t\t{c}\t\t\t\t{u}\t\t{x}\n' for e,c,u,x in rows)
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:z.writestr('XBRL_TO_CSV/test.csv',data.encode('utf-16'))
    return b.getvalue()

class V34Tests(unittest.TestCase):
    def test_ifrs_and_equity(self):
        b=blob([('NetSalesIFRS','CurrentYearDuration','JPY','10000000000'),('AssetsIFRS','CurrentYearInstant','JPY','20000000000'),('EquityAttributableToOwnersOfParentIFRS','CurrentYearInstant','JPY','8000000000')])
        r=v.review(b,{'docID':'TEST0001'})
        self.assertEqual(r['accounting_standard']['standard'],'IFRS')
        self.assertEqual(r['selected_values']['equity_ratio_pct'],'40.00')
        self.assertFalse(r['quality_gate']['ready_for_publication'])
    def test_us_gaap_blocks_numeric(self):
        b=blob([('ConsolidatedBalanceSheetUSGAAPTextBlock','CurrentYearDuration','', '<table><tr><td>Cash</td></tr></table>'),('NetSales','CurrentYearDuration','JPY','10000000000')])
        r=v.review(b,{'docID':'TEST0002'})
        self.assertEqual(r['accounting_standard']['standard'],'US_GAAP')
        self.assertIsNone(r['selected_values']['revenue_oku'])
        self.assertTrue(r['textblock_inventory'])
    def test_unknown_not_forced(self):
        b=blob([('CustomMetric','CurrentYearDuration','JPY','5')])
        r=v.review(b,{'docID':'TEST0003'})
        self.assertEqual(r['accounting_standard']['standard'],'UNKNOWN')
    def test_no_ticker_rules(self):
        b=blob([('NetSalesIFRS','CurrentYearDuration','JPY','10000000000')])
        for ticker in ('6645','6857'):
            r=v.review(b,{'ticker':ticker})
            self.assertEqual(r['accounting_standard']['standard'],'IFRS')
    def test_ratio_conflict_rejected(self):
        b=blob([('NetSalesIFRS','CurrentYearDuration','JPY','10000000000'),('AssetsIFRS','CurrentYearInstant','JPY','20000000000'),('Assets','CurrentYearInstant','JPY','21000000000'),('EquityAttributableToOwnersOfParentIFRS','CurrentYearInstant','JPY','8000000000')])
        self.assertIsNone(v.review(b,{})['selected_values']['equity_ratio_pct'])
if __name__=='__main__':unittest.main()
