import copy
import unittest
from datetime import date
from watcher import (URAYASU, KATSUSHIKA_COURTS, make_slot, slot_key, parse_urayasu,
                     parse_katsushika, update_state, target_dates, next_month)
from notify import notification_marker


class WatcherTests(unittest.TestCase):
    def areas(self):
        areas=[]
        for f,letters in URAYASU.items():
            rows=[]
            for c in letters:
                headers=[{'text':str(h),'x':(h-9)*50} for h in range(9,22)]
                cells=[{'text':'×','x':i*100,'right':i*100+100} for i in range(6)]
                cells.append({'text':'','x':600,'right':650})
                rows.append({'court':c+'面','headers':headers,'cells':cells})
            areas.append({'facility':f,'rows':rows})
        return areas

    def test_separate_tables_two_hour_span(self):
        areas=self.areas()
        areas[0]['rows'][0]['cells'][5]['text']='〇'
        slots, coverage=parse_urayasu(areas,date(2026,10,17))
        self.assertEqual(slots[0]['time'],'19:00-21:00')
        self.assertEqual(len(coverage),8)
        self.assertEqual(sum(len(c) for c in coverage.values()),28)

    def test_unavailable_symbols_and_missing_court(self):
        areas=self.areas(); areas[0]['rows'][0]['cells'][0]['text']='-'
        areas[1]['rows'][0]['cells'][0]['text']='休館'
        self.assertEqual(parse_urayasu(areas,date(2026,10,17))[0],[])
        areas[-1]['rows'].pop()
        with self.assertRaises(ValueError): parse_urayasu(areas,date(2026,10,17))
        with self.assertRaises(ValueError): parse_urayasu(areas[:-1],date(2026,10,17))

    def test_bad_geometry_fails(self):
        areas=self.areas();areas[0]['rows'][0]['cells'][0]['right']=80
        with self.assertRaises(ValueError):parse_urayasu(areas,date(2026,10,17))

    def test_katsushika_explicit_half_hour_and_surfaces(self):
        def cell(text='',alt=None):
            return {'text':text,'colspan':1,'images':[] if alt is None else [{'alt':alt,'src':'image.gif'}]}
        table=[[cell('2026年\n11月3日'),cell('７回\n1830-2030')]]
        table += [[cell('テニス'+c+'オムニ'),cell(alt='空き' if c=='B' else '受付期間外')] for c in 'ABC']
        slots,courts=parse_katsushika([table],date(2026,11,3),'にいじゅくみらい公園')
        self.assertEqual(slots[0]['time'],'18:30-20:30');self.assertEqual(slots[0]['court'],'B面')
        with self.assertRaises(ValueError): parse_katsushika([table],date(2026,11,1),'にいじゅくみらい公園')
        with self.assertRaises(ValueError): parse_katsushika([table[:-1]],date(2026,11,3),'にいじゅくみらい公園')

    def test_dedup_failure_and_actual_reopening(self):
        s=make_slot('urayasu',date(2026,10,17),next(iter(URAYASU)),'Ａ面','19:00','21:00')
        scope=[{'city':'urayasu','date':s['date'],'facility':s['facility']}]
        state={'slots':{}};self.assertEqual(update_state(state,[s],scope),[s])
        first=notification_marker([s],state)
        state['slots'][slot_key(s)]['notified']=True
        self.assertEqual(update_state(state,[s],scope),[])
        update_state(state,[],[])  # failed check cannot mark it filled
        self.assertEqual(update_state(state,[s],scope),[])
        update_state(state,[],scope)  # confirmed filled
        self.assertEqual(update_state(state,[s],scope),[s])
        self.assertNotEqual(first,notification_marker([s],state))

    def test_unacknowledged_delivery_retry_same_marker(self):
        s=make_slot('urayasu',date(2026,10,17),next(iter(URAYASU)),'A面','19:00','21:00')
        state={'slots':{}};update_state(state,[s],[])
        marker=notification_marker([s],state)
        update_state(state,[s],[])
        self.assertEqual(marker,notification_marker([s],state))

    def test_date_range_cross_month_and_holiday(self):
        self.assertEqual(next_month(date(2026,1,31)),date(2026,2,28))
        ds=target_dates(date(2026,10,26),7)
        self.assertNotIn(date(2026,11,3),ds)
        self.assertIn(date(2026,11,3),target_dates(date(2026,10,27),7))
        self.assertIn(date(2026,5,6),target_dates(date(2026,5,4),7))


if __name__=='__main__': unittest.main()
